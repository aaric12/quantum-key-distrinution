"""Real-hardware execution of the BB84/B92 circuits on IBM Quantum.

Token-handling contract (read before touching anything here):

- The IBM Quantum API token arrives in the POST /simulate/hardware request
  body and is used for exactly one thing: constructing a
  ``QiskitRuntimeService`` inside :func:`submit_and_run`.
- The token is NEVER written to the database, NEVER logged, and NEVER
  echoed in any response. ``HardwareJob`` has no token column by design.
- The token is held in exactly one in-memory location while in use: the
  local ``token`` binding inside :func:`submit_and_run` (the request-scoped
  frame). The runtime service object derived from it is also stored in the
  in-memory :data:`_services` broker so the background poller can keep the
  session alive; when the job reaches a terminal state the poller pops that
  entry and drops its own reference, letting the service (and the
  credential inside it) be garbage collected.
- Restarting the backend orphans any in-flight IBM jobs (accepted
  trade-off: the job id is public and the result row is kept, but
  re-attaching to a live job would require the user to re-submit a token).

Circuit design: BB84/B92 sifting is *classical* post-selection, so the
quantum part per shot is just Alice's state prep + Bob's measurement in a
random basis. We submit one n-qubit circuit with the (basis, outcome)
record in a classical register and ``shots`` repetitions; the classical
sifting rules are replayed on the returned per-shot registers, using the
exact Alice/Bob bit/basis draws from submission (deterministically seeded
by the HardwareJob row id — see ``_rng_for``).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.models import HardwareJob, SessionLocal

# Hard caps for real-hardware runs (device constraints + abuse limits).
MIN_QUBITS = 20
MAX_QUBITS = 50
MAX_SHOTS = 4096


@dataclass
class _HardwareJobState:
    """In-memory state attached to one hardware job (no token inside)."""

    job_id: str
    user_id: int
    status: str = "queued"
    backend: str | None = None
    result: dict | None = None
    error: str | None = None
    subscribers: list = field(default_factory=list)  # asyncio.Queue per WS client


# Module-level in-memory broker. Holds no credentials — only job handles,
# statuses, results, and live WebSocket subscriber queues.
_jobs: dict[str, _HardwareJobState] = {}
_services: dict[str, Any] = {}  # job_id -> QiskitRuntimeService (transient)
_jobs_lock = threading.Lock()


def get_job_state(job_id: str) -> _HardwareJobState | None:
    with _jobs_lock:
        return _jobs.get(job_id)


def subscribe(job_id: str, queue) -> bool:
    """Attach a WebSocket subscriber queue to a live job, if it exists."""
    with _jobs_lock:
        state = _jobs.get(job_id)
        if state is None:
            return False
        state.subscribers.append(queue)
        return True


def unsubscribe(job_id: str, queue) -> None:
    with _jobs_lock:
        state = _jobs.get(job_id)
        if state is not None and queue in state.subscribers:
            state.subscribers.remove(queue)


def _publish(state: _HardwareJobState, message: dict) -> None:
    """Fan a status update out to every live subscriber queue."""
    for q in list(state.subscribers):
        try:
            q.put_nowait(message)
        except Exception:  # noqa: BLE001 — a dead subscriber must not block others
            pass


def set_status(job_id: str, status: str, *, backend: str | None = None,
               result: dict | None = None, error: str | None = None) -> None:
    """Update the in-memory state, persist, and fan out to subscribers."""
    with _jobs_lock:
        state = _jobs.get(job_id)
        if state is None:
            return
        state.status = status
        if backend:
            state.backend = backend
        if result is not None:
            state.result = result
        if error is not None:
            state.error = error
        message = {
            "type": "status",
            "job_id": job_id,
            "status": status,
            "backend": state.backend,
            "result": state.result,
            "error": state.error,
        }
    _persist_status(job_id, status, backend=backend, result=result, error=error)
    _publish(state, message)


def _persist_status(job_id: str, status: str, *, backend=None, result=None,
                    error=None) -> None:
    """Mirror the in-memory status into the hardware_jobs table.

    Persisted fields: status, backend name, result payload, error text.
    No token or credential material ever reaches this function.
    """
    db = SessionLocal()
    try:
        job = db.query(HardwareJob).filter(HardwareJob.ibm_job_id == job_id).one_or_none()
        if job is None:
            return
        job.status = status
        if backend:
            job.backend_name = backend
        if result is not None:
            job.result_json = result
        if error is not None:
            job.error = error
        db.commit()
    finally:
        db.close()


def _rng_for(job_row_id: int) -> np.random.Generator:
    """The one RNG used both at submit time and at replay time.

    Seeded from the HardwareJob row id so the classical sifting replay sees
    exactly the Alice bits/bases and Bob bases the submitted circuit used.
    """
    return np.random.default_rng(job_row_id * 7919)


def build_bb84_circuit(alice_bits: list[int], alice_bases: list[int],
                       bob_bases: list[int]) -> Any:
    """BB84 transmission circuit: prep in Alice's basis, measure in Bob's."""
    from qiskit import QuantumCircuit

    n = len(alice_bits)
    qc = QuantumCircuit(n, n)
    for i in range(n):
        if alice_bases[i] == 1:  # X-basis prep: |+> / |-> as H·X·H chain
            qc.h(i)
            qc.x(i)
            qc.h(i)
        elif alice_bits[i] == 1:
            qc.x(i)
        if bob_bases[i] == 1:  # measure in X basis
            qc.h(i)
        qc.measure(i, i)
    return qc


def build_b92_circuit(alice_bits: list[int], bob_bases: list[int]) -> Any:
    """B92 transmission circuit: bit 0 -> |0>, bit 1 -> |+>."""
    from qiskit import QuantumCircuit

    n = len(alice_bits)
    qc = QuantumCircuit(n, n)
    for i in range(n):
        if alice_bits[i] == 1:
            qc.h(i)
        if bob_bases[i] == 1:
            qc.h(i)
        qc.measure(i, i)
    return qc


def sift_registers(protocol: str, alice_bases: list[int], bob_bases: list[int],
                   alice_bits: list[int], outcomes: list[int]) -> list[int]:
    """Classical sifting rules applied to one shot's outcome register.

    BB84: keep positions where bases match; the key bit is Bob's outcome.
    B92: keep conclusive outcomes (outcome bit == 1 means the |1>/|->
    detector fired); the key bit is 1 - Bob's basis.
    """
    if protocol == "bb84":
        return [
            int(outcomes[i])
            for i in range(len(alice_bases))
            if alice_bases[i] == bob_bases[i]
        ]
    return [
        1 - int(bob_bases[i])
        for i in range(len(bob_bases))
        if outcomes[i] == 1
    ]


def submit_and_run(job_row_id: int, protocol: str, n_qubits: int, shots: int,
                   token: str) -> str:
    """Submit the circuit to IBM and spawn the status poller.

    Called from the async endpoint via a worker thread with ONLY the
    request-scoped ``token`` binding. Steps:

    1. Construct ``QiskitRuntimeService(token=...)`` — the single use of
       the token, inside this call's frame.
    2. Build + transpile the circuit, submit via the Sampler primitive,
       store the returned IBM job id in the in-memory broker + DB row.
    3. Hand the service object to the background poller thread, which owns
       it from here on; this frame returns and the token binding goes out
       of scope immediately.
    """
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

    rng = _rng_for(job_row_id)
    alice_bits = rng.integers(2, size=n_qubits).tolist()
    alice_bases = rng.integers(2, size=n_qubits).tolist()
    bob_bases = rng.integers(2, size=n_qubits).tolist()

    if protocol == "bb84":
        qc = build_bb84_circuit(alice_bits, alice_bases, bob_bases)
    else:
        qc = build_b92_circuit(alice_bits, bob_bases)

    # 1. The single token use. This binding dies when this frame returns.
    service = QiskitRuntimeService(token=token, channel="ibm_quantum_platform")

    # 2. Pick the least-busy real backend that fits the circuit.
    backends = service.backends(
        operational=True, simulator=False, min_num_qubits=n_qubits
    )
    if not backends:
        raise RuntimeError("no operational IBM backend with enough qubits")
    backend = sorted(backends, key=lambda b: b.status().pending_jobs)[0]

    pm = generate_preset_pass_manager(optimization_level=1, backend=backend)
    isa_circuit = pm.run(qc)

    sampler = SamplerV2(mode=backend)
    job = sampler.run([isa_circuit], shots=shots)
    ibm_job_id = job.job_id()

    # Stamp the real id onto the DB row BEFORE any status can be published,
    # so _persist_status can find the row (it looks the row up by job id).
    _stamp_job_id(job_row_id, ibm_job_id)

    with _jobs_lock:
        _jobs[ibm_job_id] = _HardwareJobState(
            job_id=ibm_job_id,
            user_id=_owner_of(job_row_id),
            backend=backend.name,
        )
        _services[ibm_job_id] = service  # the poller owns it from here

    set_status(ibm_job_id, "queued", backend=backend.name)

    # 3. Background poller owns the service + job handle from here on.
    threading.Thread(
        target=_poll_ibm_job,
        args=(ibm_job_id, service, job, protocol, n_qubits, job_row_id),
        daemon=True,
        name=f"hw-poll-{ibm_job_id[:8]}",
    ).start()

    return ibm_job_id


def _stamp_job_id(job_row_id: int, ibm_job_id: str) -> None:
    """Attach the real IBM job id to the HardwareJob row (no secrets here)."""
    db = SessionLocal()
    try:
        row = db.get(HardwareJob, job_row_id)
        if row is not None:
            row.ibm_job_id = ibm_job_id
            row.status = "queued"
            db.commit()
    finally:
        db.close()


def _owner_of(job_row_id: int) -> int:
    db = SessionLocal()
    try:
        row = db.get(HardwareJob, job_row_id)
        return row.user_id if row else -1
    finally:
        db.close()


def _poll_ibm_job(ibm_job_id: str, service: Any, job: Any, protocol: str,
                  n_qubits: int, job_row_id: int) -> None:
    """Background thread: poll IBM until terminal, then clean up.

    This thread is the sole owner of the runtime ``service`` object after
    submission. At the terminal state we fetch results, publish them, pop
    the service from the broker, and drop the references so both objects
    are garbage collected — the credential inside them is released with
    them.
    """
    deadline = time.monotonic() + 30 * 60  # hard cap: 30 minutes
    try:
        while time.monotonic() < deadline:
            status = job.status()
            state_name = getattr(status, "name", str(status)).upper()
            if state_name in ("QUEUED", "VALIDATING"):
                set_status(ibm_job_id, "queued")
            elif state_name in ("RUNNING", "INITIALIZING"):
                set_status(ibm_job_id, "running")
            elif state_name == "DONE":
                break
            elif state_name in ("ERROR", "CANCELLED", "FAILED"):
                set_status(ibm_job_id, "failed",
                           error=f"IBM job ended with status {state_name}")
                return
            time.sleep(5)
        else:
            set_status(ibm_job_id, "failed", error="poll timed out after 30 min")
            return
        if time.monotonic() >= deadline:
            set_status(ibm_job_id, "failed", error="poll timed out after 30 min")
            return

        result = job.result()
        # SamplerV2, single pub: BitArray over the classical register 'c'.
        reg = result[0].data.c
        ints = reg.get_integers()  # one int per shot, bit i = c[i]
        shots_n = len(ints)

        rng = _rng_for(job_row_id)
        alice_bits = rng.integers(2, size=n_qubits).tolist()
        alice_bases = rng.integers(2, size=n_qubits).tolist()
        bob_bases = rng.integers(2, size=n_qubits).tolist()

        sifted_shots = 0
        kept_lengths = []
        preview: list[list[int]] = []
        for s in range(shots_n):
            outcomes = [(int(ints[s]) >> i) & 1 for i in range(n_qubits)]
            kept = sift_registers(protocol, alice_bases, bob_bases,
                                  alice_bits, outcomes)
            if kept:
                sifted_shots += 1
                kept_lengths.append(len(kept))
                if len(preview) < 16:
                    preview.append(kept[:32])

        avg_len = (
            sum(kept_lengths) / len(kept_lengths) if kept_lengths else 0.0
        )
        set_status(
            ibm_job_id, "done",
            result={
                "total_shots": shots_n,
                "shots_with_key": sifted_shots,
                "avg_sifted_length": round(avg_len, 2),
                "expected_sifted_fraction": 0.5 if protocol == "bb84" else 0.25,
                "sifted_preview": preview,
            },
        )
    except Exception as exc:  # noqa: BLE001 — surface, persist, keep no creds
        set_status(ibm_job_id, "failed", error=f"{type(exc).__name__}: {exc}")
    finally:
        # Credential release: the service (holding the token) is dropped.
        with _jobs_lock:
            _services.pop(ibm_job_id, None)
