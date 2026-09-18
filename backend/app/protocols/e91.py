"""E91 entanglement-based QKD protocol — not implemented yet.

Planned pipeline (Ekert 1991):

1. A source distributes entangled singlet pairs (|psi->) to Alice and Bob —
   in simulation, correlated random measurement outcomes.
2. Alice and Bob each independently choose from three measurement bases
   (0, pi/8, pi/4 relative angles).
3. Sifting keeps only positions with matching bases; the subset measured in
   the *non*-parallel bases forms CHSH/Bell test groups instead of key.
4. Bell violation (|S| > 2) is the security check: violation certifies no
   eavesdropper; E_error over the parallel-basis subset quantifies noise.
5. QBER estimate, error correction, and privacy amplification follow the
   shared PM post-processing.

Implement :func:`run_e91` returning a result dataclass whose post-sifting
field names match :class:`app.protocols.bb84.BB84Result` so the simulate API
persists, streams, and renders it unchanged.
"""

from __future__ import annotations


def run_e91(*args, **kwargs):  # noqa: ANN002, ANN003 — signature lands with the implementation
    """Run one full E91 exchange. Not implemented yet."""
    raise NotImplementedError(
        "E91 is not implemented yet — see the module docstring for the "
        "planned pipeline."
    )
