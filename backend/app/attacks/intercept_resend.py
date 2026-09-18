"""Intercept-resend attack: Eve measures in a random basis and re-sends.

Eve intercepts a fraction ``intensity`` of the flying qubits. For each she:

1. picks a random basis (Z or X),
2. measures in Born-rule simulation (same-basis outcome deterministic,
   conjugate-basis outcome a fair coin),
3. re-prepares the *measured* state and forwards it to Bob.

Resending in her measurement basis collapses the state: whenever Eve's basis
differs from Alice's, the qubit reaching Bob is wrong in either of Bob's
bases, giving the classic 25% QBER across the sifted key when Eve intercepts
everything (half the positions are conjugate-basis, half of those land in
the sifted set). Scaled by the intercepted fraction, expected sifted-key QBER
is ``intensity / 4``.

Eve learns nothing about the key on positions she skips and is statistically
detected by the QBER check — the run aborts once intensity/4 crosses the
abort threshold.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from app.protocols.bb84 import Rng


def intercept_resend(
    qubits: Sequence[tuple[int, int]],
    rng: Rng,
    intensity: float = 1.0,
) -> list[tuple[int, int]]:
    """Measure-and-resent qubits for the fraction of signals Eve intercepts.

    Untouched signals pass through unchanged. Returns the qubits as they
    arrive at Bob.
    """
    attacked: list[tuple[int, int]] = []
    for (basis, bit) in qubits:
        if rng.random() >= intensity:
            attacked.append((basis, bit))  # Eve let this one through untouched
            continue
        eve_basis = int(rng.integers(2))
        if eve_basis == basis:
            outcome = bit  # right basis: Eve reads the bit exactly
        else:
            outcome = int(rng.integers(2))  # conjugate basis: fair coin
        # Eve re-prepares in *her* basis and forwards; the original state is
        # destroyed by her measurement and never reaches Bob.
        attacked.append((eve_basis, outcome))
    return attacked
