"""Attack simulations that hook into prepare-and-measure QKD channels.

Every attack is a *channel hook*: a callable with the signature

    hook(qubits, rng) -> qubits

matching :func:`app.protocols.bb84.channel`, so a run can swap an ideal wire
for a compromised one without touching the protocol pipelines. Use
:func:`make_hook` in the simulate endpoints to build one from an
``attack_type``/``attack_intensity`` pair.
"""

from __future__ import annotations

from app.attacks.intercept_resend import intercept_resend
from app.attacks.pns import photon_number_splitting
from app.attacks.trojan import trojan_channel

#: Registered attack hooks: slug -> (callable, intensity parameter meaning).
ATTACKS: dict[str, tuple] = {
    # intercept-resend: intensity = fraction of qubits Eve intercepts
    "intercept_resend": (intercept_resend, "fraction of qubits Eve intercepts"),
    # PNS: intensity = fraction of signals split off (siphoned) by Eve;
    # pulses she siphons are suppressed (lost) so Bob never detects them.
    "pns": (photon_number_splitting, "fraction of signals Eve siphons + suppresses"),
    # Trojan: intensity = strength of the back-door coupling at Alice's setup
    "trojan": (trojan_channel, "back-door coupling strength at Alice's encoder"),
}


def make_hook(attack_type: str | None, intensity: float):
    """Build a channel hook for the given attack, or None for an ideal wire.

    ``attack_type=None`` (or "none") yields None, which protocols interpret as
    the ideal pass-through channel. Unknown slugs raise ValueError.
    """
    if attack_type in (None, "", "none"):
        return None

    if attack_type not in ATTACKS:
        raise ValueError(
            f"Unknown attack '{attack_type}'. Available: {sorted(ATTACKS)}"
        )
    if not 0.0 <= intensity <= 1.0:
        raise ValueError("attack_intensity must be within [0, 1]")

    fn, _ = ATTACKS[attack_type]
    if intensity == 0.0:
        return None  # zero-strength attack degenerates to an ideal channel

    def hook(qubits, rng):
        return fn(qubits, rng, intensity)

    return hook
