"""SARG04 prepare-and-measure QKD protocol — not implemented yet.

Planned pipeline (Scarani-Acin-Ribordy-Gisin 2004):

1. Same four states and same measurement apparatus as BB84 (attractive for
   hardware compatibility), but a different classical sifting conversation:
   Alice announces a *pair* of states containing the one she sent, and Bob
   keeps the position only when his outcome rules out one member of the pair.
2. Conclusive-outcome sifting (like B92's spirit, four-state implementation),
   targeting single-photon robustness against photon-number-splitting.
3. QBER estimate, error correction, and privacy amplification follow the
   shared PM post-processing.

Implement :func:`run_sarg04` returning a result dataclass whose post-sifting
field names match :class:`app.protocols.bb84.BB84Result` so the simulate API
persists, streams, and renders it unchanged.
"""

from __future__ import annotations


def run_sarg04(*args, **kwargs):  # noqa: ANN002, ANN003 — signature lands with the implementation
    """Run one full SARG04 exchange. Not implemented yet."""
    raise NotImplementedError(
        "SARG04 is not implemented yet — see the module docstring for the "
        "planned pipeline."
    )
