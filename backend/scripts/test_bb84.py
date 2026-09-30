"""Run the full BB84 pipeline 20 times with no eavesdropper.

Usage:  python scripts/test_bb84.py [--noise 0.02]

With no --noise argument the channel is ideal (0% noise). A small non-zero
value (e.g. 0.02 = 2%) should produce a small non-zero QBER without any
aborts — realistic channels are never perfectly clean.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.protocols.bb84 import QBER_ABORT_THRESHOLD, run_bb84

N_RUNS = 20
NOISE = 0.0
if "--noise" in sys.argv:
    NOISE = float(sys.argv[sys.argv.index("--noise") + 1])


def main() -> None:
    noise_label = f" | channel noise {NOISE:.1%}" if NOISE > 0 else " | ideal channel"
    print(f"BB84 no-eavesdropper simulation — {N_RUNS} runs, 256 qubits each{noise_label}")
    print(f"QBER sample: 15% of sifted key | abort threshold: {QBER_ABORT_THRESHOLD:.2f}")
    print("-" * 88)
    header = (
        f"{'run':>4} {'sifted':>7} {'sample':>7} {'errs':>5} "
        f"{'QBER':>8} {'EC fix':>7} {'final':>6} {'match':>6} {'abort':>6}"
    )
    print(header)
    print("-" * 88)

    aborted = 0
    mismatches = 0
    qbers: list[float] = []

    for run in range(1, N_RUNS + 1):
        res = run_bb84(n_qubits=256, seed=run, noise=NOISE)

        match = "n/a" if res.aborted else str(res.final_key_alice == res.final_key_bob)

        if res.aborted:
            aborted += 1
            print(
                f"{run:>4} {len(res.sifted_alice):>7} {len(res.sample_indices):>7} "
                f"{res.sample_errors:>5} {res.qber:>7.3f} {'-':>7} {'-':>6} "
                f"{match:>6} {'YES':>6}"
            )
            print(f"     reason: {res.abort_reason}")
            continue

        qbers.append(res.qber)
        if res.final_key_alice != res.final_key_bob:
            mismatches += 1
        print(
            f"{run:>4} {len(res.sifted_alice):>7} {len(res.sample_indices):>7} "
            f"{res.sample_errors:>5} {res.qber:>7.3f} "
            f"{len(res.corrected_positions):>7} {len(res.final_key_alice):>6} "
            f"{match:>6} {'no':>6}"
        )

    print("-" * 88)
    if qbers:
        print(
            f"QBER over {len(qbers)} completed runs: "
            f"min {min(qbers):.3f} | mean {sum(qbers) / len(qbers):.3f} | max {max(qbers):.3f}"
        )
    print(f"aborted runs: {aborted}/{N_RUNS}")
    print(f"final-key mismatches (must be 0): {mismatches}")

    # Sanity assertions — the script exits non-zero if the pipeline is broken.
    assert aborted == 0, f"unexpected aborts on an ideal channel: {aborted}"
    assert mismatches == 0, f"final keys disagree after error correction: {mismatches}"
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
