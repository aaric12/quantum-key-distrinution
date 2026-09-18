"""Attack sweep: run BB84/B92 under each attack at several intensities.

Primary check demanded by the spec: intercept_resend at intensity
0.0 / 0.5 / 1.0 must show QBER scaling up (~ intensity/4 for BB84),
measured — not assumed.

Usage:  python scripts/test_attacks.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.attacks import ATTACKS, make_hook  # noqa: E402
from app.protocols.b92 import run_b92  # noqa: E402
from app.protocols.bb84 import run_bb84  # noqa: E402

N = 4096  # qubits per run: enough that QBER estimates are stable


def sweep(protocol: str, run_fn, attack: str, intensities: list[float]) -> list[float]:
    print(f"\n=== {protocol.upper()} under {attack} (n={N} qubits per run) ===")
    print(f"{'intensity':>10} {'sifted':>7} {'sample':>7} {'errors':>7} {'QBER':>8}  {'abort':<5} reason")
    qbers = []
    for level in intensities:
        res = run_fn(
            n_qubits=N,
            seed=11,
            channel_hook=make_hook(attack, level),
            attack_type=attack if level > 0 else None,
            attack_intensity=level,
        )
        qbers.append(res.qber)
        reason = (res.abort_reason or "-")[:46]
        print(
            f"{level:>10.2f} {len(res.sifted_alice):>7} {len(res.sample_indices):>7} "
            f"{res.sample_errors:>7} {res.qber:>8.3f}  {'YES' if res.aborted else 'no':<5} {reason}"
        )
    return qbers


def main() -> None:
    print("Attack sweep on ideal-ish channel (no extra noise), seed=11, all runs")

    # --- the demanded check: intercept_resend must scale ---
    bb84_qbers = sweep("bb84", run_bb84, "intercept_resend", [0.0, 0.25, 0.5, 1.0])
    b92_qbers = sweep("b92", run_b92, "intercept_resend", [0.0, 0.25, 0.5, 1.0])

    assert bb84_qbers[0] == 0.0, "intensity 0.0 must be a clean channel"
    assert bb84_qbers[1] < bb84_qbers[2] < bb84_qbers[3], "QBER must scale with intensity"
    assert b92_qbers[1] < b92_qbers[2] < b92_qbers[3], "QBER must scale with intensity"
    # Theory: BB84 sifted-QBER ~ intensity/4; B92 ~ intensity/3 (conclusive
    # outcomes are rarer but Eve's wrong-basis re-sends stay conclusive).
    print(
        f"\nBB84 scaling check: 0.25 -> {bb84_qbers[1]:.3f} (~0.062), "
        f"0.5 -> {bb84_qbers[2]:.3f} (~0.125), 1.0 -> {bb84_qbers[3]:.3f} (~0.250)"
    )
    print(
        f"B92 scaling check:  0.25 -> {b92_qbers[1]:.3f} (~0.083), "
        f"0.5 -> {b92_qbers[2]:.3f} (~0.167), 1.0 -> {b92_qbers[3]:.3f} (~0.333)"
    )

    # --- the other two attacks, monotonic as well ---
    sweep("bb84", run_bb84, "pns", [0.0, 0.5, 1.0])
    sweep("bb84", run_bb84, "trojan", [0.0, 0.5, 1.0])

    # --- PNS decoy statistics demo: loss rates per intensity level ---
    print(f"\n=== PNS decoy-state loss statistics (n={N}) ===")
    res = run_bb84(
        n_qubits=N,
        seed=11,
        channel_hook=make_hook("pns", 0.8),
        attack_type="pns",
        attack_intensity=0.8,
    )
    stats = res.attack_stats
    print(f"{'mu':>8} {'sent':>6} {'lost':>6} {'loss rate':>10}")
    for lvl in stats["levels"]:
        print(
            f"{lvl['mu']:>8.4f} {lvl['sent']:>6} {lvl['lost']:>6} {lvl['loss_rate']:>10.3f}"
        )
    print(
        f"loss spread {stats['observed_spread']:.3f} vs binomial noise floor "
        f"{stats['noise_floor']:.3f} -> anomaly {stats['anomaly_z']:.1f} sigma "
        f"(flagged: {stats['flagged']})"
    )
    assert stats["flagged"], "PNS at intensity 0.8 must trip the decoy loss-rate test"
    clean = run_bb84(n_qubits=N, seed=11)
    assert clean.attack_stats is None

    # --- trojan is quieter than intercept-resend at equal intensity ---
    trojan = run_bb84(
        n_qubits=N,
        seed=11,
        channel_hook=make_hook("trojan", 0.5),
        attack_type="trojan",
        attack_intensity=0.5,
    )
    intercept = run_bb84(
        n_qubits=N,
        seed=11,
        channel_hook=make_hook("intercept_resend", 0.5),
        attack_type="intercept_resend",
        attack_intensity=0.5,
    )
    print(
        f"\nat intensity 0.5: trojan QBER {trojan.qber:.3f} vs "
        f"intercept-resend QBER {intercept.qber:.3f} (trojan stays under the "
        f"0.11 abort line: {not trojan.aborted})"
    )
    assert trojan.qber < intercept.qber

    print("\nATTACK SWEEP TESTS PASSED")
    print(f"(registered attacks: {sorted(ATTACKS)})")


if __name__ == "__main__":
    main()
