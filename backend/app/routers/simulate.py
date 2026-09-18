"""Simulation endpoints: run a protocol and stream its stages live.

- POST /simulate/{protocol} — blocking run; the full result dataclass (every
  stage) comes back in one response. Protocols: bb84, b92.
- WS   /ws/simulate/{protocol} — the same pipelines, but each stage is sent
  as its own JSON message the moment it completes. Requires the session
  cookie; browsers attach it automatically on WebSocket upgrades.

Both protocols share one frame protocol, one stage-message builder, and one
persistence path; only the run function and the stage table differ.

Auth note: Starlette's WebSocket scope exposes headers, not the parsed
cookies dependency used by REST routes, so the raw ``cookie`` header is
parsed manually. A rejected socket is closed with code 4401 *before*
accept(), so the browser surfaces an unambiguous auth failure instead of a
silently dead socket.
"""

import asyncio
import json
from collections.abc import Callable
from dataclasses import fields
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.models import ProtocolStageLog, SimulationRun, get_db
from app.protocols.b92 import B92Result, run_b92
from app.protocols.bb84 import BB84Result, run_bb84

router = APIRouter(tags=["simulate"])

DbDep = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RunIn(BaseModel):
    """Parameters for one protocol run (REST body / WS ``run`` frame)."""

    n_qubits: int = 256
    seed: int | None = None
    noise: float = 0.0


class SimulationRunOut(BaseModel):
    """Summary of a persisted run (no stage payloads)."""

    id: int
    protocol: str
    n_qubits: int
    seed: int | None
    qber: float | None
    aborted: bool
    abort_reason: str | None
    sifted_count: int
    final_key_length: int
    created_at: Any

    model_config = {"from_attributes": True}


class RunOut(SimulationRunOut):
    """POST response: persisted run summary, the full result payload, and the
    ordered stage messages (same shape the WebSocket streams, so clients can
    render one timeline from either transport)."""

    result: dict
    stages: list[dict]


class StageMessage(BaseModel):
    """One WebSocket frame: a completed stage, or a run terminator."""

    type: str  # "connected" | "stage" | "done" | "error"
    run_id: int | None = None
    stage_index: int | None = None
    stage_name: str | None = None
    summary: str | None = None
    data: dict | None = None


# ---------------------------------------------------------------------------
# Stage extraction — the shared spine of both endpoints
# ---------------------------------------------------------------------------

# Stage selectors shared by every PM protocol: after sifting, the pipeline
# shape is identical, and BB84's alice_bases doubles as B92's alice_states.
# Protocol-specific stages (BB84 basis matching vs B92 conclusive outcomes)
# come first, then the common tail.
_COMMON_STAGES: list[tuple[str, Any]] = [
    ("channel", lambda r: {"n_qubits": len(r.alice_bits)}),
    ("bob_measure", ["bob_bases", "bob_bits", "bob_outcomes", "bob_inferred"]),
    ("sifting", ["sifted_alice", "sifted_bob"]),
    (
        "qber_check",
        ["sample_indices", "sample_alice", "sample_bob", "sample_errors", "qber"],
    ),
    ("abort_decision", lambda r: {"aborted": r.aborted, "reason": r.abort_reason}),
    (
        "error_correction",
        [
            "remaining_alice",
            "remaining_bob",
            "parity_bits_revealed",
            "corrected_positions",
            "corrected_alice",
            "corrected_bob",
        ],
    ),
    ("privacy_amplification", ["final_key_alice", "final_key_bob"]),
]

STAGES: dict[str, list[tuple[str, Any]]] = {
    "bb84": [
        ("alice_encode", ["alice_bits", "alice_bases"]),
        *_COMMON_STAGES,
    ],
    "b92": [
        ("alice_encode", ["alice_bits", "alice_states"]),
        *_COMMON_STAGES,
    ],
}

# run function + result type per protocol slug.
PROTOCOLS: dict[str, tuple[Callable[..., BB84Result], type]] = {
    "bb84": (run_bb84, BB84Result),
    "b92": (run_b92, B92Result),
}


def _stage_payload(result: Any, selector: Any) -> dict:
    """Materialize a stage payload dict from the result object.

    A selector entry may be missing on a result type (e.g. bob_outcomes on
    BB84); missing fields are simply omitted from the payload.
    """
    if callable(selector):
        return dict(selector(result))
    return {
        name: getattr(result, name)
        for name in selector
        if hasattr(result, name)
    }


def _stage_summary(stage_name: str, result: Any) -> str:
    """Short human-readable one-liner for the timeline UI."""
    if stage_name == "alice_encode":
        return f"Alice generated {len(result.alice_bits)} random bits + bases (Z/X)"
    if stage_name == "channel":
        return "Quantum channel: qubits transmitted"
    if stage_name == "bob_measure":
        measured = getattr(result, "bob_bits", None)
        n = len(measured if measured is not None else result.bob_outcomes)
        conclusive = getattr(result, "bob_inferred", None)
        if conclusive is not None:
            kept = sum(1 for v in conclusive if v is not None)
            return (
                f"Bob measured {n} qubits in random bases "
                f"({kept} conclusive outcomes)"
            )
        return f"Bob measured {n} qubits in independent bases"
    if stage_name == "sifting":
        kept = len(result.sifted_alice)
        pct = kept * 100 // max(1, len(result.alice_bits))
        if hasattr(result, "bob_inferred"):
            return (
                f"Sifting: kept {kept} conclusive outcomes "
                f"({pct}% of transmitted)"
            )
        return f"Sifting: kept {kept} matching-basis positions ({pct}%)"
    if stage_name == "qber_check":
        n = len(result.sample_indices)
        return f"QBER sample: {result.sample_errors}/{n} errors -> {result.qber:.3f}"
    if stage_name == "abort_decision":
        if result.aborted:
            return "ABORT — channel compromised"
        return "QBER within threshold — proceed"
    if stage_name == "error_correction":
        return (
            f"Error correction: fixed {len(result.corrected_positions)} bit(s), "
            f"{result.parity_bits_revealed} parity bits revealed"
        )
    if stage_name == "privacy_amplification":
        return f"Privacy amplification: final key {len(result.final_key_alice)} bits"
    return stage_name


def build_stage_messages(
    protocol: str, result: BB84Result | B92Result
) -> list[StageMessage]:
    """Slice a finished protocol result into ordered stage messages."""
    msgs: list[StageMessage] = []
    for i, (name, selector) in enumerate(STAGES[protocol]):
        msgs.append(
            StageMessage(
                type="stage",
                stage_index=i,
                stage_name=name,
                summary=_stage_summary(name, result),
                data=_stage_payload(result, selector),
            )
        )
    return msgs


def _result_to_dict(result: Any) -> dict:
    """Full result dataclass as a JSON-safe dict (for result_json)."""
    return {f.name: getattr(result, f.name) for f in fields(result)}


def persist_run(
    db: Session,
    *,
    user_id: int,
    protocol: str,
    req: RunIn,
    result: Any,
    stage_msgs: list[StageMessage],
) -> SimulationRun:
    """Persist one SimulationRun plus its ordered ProtocolStageLog rows.

    One transaction: the run row is flushed to assign its id, the stage rows
    are staged against it, then everything commits together.
    """
    run = SimulationRun(
        user_id=user_id,
        protocol=protocol,
        n_qubits=req.n_qubits,
        seed=req.seed,
        qber=result.qber,
        aborted=result.aborted,
        abort_reason=result.abort_reason,
        sifted_count=len(result.sifted_alice),
        final_key_length=len(result.final_key_alice),
        result_json=_result_to_dict(result),
    )
    db.add(run)
    db.flush()  # assign run.id before staging children

    for msg in stage_msgs:
        db.add(
            ProtocolStageLog(
                run_id=run.id,
                stage_index=msg.stage_index,
                stage_name=msg.stage_name,
                payload={"summary": msg.summary, "data": msg.data},
            )
        )
    db.commit()
    db.refresh(run)
    return run


# ---------------------------------------------------------------------------
# WebSocket auth (cookie parsed from the raw upgrade header)
# ---------------------------------------------------------------------------


def _current_user_id_ws(ws: WebSocket, db: Session) -> int | None:
    """Resolve the user id from the WS upgrade's session cookie, or None."""
    raw = ws.headers.get("cookie")
    if not raw:
        return None
    token = None
    # Cookie headers are semicolon-separated "k=v" pairs; find ours without
    # assuming it is the first.
    for part in raw.split(";"):
        k, _, v = part.strip().partition("=")
        if k == auth.settings.session_cookie_name:
            token = v
            break
    if not token:
        return None
    try:
        return auth.decode_access_token(token)
    except HTTPException:
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/simulate/{protocol}", response_model=RunOut, status_code=status.HTTP_201_CREATED
)
def run_protocol_sync(
    protocol: str,
    req: RunIn,
    db: DbDep,
    user: auth.CurrentUser,
) -> RunOut:
    """Run the full pipeline once, persist it, and return every stage."""
    run_fn, result_type = _protocol_or_404(protocol)
    _validated(req)
    result = run_fn(n_qubits=req.n_qubits, seed=req.seed, noise=req.noise)
    stage_msgs = build_stage_messages(protocol, result)
    run = persist_run(
        db, user_id=user.id, protocol=protocol, req=req, result=result, stage_msgs=stage_msgs
    )
    out = SimulationRunOut.model_validate(run)
    return RunOut(
        **out.model_dump(),
        result=_result_to_dict(result),
        stages=[m.model_dump() for m in stage_msgs],
    )


@router.websocket("/ws/simulate/{protocol}")
async def ws_protocol(
    ws: WebSocket, protocol: str, db: Annotated[Session, Depends(get_db)]
) -> None:
    """Stream each protocol stage as its own JSON frame as the pipeline runs.

    Frame sequence: one "connected" hello -> a client "run" frame with
    parameters -> eight "stage" frames (pipeline order) -> a "done" frame
    carrying the run summary + persisted run id. Any invalid client frame,
    unknown protocol, or pipeline failure becomes a single "error" frame
    followed by a close, and nothing is persisted.
    """
    if protocol not in PROTOCOLS:
        await ws.close(code=4404, reason=f"Unknown protocol: {protocol}")
        return
    user_id = _current_user_id_ws(ws, db)
    if user_id is None:
        await ws.close(code=4401, reason="Not authenticated")
        return
    await ws.accept()

    await ws.send_json(
        StageMessage(type="connected", data={"protocol": protocol}).model_dump()
    )

    # Phase 1: negotiate parameters.
    try:
        raw = await ws.receive_json()
    except WebSocketDisconnect:
        return
    if not isinstance(raw, dict) or raw.get("type") != "run":
        await ws.send_json(
            StageMessage(
                type="error", summary="expected a {type: 'run'} frame"
            ).model_dump()
        )
        await ws.close()
        return
    try:
        req = _validated(RunIn(**{k: v for k, v in raw.items() if k != "type"}))
    except (ValueError, HTTPException) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        await ws.send_json(StageMessage(type="error", summary=detail).model_dump())
        await ws.close()
        return

    run_fn, _ = PROTOCOLS[protocol]

    # Phase 2: run + stream. Each stage frame is flushed to the socket before
    # the next is produced. Persistence happens after the final frame so the
    # socket never blocks on the database mid-stream.
    try:
        result = run_fn(n_qubits=req.n_qubits, seed=req.seed, noise=req.noise)
        stage_msgs = build_stage_messages(protocol, result)
        for msg in stage_msgs:
            await ws.send_json(msg.model_dump())
            await asyncio.sleep(0)  # yield so frames flush incrementally

        run = persist_run(
            db,
            user_id=user_id,
            protocol=protocol,
            req=req,
            result=result,
            stage_msgs=stage_msgs,
        )
        await ws.send_json(
            StageMessage(
                type="done",
                run_id=run.id,
                summary=(
                    "ABORT — channel compromised"
                    if result.aborted
                    else f"Key established: {len(result.final_key_alice)} bits"
                ),
                data={
                    "aborted": result.aborted,
                    "abort_reason": result.abort_reason,
                    "sifted_count": len(result.sifted_alice),
                    "final_key_length": len(result.final_key_alice),
                    "qber": result.qber,
                    "final_key_match": result.final_key_alice == result.final_key_bob,
                },
            ).model_dump()
        )
    except WebSocketDisconnect:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001 — report, persist nothing, close cleanly
        db.rollback()
        await ws.send_json(StageMessage(type="error", summary=str(exc)).model_dump())
        await ws.close()
        return


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@router.get("/simulate/runs", response_model=list[SimulationRunOut])
def list_runs(
    db: DbDep,
    user: auth.CurrentUser,
    limit: int = 20,
) -> list[SimulationRun]:
    """List the current user's persisted runs, newest first."""
    limit = max(1, min(limit, 100))
    return list(
        db.execute(
            select(SimulationRun)
            .where(SimulationRun.user_id == user.id)
            .order_by(SimulationRun.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )


def _validated(req: RunIn) -> RunIn:
    """Enforce simulation bounds that pydantic field constraints can't express."""
    if req.n_qubits < 16:
        raise HTTPException(status_code=422, detail="n_qubits must be >= 16")
    if req.n_qubits > 10000:
        raise HTTPException(status_code=422, detail="n_qubits must be <= 10000")
    if not 0.0 <= req.noise <= 1.0:
        raise HTTPException(status_code=422, detail="noise must be within [0, 1]")
    return req


def _protocol_or_404(protocol: str) -> tuple[Callable[..., Any], type]:
    """Resolve a protocol slug to its run function, or raise 404."""
    entry = PROTOCOLS.get(protocol)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown protocol '{protocol}'. Available: {sorted(PROTOCOLS)}",
        )
    return entry
