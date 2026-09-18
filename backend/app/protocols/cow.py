"""COW coherent-one-way QKD protocol — not implemented yet.

Planned pipeline (Grosshans-Grangier lineage; Scarani et al. 2004 / Gisin et al.):

1. Alice encodes bit 0 as a coherent pulse and bit 1 as a *decoy* pulse plus
   an empty slot; timing, not polarization, carries the information.
2. Bob measures with an interferometer; sifting compares detection patterns
   including empty-slot checks.
3. Security relies on coherent states' mutual information between adjacent
   pulses: the intercept-resend attack destroys inter-pulse coherence, caught
   by comparing neighboring-pulse statistics.
4. QBER estimate, error correction, and privacy amplification follow the
   shared post-processing.

Implement :func:`run_cow` returning a result dataclass whose post-sifting
field names match :class:`app.protocols.bb84.BB84Result` so the simulate API
persists, streams, and renders it unchanged.
"""

from __future__ import annotations


def run_cow(*args, **kwargs):  # noqa: ANN002, ANN003 — signature lands with the implementation
    """Run one full COW exchange. Not implemented yet."""
    raise NotImplementedError(
        "COW is not implemented yet — see the module docstring for the "
        "planned pipeline."
    )
