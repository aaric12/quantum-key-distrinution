"""Real-hardware execution endpoints (IBM Quantum).

Security contract for the IBM token:

- The token travels in the POST /simulate/hardware request body, is read
  once, and is passed to :func:`app.hardware.submit_and_run`, which uses it
  in a worker thread to construct a ``QiskitRuntimeService``.
- It is NEVER logged (this module has no logging calls at all), NEVER
  persisted (``HardwareJob`` has no token column), and NEVER echoed in any
  response or error message (error strings that could embed provider
  messages are prefixed, never interpolated raw with request data).
- No request-body logging middleware is mounted anywhere in app.main; the
  slowapi limiter keys on the client address and route path only.
- The POST returns 202 with the public job id immediately; execution and
  status streaming happen over WS /ws/hardware/{job_id} (auth: session
  cookie, same pattern as the simulator WebSocket).
"""

import asyncio
from types import SimpleNamespace
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field

from app import auth
from app.hardware import (
    MAX_QUBITS,
    MAX_SHOTS,
    MIN_QUBITS,
    get_job_state,
    subscribe,
    submit_and_run,
    unsubscribe,
)
from app.models import HardwareJob, SessionLocal

router = APIRouter(tags=["hardware"])

# Stricter than the simulator endpoints: real-hardware submissions cost the
# user real quota. Keyed per client address by slowapi.
HARDWARE_RATE_LIMIT = "3/minute"


class HardwareRunIn(BaseModel):
    """Body for POST /simulate/hardware.

    ``ibm_token`` carries NO pydantic length constraints on purpose: pydantic
    v2 embeds the offending input value in 422 error details, which would
    echo a malformed token back in the response. Length checks happen in the
    endpoint as a plain HTTPException with a fixed message instead.
    """

    protocol: str = "bb84"  # "bb84" | "b92"
    n_qubits: int = Field(default=20, ge=MIN_QUBITS, le=MAX_QUBITS)
    shots: int = Field(default=1024, gt=0, le=MAX_SHOTS)
    ibm_token: str


class HardwareJobOut(BaseModel):
    """Response of the submit endpoint — public fields only, never a token."""

    job_id: str
    status: str
    protocol: str
    n_qubits: int
    shots: int
    backend: str | None = None
    poll_url: str


@router.post(
    "/simulate/hardware",
    response_model=HardwareJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
@auth.limiter.limit(HARDWARE_RATE_LIMIT)
async def submit_hardware_run(
    request: Request,
    payload: HardwareRunIn,
    user: auth.CurrentUser,
) -> HardwareJobOut:
    """Accept a real-hardware run and return the job id immediately.

    The token lives in ``payload.ibm_token`` (request body) and is forwarded
    verbatim to :func:`submit_and_run`, which uses it in a worker thread and
    lets the binding go out of scope. Nothing in this endpoint or anything
    it calls writes the token to the database, a log, or a response.
    """
    if payload.protocol not in ("bb84", "b92"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="protocol must be 'bb84' or 'b92'",
        )
    # Manual token validation (fixed message — the value is never echoed).
    if not payload.ibm_token.strip() or len(payload.ibm_token) > 512:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ibm_token missing or too long",
        )

    # Persist the job row FIRST (no token column exists to write to), so the
    # poller and status route have an owner + id before submission begins.
    db = SessionLocal()
    try:
        row = HardwareJob(
            user_id=user.id,
            protocol=payload.protocol,
            ibm_job_id="pending",  # replaced with the real id after submission
            n_qubits=payload.n_qubits,
            shots=payload.shots,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        row_id = row.id
    finally:
        db.close()

    # Heavy, blocking work off the event loop. If IBM rejects the token or
    # no backend fits, the row is deleted and a 502 is returned; the token
    # binding in submit_and_run dies with that worker-thread frame either way.
    try:
        ibm_job_id = await asyncio.to_thread(
            submit_and_run,
            row_id,
            payload.protocol,
            payload.n_qubits,
            payload.shots,
            payload.ibm_token,
        )
    except Exception as exc:  # noqa: BLE001 — never echo provider error text
        db = SessionLocal()
        try:
            row = db.get(HardwareJob, row_id)
            if row is not None:
                db.delete(row)
                db.commit()  # without this the close() rolls the delete back
        finally:
            db.close()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "hardware submission failed — check that the token is valid "
                "and an appropriate backend is available"
            ),
        ) from exc

    state = get_job_state(ibm_job_id)
    return HardwareJobOut(
        job_id=ibm_job_id,
        status="queued",
        protocol=payload.protocol,
        n_qubits=payload.n_qubits,
        shots=payload.shots,
        backend=state.backend if state else None,
        poll_url=f"/ws/hardware/{ibm_job_id}",
    )


@router.websocket("/ws/hardware/{job_id}")
async def ws_hardware_status(ws: WebSocket, job_id: str) -> None:
    """Stream queued/running/done (and error) status for one hardware job.

    Auth: session cookie only — the IBM token is never part of this
    exchange. Frame per transition, then a terminal frame; the socket
    closes after the terminal state or when the client leaves.
    """
    user_id = _current_user_id_ws(ws)
    if user_id is None:
        await ws.close(code=4401, reason="Not authenticated")
        return

    state = get_job_state(job_id)
    if state is None or state.user_id != user_id:
        # Unknown, expired (backend restarted), or not owned by this user.
        await ws.close(code=4404, reason="Unknown job")
        return

    await ws.accept()
    queue: asyncio.Queue = asyncio.Queue()
    if not subscribe(job_id, queue):
        await ws.close(code=4404, reason="Unknown job")
        return

    try:
        # Replay the current state immediately, then stream transitions.
        await ws.send_json(
            {
                "type": "status",
                "job_id": job_id,
                "status": state.status,
                "backend": state.backend,
                "result": state.result,
                "error": state.error,
            }
        )
        while True:
            message = await queue.get()
            await ws.send_json(message)
            if message.get("status") in ("done", "failed"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe(job_id, queue)


def _current_user_id_ws(ws: WebSocket) -> int | None:
    """Resolve the user id from the WS upgrade's session cookie, or None.

    Same contract as the simulator WebSocket: the cookie header is parsed
    manually (WS scopes expose raw headers), the token is validated against
    the user_sessions table, and no credential is logged or stored.
    """
    from app.routers.simulate import _current_user_id_ws as _sim_ws_auth

    return _sim_ws_auth(ws, None)
