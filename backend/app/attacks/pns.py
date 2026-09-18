"""Photon-number-splitting (PNS) attack via weak coherent pulses + decoys.

Model, in four layers:

1. **Weak coherent pulses.** Alice's laser emits coherent states whose photon
   number is Poisson distributed with mean ``mu`` (the signal intensity).
   Probability of n photons: ``p[n] = mu**n * exp(-mu) / n!``. Around
   mu ~ 0.1-0.5 most pulses are vacuum or single-photon, with a small tail
   of multi-photon pulses (n >= 2).

2. **The attack.** Eve performs a number-resolving non-demolition
   measurement. Single-photon pulses are left alone (blocking them would be
   visible); multi-photon pulses are *split*: she peels off one photon and
   stores it in a quantum memory, forwarding the rest losslessly. Later,
   after basis announcement, she measures her stored photon and knows the
   bit. She ideally keeps her presence hidden — the forwarded pulse looks
   perfect to Bob.

3. **The tell: loss statistics.** Her only unavoidable footprint is
   *which* pulses vanish. An honest channel's loss is intensity-independent
   (attenuation does not care how many photons a pulse carried), so the
   per-intensity loss rates should agree. Suppression tied to siphoned
   multi-photon pulses makes the loss rate intensity-dependent — visible as
   a spread across decoy levels beyond binomial noise. This is exactly why
   decoy states exist.

4. **Decoy intensities.** Alice randomly tags each pulse as signal
   (``mu``, e.g. 0.5) or decoy (``mu/4`` and ``mu/16`` here — 3 levels
   total, plus implicit vacuum). Decoy bits never enter the key; their
   per-intensity detection/loss rates are published. With Eve siphoning a
   fraction ``f`` of multi-photon pulses *and suppressing the corresponding
   pulses* to cover her tracks, the decoy loss rates diverge from the
   signal loss rate — quantified here by the PNS statistics payload.

The hook returns (qubits, stats): qubits carry ``LOST``-sentinel entries for
suppressed pulses, and ``stats`` carries the per-intensity tables plus the
divergence metrics the simulate API surfaces in the qber_check stage.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from app.protocols.bb84 import Rng

LOST = -1  # sentinel: pulse suppressed in transit; Bob detects nothing

# Decoy intensity levels relative to the signal mean mu: [1.0, 0.25, 0.0625].
# Three levels is the standard minimum for decoy-state analysis (signal +
# two decoys); the imbalance between their loss rates is the detection rule.
DECOY_LEVELS: tuple[float, ...] = (1.0, 0.25, 0.0625)

#: Intensity tag stored per qubit slot: 0 = signal, 1..2 = decoy levels.
SIGNAL = 0


def _multi_photon_prob(mu: float) -> float:
    """P(n >= 2) for a Poisson(mu) photon-number distribution."""
    return 1.0 - math.exp(-mu) * (1.0 + mu)


def _sample_photon_number(mu: float, rng: Rng) -> int:
    """Draw n ~ Poisson(mu) via inverse-CDF over a small truncated support."""
    n = 0
    term = math.exp(-mu)  # p(0)
    u = rng.random()
    while u > term and n < 64:
        n += 1
        term += math.exp(-mu) * mu**n / math.factorial(n)
    return n


def photon_number_splitting(
    qubits: Sequence[tuple[int, int]],
    rng: Rng,
    intensity: float = 0.5,
    mu_signal: float = 0.5,
    decoy_levels: Sequence[float] = DECOY_LEVELS,
):
    """Split multi-photon pulses and suppress siphoned ones.

    Parameters
    ----------
    qubits:
        (basis, bit) pairs; tags alternate per pulse below.
    rng:
        Shared randomness source.
    intensity:
        Fraction ``f`` of multi-photon pulses Eve siphons. A siphoned pulse
        is also *suppressed* (returns ``LOST``) so Bob reports a loss —
        leaving it through untouched would hand Eve nothing measurable,
        but real PNS must hide the siphoned photon's fate, and the
        suppression is precisely the statistical tell.
    mu_signal:
        Signal intensity mu; decoys sit at ``decoy_levels * mu``.
    decoy_levels:
        Relative intensity levels (level 1.0 = the signal itself).

    Returns
    -------
    ``(qubits_out, stats)`` where ``qubits_out`` replaces suppressed pulses
    with the ``LOST`` sentinel and keeps everything else unchanged, and
    ``stats`` carries the per-level yield/loss table and divergence metrics.
    """
    stats = {
        "mu_signal": mu_signal,
        "levels": [],
        "split_fraction": intensity,
        "multi_photon_rate": _multi_photon_prob(mu_signal),
    }
    out: list[tuple[int, int]] = []

    # Per-level detection accounting: [sent, lost, detected] per level.
    n_levels = len(decoy_levels)
    sent = [0] * n_levels
    lost = [0] * n_levels

    # Assign each pulse an intensity level round-robin with random jitter so
    # levels interleave along the line (simulation shorthand for Alice's
    # randomized decoy tagging).
    for idx, qubit in enumerate(qubits):
        level = rng.integers(n_levels)
        mu = mu_signal * decoy_levels[level]
        sent[level] += 1

        n_photons = _sample_photon_number(mu, rng)
        siphonable = n_photons >= 2 and rng.random() < intensity
        if siphonable:
            # Eve peels one photon off and suppresses the pulse: a loss Bob
            # (and the decoy analysis) will count.
            out.append((LOST, LOST))
            lost[level] += 1
        else:
            out.append(qubit)  # untouched: travels as-is, detected normally

    detected = [sent[i] - lost[i] for i in range(n_levels)]
    for i, rel in enumerate(decoy_levels):
        stats["levels"].append(
            {
                "mu": mu_signal * rel,
                "sent": sent[i],
                "lost": lost[i],
                "detected": detected[i],
                # Conditional loss rate P(loss | sent) at this intensity.
                "loss_rate": (lost[i] / sent[i]) if sent[i] else 0.0,
            }
        )

    # Detection rule (decoy-state analysis). Null hypothesis: an honest
    # channel's loss is intensity-INDEPENDENT — photons are lost to
    # attenuation regardless of how many were sent — so the per-level loss
    # rates should agree up to binomial sampling noise, i.e. spread ~ 0.
    # Eve's suppression is tied to multi-photon richness, which varies with
    # intensity, so her presence makes the spread exceed the noise floor.
    levels = stats["levels"]
    rates = [lvl["loss_rate"] for lvl in levels]
    stats["observed_spread"] = max(rates) - min(rates) if rates else 0.0

    # Binomial noise floor for the spread between the extreme levels.
    hi = max(levels, key=lambda l: l["loss_rate"])
    lo = min(levels, key=lambda l: l["loss_rate"])
    var = 0.0
    for lvl in (hi, lo):
        n, p = lvl["sent"], lvl["loss_rate"]
        if n:
            var += p * (1 - p) / n
    noise_floor = math.sqrt(var)
    stats["noise_floor"] = noise_floor
    stats["anomaly_z"] = (
        stats["observed_spread"] / noise_floor if noise_floor > 0 else 0.0
    )
    stats["flagged"] = stats["anomaly_z"] > 3.0  # ~3-sigma detection

    return out, stats
