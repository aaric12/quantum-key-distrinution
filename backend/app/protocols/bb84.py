"""BB84 prepare-and-measure QKD protocol — full pipeline, ideal-channel sim.

Pipeline (every stage is returned in :class:`BB84Result`):

1. Alice draws random bits + random bases (Z=0 / X=1) and encodes qubits.
2. Channel hook — a no-op pass-through for now; Step-8 attacks plug in here.
   An optional ``noise`` bit-flip knob exists purely to exercise the QBER and
   abort machinery in tests.
3. Bob picks independent random bases and measures. Born-rule equivalence:
   same basis -> deterministic bit; different basis -> fair coin flip.
4. Sifting: keep only positions where Alice's and Bob's bases match.
5. QBER: a random ~15% sample of the sifted key is revealed over the public
   channel, compared, and then discarded from the remaining key.
6. Abort if QBER > 0.11 (11% BB84 security threshold).
7. Simplified error correction: block parity checks with binary-search
   localization (a one-pass Cascade stand-in). Every parity bit Alice reveals
   is tracked as public leakage and paid back during amplification. Extra
   permutation passes run only while the previous pass found errors.
8. Privacy amplification: SHA-256 based universal-hash compression of the
   corrected key (minus the parity bits revealed in step 7).

Only stdlib + numpy are used; qubits are simulated, not physically modelled.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

# Basis labels
Z = 0  # computational basis
X = 1  # Hadamard basis

# Security parameters
QBER_SAMPLE_FRACTION = 0.15  # fraction of sifted key revealed to estimate QBER
QBER_ABORT_THRESHOLD = 0.11  # abort above 11% (BB84 intercept-resend sits at 25%)
ERROR_CORRECTION_BLOCK_SIZE = 8  # bits per parity block in the simplified EC
ERROR_CORRECTION_MAX_PASSES = 12  # permutation passes while errors keep appearing
# Alice and Bob publicly compare a short hash of their corrected keys (real
# implementations do this before amplification). The comparison leaks these
# many bits about the corrected key and is charged to the PA budget.
KEY_CONFIRM_HASH_BITS = 32

# Sentinel for a pulse lost/suppressed in the quantum channel (PNS attack).
# A LOST entry never produces a sifted position: Bob detects nothing there.
LOST = -1

Rng = np.random.Generator


@dataclass
class BB84Result:
    """Every intermediate stage of one BB84 run."""

    alice_bits: list[int]
    alice_bases: list[int]
    bob_bases: list[int]
    bob_bits: list[int]
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
    attack_type: str | None = None
    attack_intensity: float = 0.0
    attack_stats: dict | None = None
    abort_reason: str | None = None
    notes: list[str] = field(default_factory=list)


def channel(qubits: Sequence[tuple[int, int]], rng: Rng, noise: float = 0.0) -> list[tuple[int, int]]:
    """Pass-through channel hook for Step-8 attacks.

    Parameters
    ----------
    qubits:
        Encoded (basis, bit) pairs as they leave Alice's lab.
    rng:
        Shared randomness source (attacks may be stochastic).
    noise:
        Optional per-qubit bit-flip probability. 0.0 = ideal channel, i.e. a
        pure no-op. Exists so the QBER/abort machinery can be exercised
        without an eavesdropper.

    Returns
    -------
    The qubits arriving at Bob.
    """
    if noise <= 0.0:
        return list(qubits)
    flipped = rng.random(len(qubits)) < noise
    return [
        (basis, bit ^ 1) if flip else (basis, bit)
        for (basis, bit), flip in zip(qubits, flipped)
    ]


def encode_qubits(alice_bits: Sequence[int], alice_bases: Sequence[int]) -> list[tuple[int, int]]:
    """Alice's preparation: (basis, bit) pairs describing each qubit state."""
    return list(zip(alice_bases, alice_bits))


def measure_qubits(
    qubits: Sequence[tuple[int, int]], bob_bases: Sequence[int], rng: Rng
) -> list[int]:
    """Bob's measurement in his independently chosen bases.

    Same basis as preparation -> the encoded bit, deterministically.
    Wrong basis -> the state is destroyed and a fair coin is observed.
    A LOST pulse produces no detection (vacuum): recorded as -1 and dropped
    from sifting.
    """
    bob_bits: list[int] = []
    for (prep_basis, bit), meas_basis in zip(qubits, bob_bases):
        if prep_basis == LOST:  # vacuum pulse: no photon, no detection
            bob_bits.append(-1)
        elif meas_basis == prep_basis:
            bob_bits.append(int(bit))
        else:
            bob_bits.append(int(rng.integers(2)))
    return bob_bits


def sift(
    alice_bases: Sequence[int],
    bob_bases: Sequence[int],
    alice_bits: Sequence[int],
    bob_bits: Sequence[int],
) -> tuple[list[int], list[int]]:
    """Keep only positions where Alice and Bob happened to use the same basis
    *and* Bob actually detected a pulse (not LOST)."""
    sifted_alice: list[int] = []
    sifted_bob: list[int] = []
    for a_b, b_b, a_bit, b_bit in zip(alice_bases, bob_bases, alice_bits, bob_bits):
        if a_b == b_b and b_bit != -1:
            sifted_alice.append(int(a_bit))
            sifted_bob.append(int(b_bit))
    return sifted_alice, sifted_bob


def estimate_qber(
    sifted_alice: Sequence[int],
    sifted_bob: Sequence[int],
    rng: Rng,
    fraction: float = QBER_SAMPLE_FRACTION,
) -> tuple[float, list[int], list[int], list[int], int]:
    """Reveal a random ~15% sample of the sifted key to estimate the QBER.

    Returns ``(qber, sample_indices, sample_alice, sample_bob, n_errors)``.
    The caller discards the revealed positions from the key afterwards.
    """
    n = len(sifted_alice)
    if n == 0:
        return 0.0, [], [], [], 0

    sample_size = max(1, int(round(n * fraction)))
    indices = sorted(rng.choice(n, size=sample_size, replace=False).tolist())

    sample_alice = [int(sifted_alice[i]) for i in indices]
    sample_bob = [int(sifted_bob[i]) for i in indices]
    errors = sum(1 for a, b in zip(sample_alice, sample_bob) if a != b)
    qber = errors / sample_size
    return qber, indices, sample_alice, sample_bob, errors


def _parity(bits: list[int], lo: int, hi: int) -> int:
    """XOR-parity of bits[lo:hi]."""
    return sum(bits[lo:hi]) & 1


def _perm(n: int, salt: int) -> list[int]:
    """Deterministic pseudo-random bijection of range(n) (Fisher-Yates over a
    SHA-256 keystream). Cascade re-parallels the key every pass; a fixed
    keystream keeps runs reproducible without plumbing an rng through."""
    idx = list(range(n))
    counter = 0
    for i in range(n - 1, 0, -1):
        digest = hashlib.sha256(salt.to_bytes(4, "big") + counter.to_bytes(4, "big")).digest()
        j = int.from_bytes(digest, "big") % (i + 1)
        idx[i], idx[j] = idx[j], idx[i]
        counter += 1
    return idx


def _key_hash(bits: Sequence[int]) -> int:
    """Short public confirmation hash of a candidate key (KEY_CONFIRM_HASH_BITS)."""
    digest = hashlib.sha256("".join(str(b) for b in bits).encode()).digest()
    return int.from_bytes(digest[: KEY_CONFIRM_HASH_BITS // 8], "big")


def _ec_pass(
    a: list[int], b: list[int], perm: list[int], block_size: int, leaks: int,
    corrected: list[int],
) -> tuple[int, int]:
    """One parity-check pass over a permuted alignment. Returns (leaks, fixes)."""
    n = len(perm)
    pa = [a[p] for p in perm]  # reference, never modified
    pb = [b[p] for p in perm]
    fixes = 0
    for start in range(0, n - block_size + 1, block_size):
        lo, hi = start, start + block_size
        leaks += 1  # block parity bit is public
        if _parity(pa, lo, hi) != _parity(pb, lo, hi):
            # Odd errors in this block: bisect until one is localized.
            while hi - lo > 1:
                mid = (lo + hi) // 2
                leaks += 1  # each bisection reveals one parity bit
                if _parity(pa, lo, mid) != _parity(pb, lo, mid):
                    hi = mid
                else:
                    lo = mid
            pb[lo] ^= 1  # single-bit window + parity mismatch = wrong bit
            corrected.append(perm[lo])
            fixes += 1
    for i in range(n):
        b[perm[i]] = pb[i]
    return leaks, fixes


def parity_error_correct(
    alice: Sequence[int],
    bob: Sequence[int],
    block_size: int = ERROR_CORRECTION_BLOCK_SIZE,
    max_passes: int = ERROR_CORRECTION_MAX_PASSES,
) -> tuple[list[int], list[int], int, list[int], bool]:
    """Simplified error correction: block parity + binary-search repair.

    For each block of ``block_size`` bits, Alice reveals one parity bit. A
    mismatch means the block holds an odd number of errors; Alice and Bob
    then bisect the block, revealing one parity bit per bisection, until the
    erroneous bit is pinned down and Bob flips it — a one-block slice of the
    classic Cascade protocol. Passes over re-permuted alignments repeat while
    errors keep appearing (even-count errors hide from parity until a
    permutation isolates them).

    Convergence is confirmed the way real implementations do it pre-
    amplification: Alice and Bob publicly compare a short hash of their
    corrected keys (``KEY_CONFIRM_HASH_BITS``); on mismatch another pass
    runs. The comparison is charged as public leakage to the PA budget.

    Returns ``(alice_corrected, bob_corrected, parity_bits_revealed,
    corrected_positions, confirmed)``. Alice's key is never modified.
    """
    n = len(bob)
    if n == 0:
        return list(alice), [], 0, [], True

    a = list(alice)
    b = list(bob)
    leaks = 0
    corrected: list[int] = []
    passes = 0

    for pass_no in range(max_passes):
        passes += 1
        perm = list(range(n)) if pass_no == 0 else _perm(n, 0xA11CE + pass_no)
        leaks, fixes = _ec_pass(a, b, perm, block_size, leaks, corrected)
        if fixes == 0:
            break

    # Public key confirmation; extra passes until the hashes agree.
    confirmed = _key_hash(a) == _key_hash(b)
    while not confirmed and passes < max_passes + 6:
        passes += 1
        perm = _perm(n, 0xB0B00 + passes)
        leaks, _ = _ec_pass(a, b, perm, block_size, leaks, corrected)
        confirmed = _key_hash(a) == _key_hash(b)

    return a, b, leaks, sorted(corrected), confirmed


def privacy_amplify(
    key: Sequence[int], leak_bits: int, target_fraction: float = 0.5
) -> list[int]:
    """Hash-based privacy amplification (privacy two-universal-hash stand-in).

    The remaining key is SHA-256 hashed (seeded by its own content, fine for
    simulation) and compressed to ``target_fraction`` of its length, never
    exceeding ``len(key) - leak_bits`` so every bit publicly revealed during
    sifting-adjacent steps (error-correction parities, key-confirmation
    hash) is paid back with headroom.
    """
    if not key:
        return []
    n_target = max(1, min(int(len(key) * target_fraction), len(key) - leak_bits))
    n_target = min(n_target, 256)  # SHA-256 output bound

    bits = "".join(str(b) for b in key)
    out: list[int] = []
    counter = 0
    while len(out) < n_target:
        digest = hashlib.sha256(f"{bits}:{counter}".encode()).digest()
        byte_int = int.from_bytes(digest, "big")
        out.extend((byte_int >> shift) & 1 for shift in range(255, -1, -1))
        counter += 1
    return out[:n_target]


def run_bb84(
    n_qubits: int = 256,
    seed: int | None = None,
    noise: float = 0.0,
    channel_hook: Callable[..., list] | None = None,
    attack_type: str | None = None,
    attack_intensity: float = 0.0,
) -> BB84Result:
    """Run one full BB84 exchange and return every intermediate stage."""
    if n_qubits < 16:
        raise ValueError("n_qubits must be >= 16 for a meaningful simulation")
    rng: Rng = np.random.default_rng(seed)

    # 1. Alice: random bits + random bases, encoded into qubits
    alice_bits = rng.integers(2, size=n_qubits).tolist()
    alice_bases = rng.integers(2, size=n_qubits).tolist()
    qubits = encode_qubits(alice_bits, alice_bases)

    # 2. Channel hook (no-op pass-through on the ideal channel). Attacks may
    # return (qubits, stats); unpack stats when present.
    hook = channel_hook if channel_hook is not None else (lambda q, r: channel(q, r, noise=noise))
    hook_out = hook(qubits, rng)
    if isinstance(hook_out, tuple):
        received, attack_stats = hook_out
    else:
        received, attack_stats = hook_out, None

    # 3. Bob: independent random bases, measures accordingly
    bob_bases = rng.integers(2, size=n_qubits).tolist()
    bob_bits = measure_qubits(received, bob_bases, rng)

    # 4. Sifting — mandatory
    sifted_alice, sifted_bob = sift(alice_bases, bob_bases, alice_bits, bob_bits)
    notes: list[str] = []
    if attack_stats is not None:
        notes.append(
            f"attack '{attack_type}' (intensity {attack_intensity:.2f}): "
            f"{len(received) - sum(1 for q in received if q[0] != LOST)} qubit(s) suppressed"
        )

    # 5. QBER from a revealed ~15% sample (sample then discarded)
    qber, sample_indices, sample_alice, sample_bob, n_errors = estimate_qber(
        sifted_alice, sifted_bob, rng
    )
    sample_set = set(sample_indices)
    remaining_alice = [b for i, b in enumerate(sifted_alice) if i not in sample_set]
    remaining_bob = [b for i, b in enumerate(sifted_bob) if i not in sample_set]

    # 6. Abort decision
    if qber > QBER_ABORT_THRESHOLD:
        return BB84Result(
            alice_bits=alice_bits,
            alice_bases=alice_bases,
            bob_bases=bob_bases,
            bob_bits=bob_bits,
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
            attack_type=attack_type,
            attack_intensity=attack_intensity,
            attack_stats=attack_stats,
            abort_reason=(
                f"QBER {qber:.3f} exceeds security threshold "
                f"{QBER_ABORT_THRESHOLD:.2f} — channel assumed compromised, key discarded"
            ),
            notes=notes,
        )

    # 7. Simplified error correction on the remaining bits
    corrected_alice, corrected_bob, parity_leak, corrected_positions, confirmed = (
        parity_error_correct(remaining_alice, remaining_bob)
    )
    parity_leak += KEY_CONFIRM_HASH_BITS  # public confirmation comparison
    if corrected_positions:
        notes.append(f"error correction fixed {len(corrected_positions)} bit(s)")

    if not confirmed:
        # EC could not make the keys agree publicly-verifyably: no key material
        # is safe to keep. Same policy as a real link: abort, keep nothing.
        return BB84Result(
            alice_bits=alice_bits,
            alice_bases=alice_bases,
            bob_bases=bob_bases,
            bob_bits=bob_bits,
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
            attack_type=attack_type,
            attack_intensity=attack_intensity,
            attack_stats=attack_stats,
            abort_reason=(
                "error correction failed to converge — public key confirmation "
                "hash mismatch, corrected keys discarded"
            ),
            notes=notes,
        )

    # 8. Privacy amplification: compress, paying back the parity + confirm leak
    final_key_alice = privacy_amplify(corrected_alice, leak_bits=parity_leak)
    final_key_bob = privacy_amplify(corrected_bob, leak_bits=parity_leak)

    return BB84Result(
        alice_bits=alice_bits,
        alice_bases=alice_bases,
        bob_bases=bob_bases,
        bob_bits=bob_bits,
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
        attack_type=attack_type,
        attack_intensity=attack_intensity,
        attack_stats=attack_stats,
        abort_reason=None,
        notes=notes,
    )
