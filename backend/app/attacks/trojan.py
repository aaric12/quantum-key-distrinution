"""Trojan-horse attack — simplified conceptual model.

**This is a deliberately simplified, conceptual stand-in**, not a physical
trojan-horse simulation. A real THA attack pulses light *into* Alice's
apparatus and reads phase/intensity modulator reflections to infer her
settings; modelling that needs optical transfer matrices, isolation ratios,
and detector back-reflection models. None of that is attempted here.

The educational simplification: Eve's probing perturbs the qubits at
Alice's encoding step in a *local, correlated* way, so we model it as a
small localized error-rate signature on the qubit stream:

- the stream is partitioned into contiguous blocks; a fixed 20% of blocks
  (``PATCH_FRACTION``) act as the "modulator reflection" regions where
  information leaks,
- inside a leakage block, each qubit flips with probability
  ``0.5 * intensity`` — coupling strength maps to disturbance,
- everywhere else the channel is untouched.

The result behaves like a Trojan leak should: a small error-rate signature
that scales with the attack knob, **spatially clustered** (errors bunch
inside the leakage blocks instead of scattering uniformly — the property
that distinguishes THA from intercept-resend in the ML features), zero
footprint at intensity 0, and a QBER far below intercept-resend's at the
same intensity (THA is quiet per qubit, which is what makes it dangerous
in practice).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.protocols.bb84 import Rng

#: Fraction of transmission blocks modelling modulator-reflection regions.
PATCH_FRACTION = 0.2
#: Flip probability inside a leakage block at intensity 1.0.
MAX_PATCH_FLIP = 0.5
#: Number of contiguous blocks the transmission is partitioned into.
N_BLOCKS = 8


def trojan_channel(
    qubits: Sequence[tuple[int, int]],
    rng: Rng,
    intensity: float = 0.5,
) -> list[tuple[int, int]]:
    """Apply localized bit disturbance at Alice's encoder.

    ``intensity`` is the back-door coupling strength: 0.0 -> perfect
    channel, 1.0 -> half the qubits inside leakage blocks flip.
    """
    n = len(qubits)
    if n == 0:
        return []

    block_len = max(1, n // N_BLOCKS)
    flip = [False] * n
    for b in range(N_BLOCKS):
        lo = b * block_len
        hi = lo + block_len if b < N_BLOCKS - 1 else n
        if rng.random() >= PATCH_FRACTION:
            continue  # this block is clean
        p_flip = MAX_PATCH_FLIP * intensity
        for i in range(lo, hi):
            flip[i] = rng.random() < p_flip

    return [
        (basis, bit ^ 1) if should_flip else (basis, bit)
        for (basis, bit), should_flip in zip(qubits, flip)
    ]
