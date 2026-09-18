"""Shareable read-only reports for simulation runs.

POST /reports/{run_id}   (auth required, owner-checked)
    Snapshots a run into a UUID-keyed, self-contained report: stage log,
    attack details, ML classification, AI summary, and key-rate chart data.
    The snapshot is intentionally stored OUTSIDE the user-account tables:
    reports are public read-only artifacts keyed by an unguessable UUID and
    must survive user deletion, so the Report row carries no user_id.

GET /reports/{uuid}      (public, unauthenticated, read-only)
    Returns the stored snapshot verbatim. Nothing is computed here, so a
    shared link can never leak anything added after the snapshot.

GET /reports/{uuid}/report.pdf   (public, unauthenticated)
    Renders the snapshot as a PDF via reportlab.
"""

import asyncio
import uuid as uuid_mod
from types import SimpleNamespace
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import auth
from app.ai_summary import summarize_run
from app.keyrate import DEFAULT_CLOCK_HZ, DEFAULT_STEP_KM, skr_curve
from app.models import ProtocolStageLog, Report, SimulationRun, get_db
from app.routers.simulate import _ml_view, _run_facts

router = APIRouter(tags=["reports"])

DbDep = Annotated[Session, Depends(get_db)]


class ReportCreated(BaseModel):
    """Response of POST /reports/{run_id}."""

    uuid: str
    run_id: int
    title: str | None
    created_at: str
    share_url: str


def _get_run_checked(db: Session, run_id: int, user_id: int) -> SimulationRun:
    """Fetch the run, 404 for unknown or non-owned (no existence oracle)."""
    run = db.get(SimulationRun, run_id)
    if run is None or run.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Run not found"
        )
    return run


def _build_snapshot(db: Session, run: SimulationRun, protocol: str) -> dict[str, Any]:
    """Assemble the self-contained report payload for one run.

    Best-effort extras (ML, AI summary) degrade to nulls rather than failing
    the snapshot — a report must always be creatable.
    """
    stages = [
        {
            "stage_index": s.stage_index,
            "stage_name": s.stage_name,
            "payload": s.payload,
        }
        for s in db.query(ProtocolStageLog)
        .filter(ProtocolStageLog.run_id == run.id)
        .order_by(ProtocolStageLog.stage_index)
        .all()
    ]

    # ML classification recomputed at snapshot time (from stored result_json).
    ml_pred, ml_probs = _ml_view(SimpleNamespace(**run.result_json))

    snapshot: dict[str, Any] = {
        "run": {
            "id": run.id,
            "protocol": run.protocol,
            "n_qubits": run.n_qubits,
            "seed": run.seed,
            "qber": run.qber,
            "aborted": run.aborted,
            "abort_reason": run.abort_reason,
            "attack_type": run.attack_type,
            "attack_intensity": run.attack_intensity,
            "sifted_count": run.sifted_count,
            "final_key_length": run.final_key_length,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        },
        "attack": {
            "type": run.attack_type,
            "intensity": run.attack_intensity,
            "description": _attack_blurb(run.attack_type, run.attack_intensity),
        },
        "stages": stages,
        "ml": {"predicted_class": ml_pred, "probabilities": ml_probs},
        "ai_summary": None,
        "summary_source": None,
        "keyrate": None,
    }

    # AI summary: deterministic fallback unless an LLM key is configured;
    # same fact shape the simulate endpoints use. asyncio.run is safe here:
    # sync endpoints execute in worker threads with no running loop.
    result_like = SimpleNamespace(**run.result_json)
    req_like = SimpleNamespace(n_qubits=run.n_qubits, seed=run.seed, noise=None)
    facts = _run_facts(
        protocol, result_like, req_like, ml_pred, ml_probs
    )
    try:
        ai = asyncio.run(summarize_run(facts))
        snapshot["ai_summary"] = ai["summary"]
        snapshot["summary_source"] = ai["summary_source"]
    except Exception:  # noqa: BLE001 — a summary failure must not block sharing
        pass

    # Key-rate chart data for the run's protocol at the measured QBER level:
    # the clean curve plus the curve the attack intensity implies.
    try:
        clean = skr_curve(
            protocol, attack_intensity=0.0,
            clock_hz=DEFAULT_CLOCK_HZ, step_km=DEFAULT_STEP_KM,
        )
        attacked = skr_curve(
            protocol,
            attack_intensity=float(run.attack_intensity or 0.0),
            clock_hz=DEFAULT_CLOCK_HZ, step_km=DEFAULT_STEP_KM,
        )
        snapshot["keyrate"] = {
            "protocol": protocol,
            "clean_curve": clean["curve"],
            "attacked_curve": attacked["curve"],
            "clean_cutoff_km": clean["cutoff_km"],
            "attacked_cutoff_km": attacked["cutoff_km"],
        }
    except Exception:  # noqa: BLE001
        pass

    return snapshot


def _attack_blurb(attack_type: str | None, intensity: float) -> str:
    if not attack_type:
        return "No attack was applied — ideal channel."
    blurbs = {
        "intercept_resend": (
            "Eve measured an intensity-scaled fraction of qubits in a random "
            "basis and re-sent her measured states, adding ~intensity/4 (BB84) "
            "or ~intensity/3 (B92) to the QBER."
        ),
        "pns": (
            "Photon-number splitting on weak coherent pulses with 3 decoy "
            "levels; detectable only through loss-rate statistics across "
            "intensities, not through QBER."
        ),
        "trojan": (
            "Simplified conceptual Trojan-horse model: localized leakage "
            "patches at Alice's modulator flip bits with probability 0.5x "
            "intensity inside them."
        ),
    }
    base = blurbs.get(attack_type, attack_type)
    return f"{base} Attack intensity: {intensity * 100:.0f}%."


@router.post("/reports/{run_id}", response_model=ReportCreated, status_code=201)
def create_report(
    run_id: int,
    db: DbDep,
    user: auth.CurrentUser,
) -> ReportCreated:
    """Snapshot one owned run into a public, UUID-keyed report."""
    run = _get_run_checked(db, run_id, user.id)
    snapshot = _build_snapshot(db, run, run.protocol)

    title = f"{run.protocol.upper()} run #{run.id}"
    if run.attack_type:
        title += f" — {run.attack_type} @ {run.attack_intensity * 100:.0f}%"
    elif run.aborted:
        title += " — aborted"

    report = Report(
        uuid=str(uuid_mod.uuid4()),
        run_id=run.id,
        title=title,
        payload=snapshot,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return ReportCreated(
        uuid=report.uuid,
        run_id=run.id,
        title=title,
        created_at=report.created_at.isoformat(),
        share_url=f"/reports/{report.uuid}",
    )


@router.get("/reports/{report_uuid}")
def get_report(report_uuid: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Public, unauthenticated, read-only report fetch."""
    report = (
        db.query(Report).filter(Report.uuid == report_uuid).one_or_none()
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report not found"
        )
    return {
        "uuid": report.uuid,
        "title": report.title,
        "created_at": report.created_at.isoformat(),
        **report.payload,
    }


@router.get("/reports/{report_uuid}/report.pdf")
def get_report_pdf(report_uuid: str, db: Session = Depends(get_db)) -> Response:
    """Public PDF rendering of the report snapshot (reportlab)."""
    report = (
        db.query(Report).filter(Report.uuid == report_uuid).one_or_none()
    )
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report not found"
        )

    from app.report_pdf import render_report_pdf  # local import: heavy module

    pdf_bytes = render_report_pdf(
        report.title,
        {**report.payload, "created_at": report.created_at.isoformat()},
    )
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="qkd-report-{report.uuid[:8]}.pdf"'
        },
    )
