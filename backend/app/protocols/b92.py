"""B92 prepare-and-measure QKD protocol — 2-state pipeline, ideal-channel sim.

B92 (Bennett 1992) compresses BB84's four states down to two **non-orthogonal**
ones and replaces basis-matching sifting with *conclusive-outcome* sifting:

1. Alice encodes each random bit into one of two states:

       bit 0 -> |0>   (Z basis)
       bit 1 -> |+>   (X basis)

2. Channel hook — a no-op pass-through for now; attacks plug in here. The
   ``noise`` knob applies a per-qubit bit flip (|0> -> |1>, |+> -> |->) to
   exercise the QBER/abort machinery without an eavesdropper.
3. Bob picks a random measurement basis (Z or X) per qubit. Unlike BB84 there
   is no basis comparison afterwards: Bob keeps a position only when his
   outcome is impossible for one of the two signal states:

       basis Z, outcome |1>  -> Alice cannot have sent |0>  -> bit was 1
       basis X, outcome |->  -> Alice cannot have sent |+>  -> bit was 0

   Every other outcome is inconclusive (both states can produce it) and is
   discarded. Each signal state yields a conclusive result only in the other
   basis and only half the time there, so the expected sifted fraction is
   25% of transmitted qubits (vs BB84's 50%).
4. Sifting — the conclusive-outcome rule above, which is *not* BB84's
   basis-matching rule.
5. QBER from a revealed ~15% sample of the sifted key; the sample is then
   discarded from the key material.
6. Abort if QBER > 0.11 (the standard PM-QKD security threshold).
7. Error correction — after sifting, the bit-level problem is identical to
   BB84's, so the generic block-parity corrector from :mod:`bb84` is reused.
   Sifting is the only protocol-specific step reimplemented here.
8. Privacy amplification — the same SHA-256 hash compression as BB84, charged
   for the parity + confirmation bits revealed in step 7.

Only stdlib + numpy are used; qubits are simulated, not physically modelled.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

from app.protocols.bb84 import (
    KEY_CONFIRM_HASH_BITS,
    QBER_ABORT_THRESHOLD,
    Rng,
    channel,
    estimate_qber,
    parity_error_correct,
    privacy_amplify,
)

Z = 0  # computational basis (|0>, |1>)
X = 1  # Hadamard basis (|+>, |->)


@dataclass
class B92Result:
    """Every intermediate stage of one B92 run.

    Field names after ``bob_inferred`` deliberately match :class:`BB84Result`
    so the simulate API persists, streams, and renders both protocols with
    the same code paths. B92-specific stages: ``alice_states`` (which of the
    two non-orthogonal states was sent), ``bob_outcomes`` (raw 0/1 outcome
    per qubit) and ``bob_inferred`` (the conclusive bit, or None).
    """

    alice_bits: list[int]
    alice_states: list[int]  # prepared state per qubit: 0 -> |0>, 1 -> |+>
    bob_bases: list[int]
    bob_outcomes: list[int]
    bob_inferred: list[int | None]
    sifted_alice: list[int]
    sifted_bob: list[int]
    sample_indices: list[int]
    sample_alice: list[int]
    sample_bob: list[int]
    sample_errors: int
    qber: float
    remaining_alice: list[int]
    remaining_bob: list[int]
    parity_bits_revealed: int
    corrected_positions: list[int]
    corrected_alice: list[int]
    corrected_bob: list[int]
    final_key_alice: list[int]
    final_key_bob: list[int]
    aborted: bool
    abort_reason: str | None = None
    notes: list[str] = field(default_factory=list)


def encode_b92(alice_bits: Sequence[int]) -> list[tuple[int, int]]:
    """Alice's preparation: bit 0 -> |0> (Z), bit 1 -> |+> (X).

    States are (basis, eigenvalue) pairs; both signal states carry eigenvalue
    0 in their own basis — the states differ only in *basis*, and are
    non-orthogonal by construction (⟨0|+⟩ = 1/√2 ≠ 0).
    """
    return [(Z if bit == 0 else X, 0) for bit in alice_bits]


def measure_b92(
    qubits: Sequence[tuple[int, int]], bob_bases: Sequence[int], rng: Rng
) -> list[int]:
    """Bob's raw measurement outcomes in his independently chosen bases.

    Ordinary projective measurement: a state measured in its own basis gives
    its eigenvalue deterministically; in the conjugate basis the outcome is a
    fair coin. Conclusiveness is decided later, in :func:`sift_conclusive`.
    """
    outcomes: list[int] = []
    for (prep_basis, eigenvalue), meas_basis in zip(qubits, bob_bases):
        if meas_basis == prep_basis:
            outcomes.append(int(eigenvalue))
        else:
            outcomes.append(int(rng.integers(2)))
    return outcomes


def sift_conclusive(
    alice_bits: Sequence[int],
    bob_bases: Sequence[int],
    bob_outcomes: Sequence[int],
) -> tuple[list[int], list[int]]:
    """B92 sifting: keep only conclusive outcomes — not BB84's basis matching.

    A position is conclusive when Bob's outcome is orthogonal to one of the
    two signal states, ruling that state out:

        basis Z, outcome 1 (|1>)  -> |0> excluded -> Alice sent |+> -> bit 1
        basis X, outcome 1 (|->)  -> |+> excluded -> Alice sent |0> -> bit 0

    Outcome 0 is always inconclusive (either signal state can produce it in
    either basis) and is dropped. Bob's inferred bit is therefore
    ``1 - basis`` for every conclusive position.
    """
    sifted_alice: list[int] = []
    sifted_bob: list[int] = []
    for a_bit, basis, outcome in zip(alice_bits, bob_bases, bob_outcomes):
        if outcome != 1:
            continue  # inconclusive: both signal states could have produced it
        sifted_alice.append(int(a_bit))
        sifted_bob.append(1 - int(basis))
    return sifted_alice, sifted_bob


def run_b92(
    n_qubits: int = 256,
    seed: int | None = None,
    noise: float = 0.0,
    channel_hook: Callable[[list[tuple[int, int]], Rng], list[tuple[int, int]]] | None = None,
) -> B92Result:
    """Run one full B92 exchange and return every intermediate stage."""
    if n_qubits < 16:
        raise ValueError("n_qubits must be >= 16 for a meaningful simulation")
    rng: Rng = np.random.default_rng(seed)

    # 1. Alice: random bits -> two non-orthogonal states
    alice_bits = rng.integers(2, size=n_qubits).tolist()
    alice_states = [Z if bit == 0 else X for bit in alice_bits]
    qubits = encode_b92(alice_bits)

    # 2. Channel hook (no-op pass-through on the ideal channel)
    hook = channel_hook if channel_hook is not None else (lambda q, r: channel(q, r, noise=noise))
    received = hook(qubits, rng)

    # 3. Bob: independent random bases; mark conclusive vs inconclusive
    bob_bases = rng.integers(2, size=n_qubits).tolist()
    bob_outcomes = measure_b92(received, bob_bases, rng)
    bob_inferred = [
        1 - basis if outcome == 1 else None
        for basis, outcome in zip(bob_bases, bob_outcomes)
    ]

    # 4. Sifting — B92 conclusive-outcome rule (not basis matching)
    sifted_alice, sifted_bob = sift_conclusive(alice_bits, bob_bases, bob_outcomes)
    notes: list[str] = []

    # 5. QBER from a revealed ~15% sample (sample then discarded)
    qber, sample_indices, sample_alice, sample_bob, n_errors = estimate_qber(
        sifted_alice, sifted_bob, rng
    )
    sample_set = set(sample_indices)
    remaining_alice = [b for i, b in enumerate(sifted_alice) if i not in sample_set]
    remaining_bob = [b for i, b in enumerate(sifted_bob) if i not in sample_set]

    # 6. Abort decision
    if qber > QBER_ABORT_THRESHOLD:
        return B92Result(
            alice_bits=alice_bits,
            alice_states=alice_states,
            bob_bases=bob_bases,
            bob_outcomes=bob_outcomes,
            bob_inferred=bob_inferred,
            sifted_alice=sifted_alice,
            sifted_bob=sifted_bob,
            sample_indices=sample_indices,
            sample_alice=sample_alice,
            sample_bob=sample_bob,
            sample_errors=n_errors,
            qber=qber,
            remaining_alice=remaining_alice,
            remaining_bob=remaining_bob,
            parity_bits_revealed=0,
            corrected_positions=[],
            corrected_alice=[],
            corrected_bob=[],
            final_key_alice=[],
            final_key_bob=[],
            aborted=True,
            abort_reason=(
                f"QBER {qber:.3f} exceeds security threshold "
                f"{QBER_ABORT_THRESHOLD:.2f} — channel assumed compromised, key discarded"
            ),
            notes=notes,
        )

    # 7-8. Shared post-processing: parity EC (with public key confirmation),
    # then hash-based privacy amplification paying back the public leakage.
    corrected_alice, corrected_bob, parity_leak, corrected_positions, confirmed = (
        parity_error_correct(remaining_alice, remaining_bob)
    )
    parity_leak += KEY_CONFIRM_HASH_BITS
    if corrected_positions:
        notes.append(f"error correction fixed {len(corrected_positions)} bit(s)")

    if not confirmed:
        return B92Result(
            alice_bits=alice_bits,
            alice_states=alice_states,
            bob_bases=bob_bases,
            bob_outcomes=bob_outcomes,
            bob_inferred=bob_inferred,
            sifted_alice=sifted_alice,
            sifted_bob=sifted_bob,
            sample_indices=sample_indices,
            sample_alice=sample_alice,
            sample_bob=sample_bob,
            sample_errors=n_errors,
            qber=qber,
            remaining_alice=remaining_alice,
            remaining_bob=remaining_bob,
            parity_bits_revealed=parity_leak,
            corrected_positions=corrected_positions,
            corrected_alice=corrected_alice,
            corrected_bob=corrected_bob,
            final_key_alice=[],
            final_key_bob=[],
            aborted=True,
            abort_reason=(
                "error correction failed to converge — public key confirmation "
                "hash mismatch, corrected keys discarded"
            ),
            notes=notes,
        )

    final_key_alice = privacy_amplify(corrected_alice, leak_bits=parity_leak)
    final_key_bob = privacy_amplify(corrected_bob, leak_bits=parity_leak)

    return B92Result(
        alice_bits=alice_bits,
        alice_states=alice_states,
        bob_bases=bob_bases,
        bob_outcomes=bob_outcomes,
        bob_inferred=bob_inferred,
        sifted_alice=sifted_alice,
        sifted_bob=sifted_bob,
        sample_indices=sample_indices,
        sample_alice=sample_alice,
        sample_bob=sample_bob,
        sample_errors=n_errors,
        qber=qber,
        remaining_alice=remaining_alice,
        remaining_bob=remaining_bob,
        parity_bits_revealed=parity_leak,
        corrected_positions=corrected_positions,
        corrected_alice=corrected_alice,
        corrected_bob=corrected_bob,
        final_key_alice=final_key_alice,
        final_key_bob=final_key_bob,
        aborted=False,
        abort_reason=None,
        notes=notes,
    )
