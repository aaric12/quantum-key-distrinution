"""Simulation endpoints: run a protocol and stream its stages live.

- POST /simulate/bb84 — blocking run; the full BB84Result (every stage) comes
  back in one response.
- WS   /ws/simulate/bb84 — the same pipeline, but each stage is sent as its
  own JSON message the moment it completes. Requires the session cookie;
  browsers attach it automatically on WebSocket upgrades.

Auth note: Starlette's WebSocket scope exposes headers, not the parsed
cookies dependency used by REST routes, so the raw ``cookie`` header is
parsed manually. A rejected socket is closed with code 4401 *before*
accept(), so the browser surfaces an unambiguous auth failure instead of a
silently dead socket.
"""

import asyncio
import json
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
from sqlalchemy.orm import Session

from app import auth
from app.models import ProtocolStageLog, SimulationRun, get_db
from app.protocols.bb84 import BB84Result, run_bb84

router = APIRouter(tags=["simulate"])

DbDep = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class Bb84RunIn(BaseModel):
    """Parameters for one BB84 run (REST body / WS ``run`` frame)."""

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


class Bb84RunOut(SimulationRunOut):
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

# The pipeline, in execution order. Each entry is a stage name plus a
# selector over BB84Result: a list of field names, or a callable deriving a
# small dict. The WebSocket and the REST response therefore always report
# identical stage data.
STAGES: list[tuple[str, Any]] = [
    ("alice_encode", ["alice_bits", "alice_bases"]),
    ("channel", lambda r: {"n_qubits": len(r.alice_bits)}),
    ("bob_measure", ["bob_bases", "bob_bits"]),
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


def _stage_payload(result: BB84Result, selector: Any) -> dict:
    """Materialize a stage payload dict from the result object."""
    if callable(selector):
        return dict(selector(result))
    return {name: getattr(result, name) for name in selector}


def _stage_summary(stage_name: str, result: BB84Result) -> str:
    """Short human-readable one-liner for the timeline UI."""
    if stage_name == "alice_encode":
        return f"Alice generated {len(result.alice_bits)} random bits + bases (Z/X)"
    if stage_name == "channel":
        return "Quantum channel: qubits transmitted"
    if stage_name == "bob_measure":
        return f"Bob measured {len(result.bob_bits)} qubits in independent bases"
    if stage_name == "sifting":
        kept = len(result.sifted_alice)
        pct = kept * 100 // max(1, len(result.alice_bits))
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


def build_stage_messages(result: BB84Result) -> list[StageMessage]:
    """Slice a finished BB84Result into ordered stage messages."""
    msgs: list[StageMessage] = []
    for i, (name, selector) in enumerate(STAGES):
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


def _result_to_dict(result: BB84Result) -> dict:
    """Full BB84Result as a JSON-safe dict (for result_json)."""
    return {f.name: getattr(result, f.name) for f in fields(BB84Result)}


def persist_run(
    db: Session,
    *,
    user_id: int,
    req: Bb84RunIn,
    result: BB84Result,
    stage_msgs: list[StageMessage],
) -> SimulationRun:
    """Persist one SimulationRun plus its ordered ProtocolStageLog rows.

    One transaction: the run row is flushed to assign its id, the stage rows
    are staged against it, then everything commits together.
    """
    run = SimulationRun(
        user_id=user_id,
        protocol="bb84",
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
    "/simulate/bb84", response_model=Bb84RunOut, status_code=status.HTTP_201_CREATED
)
def run_bb84_sync(
    req: Bb84RunIn,
    db: DbDep,
    user: auth.CurrentUser,
) -> Bb84RunOut:
    """Run the full BB84 pipeline once, persist it, and return every stage."""
    _validated(req)
    result = run_bb84(n_qubits=req.n_qubits, seed=req.seed, noise=req.noise)
    stage_msgs = build_stage_messages(result)
    run = persist_run(db, user_id=user.id, req=req, result=result, stage_msgs=stage_msgs)
    out = SimulationRunOut.model_validate(run)
    return Bb84RunOut(
        **out.model_dump(),
        result=_result_to_dict(result),
        stages=[m.model_dump() for m in stage_msgs],
    )


@router.websocket("/ws/simulate/bb84")
async def ws_bb84(
    ws: WebSocket, db: Annotated[Session, Depends(get_db)]
) -> None:
    """Stream each BB84 stage as its own JSON frame as the pipeline completes.

    Frame sequence: one "connected" hello -> a client "run" frame with
    parameters -> eight "stage" frames (pipeline order) -> a "done" frame
    carrying the run summary + persisted run id. Any invalid client frame or
    pipeline failure becomes a single "error" frame followed by a close, and
    nothing is persisted.
    """
    user_id = _current_user_id_ws(ws, db)
    if user_id is None:
        await ws.close(code=4401, reason="Not authenticated")
        return
    await ws.accept()

    await ws.send_json(
        StageMessage(type="connected", data={"protocol": "bb84"}).model_dump()
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
        req = _validated(Bb84RunIn(**{k: v for k, v in raw.items() if k != "type"}))
    except (ValueError, HTTPException) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        await ws.send_json(StageMessage(type="error", summary=detail).model_dump())
        await ws.close()
        return

    # Phase 2: run + stream. Each stage frame is flushed to the socket before
    # the next is produced. Persistence happens after the final frame so the
    # socket never blocks on the database mid-stream.
    try:
        result = run_bb84(n_qubits=req.n_qubits, seed=req.seed, noise=req.noise)
        stage_msgs = build_stage_messages(result)
        for msg in stage_msgs:
            await ws.send_json(msg.model_dump())
            await asyncio.sleep(0)  # yield so frames flush incrementally

        run = persist_run(
            db, user_id=user_id, req=req, result=result, stage_msgs=stage_msgs
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


def _validated(req: Bb84RunIn) -> Bb84RunIn:
    """Enforce simulation bounds that pydantic field constraints can't express."""
    if req.n_qubits < 16:
        raise HTTPException(status_code=422, detail="n_qubits must be >= 16")
    if req.n_qubits > 10000:
        raise HTTPException(status_code=422, detail="n_qubits must be <= 10000")
    if not 0.0 <= req.noise <= 1.0:
        raise HTTPException(status_code=422, detail="noise must be within [0, 1]")
    return req
