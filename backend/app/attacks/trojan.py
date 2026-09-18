"""Trojan-horse attack — simplified conceptual model.

**This is a deliberately simplified, conceptual stand-in**, not a physical
trojan-horse simulation. A real THA attack pulses light *into* Alice's
apparatus and reads phase/intensity modulator reflections to infer her
settings; modelling that needs optical transfer matrices, isolation ratios,
and detector back-reflection models. None of that is attempted here.

The educational simplification: Eve's probing perturbs the qubits at
Alice's encoding step in a *local, correlated* way, so we model it as a
small localized error-rate patch on the qubit stream:

- a fixed 20% of positions (``PATCH_FRACTION``) act as the "modulator
  reflection" regions where information leaks,
- within a patch, each qubit flips with probability
  ``0.5 * intensity`` — coupling strength maps to disturbance,
- between patches the channel is untouched.

The result behaves like a Trojan leak should: a small localized error-rate
signature that scales with the attack knob, zero footprint at intensity 0,
and a QBER far below intercept-resend's at the same intensity (THA is
quiet per qubit, which is what makes it dangerous in practice).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from app.protocols.bb84 import Rng

#: Fraction of positions modelling modulator-reflection leakage patches.
PATCH_FRACTION = 0.2
#: Flip probability inside a patch at intensity 1.0.
MAX_PATCH_FLIP = 0.5


def _patch_mask(n: int, rng: Rng) -> np.ndarray:
    """Boolean mask marking the localized leakage regions."""
    return rng.random(n) < PATCH_FRACTION


def trojan_channel(
    qubits: Sequence[tuple[int, int]],
    rng: Rng,
    intensity: float = 0.5,
) -> list[tuple[int, int]]:
    """Apply localized bit disturbance at Alice's encoder.

    ``intensity`` is the back-door coupling strength: 0.0 -> perfect
    channel, 1.0 -> half the qubits inside leakage patches flip.
    """
    n = len(qubits)
    if n == 0:
        return []
    mask = _patch_mask(n, rng)
    flip = rng.random(n) < (MAX_PATCH_FLIP * intensity)
    return [
        (basis, bit ^ 1) if (in_patch and should_flip) else (basis, bit)
        for (basis, bit), in_patch, should_flip in zip(qubits, mask, flip)
    ]
