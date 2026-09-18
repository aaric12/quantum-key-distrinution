"""Secret-key-rate vs distance endpoint (pure math, no persistence).

GET /keyrate?protocol=bb84[&distance_km=80][&attack_intensity=0.5][...]

Query parameters (all optional unless noted):
    protocol          bb84 | b92                       (default bb84)
    distance_km       evaluate a single point too       (default: none)
    alpha_db_km       fiber loss coefficient            (default 0.2 dB/km)
    eta_det           detector efficiency 0-1           (default 0.6)
    dcr_per_gate      dark-count prob per gate          (default 3e-6)
    misalignment      baseline optical QBER             (default 0.015)
    mu                WCP mean photon number            (default 0.5)
    f_ec              EC inefficiency                   (default 1.16)
    clock_hz          pulse clock (bits/s conversion)   (default 1e8)
    attack_intensity  intercept-resend 0-1              (default 0.0)
    max_distance_km   curve extent                      (default 300)
    step_km           curve resolution                  (default 5)

Response: {"protocol", "curve": [{distance_km, skr_bps, qber}...],
"cutoff_km", "peak_skr_bps", "peak_distance_km", "params", and — when
distance_km was given — "point" with the single-distance evaluation}.
No auth: the endpoint computes from constants, holds no user data, and is
useful unauthenticated; rate limiting is unnecessary for pure math.
"""

import math
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status

from app.keyrate import (
    ATTACK_QBER_SLOPE,
    DEFAULT_ALPHA_DB_KM,
    DEFAULT_CLOCK_HZ,
    DEFAULT_DCR_PER_GATE,
    DEFAULT_ETA_DET,
    DEFAULT_F_EC,
    DEFAULT_MISALIGNMENT,
    DEFAULT_MU,
    DEFAULT_STEP_KM,
    PROTOCOLS,
    SIFTING_FRACTION,
    skr_curve,
    skr_per_pulse,
)

router = APIRouter(tags=["keyrate"])


@router.get("/keyrate")
def get_keyrate(
    protocol: str = "bb84",
    distance_km: Annotated[float | None, Query(gt=0, le=1000)] = None,
    alpha_db_km: Annotated[float, Query(gt=0, le=5)] = DEFAULT_ALPHA_DB_KM,
    eta_det: Annotated[float, Query(gt=0, lt=1)] = DEFAULT_ETA_DET,
    dcr_per_gate: Annotated[float, Query(ge=0, lt=0.1)] = DEFAULT_DCR_PER_GATE,
    misalignment: Annotated[float, Query(ge=0, lt=0.25)] = DEFAULT_MISALIGNMENT,
    mu: Annotated[float, Query(gt=0, le=2)] = DEFAULT_MU,
    f_ec: Annotated[float, Query(ge=1.0, le=2.0)] = DEFAULT_F_EC,
    clock_hz: Annotated[float, Query(gt=0, le=1e12)] = DEFAULT_CLOCK_HZ,
    attack_intensity: Annotated[float, Query(ge=0, le=1)] = 0.0,
    max_distance_km: Annotated[float, Query(gt=0, le=1000)] = 300.0,
    step_km: Annotated[float, Query(gt=0, le=100)] = DEFAULT_STEP_KM,
) -> dict[str, Any]:
    """SKR-vs-distance curve (and optional single point) for one protocol."""
    if protocol not in PROTOCOLS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"protocol must be one of {list(PROTOCOLS)}",
        )
    # A curve spanning 1000 km at 0.1 km steps would be 10k points; keep the
    # response bounded (8192 points max) — the frontend only plots ~60.
    if max_distance_km / step_km > 8192:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="max_distance_km / step_km too large",
        )

    curve = skr_curve(
        protocol,
        alpha_db_km=alpha_db_km,
        eta_det=eta_det,
        dcr_per_gate=dcr_per_gate,
        misalignment=misalignment,
        mu=mu,
        f_ec=f_ec,
        clock_hz=clock_hz,
        attack_intensity=attack_intensity,
        max_distance_km=max_distance_km,
        step_km=step_km,
    )

    response: dict[str, Any] = {**curve}
    if distance_km is not None:
        point = skr_per_pulse(
            protocol,
            distance_km,
            alpha_db_km=alpha_db_km,
            eta_det=eta_det,
            dcr_per_gate=dcr_per_gate,
            misalignment=misalignment,
            mu=mu,
            f_ec=f_ec,
            attack_intensity=attack_intensity,
        )
        point["skr_bps"] = point["skr_per_pulse"] * clock_hz
        response["point"] = point
    return response
