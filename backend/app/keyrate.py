"""Secret-key-rate vs distance model (standard asymptotic weak-coherent).

This is the textbook GLLP-style asymptotic rate for a weak coherent pulse
(WCP) QKD link with dark counts and channel loss:

    R  =  q * [ Q1 * (1 - h2(e1))  -  Q_mu * f * h2(E_mu) ]      [bits/pulse]

with, for channel transmittance eta_ch(d) = 10 ** (-alpha * d / 10)
(alpha in dB/km) and total transmittance eta = eta_ch * eta_det:

  P1     = mu * exp(-mu)                single-photon emission probability
  Ysig   = 1 - exp(-eta * mu)           gain of genuine signal (any n >= 1)
  Y0     = 2 * p_d                      dark-click yield (either detector)
  Qmu    = Y0 + Ysig - Y0 * Ysig        overall gain (passive dark + signal)
  E_mu   = (0.5 * Y0 + e_mis * Ysig) / Qmu        overall QBER (e0 = 1/2)
  Q1     = P1 * (eta + 2 * p_d * (1 - eta))       single-photon gain
  e1     = (p_d + e_mis * eta) / (eta + 2 * p_d * (1 - eta))
                                        single-photon error rate
  q      = sifting fraction: 1/2 (BB84) | 1/4 (B92) — matches the simulators
  f      = error-correction inefficiency (standard 1.16)
  h2(p)  = binary entropy, guarded for p in {0, 1}

Attack model (consistent with the measured Step-7 simulators): an
intercept-resend attack at intensity I adds I/4 (BB84) or I/3 (B92) to the
sifted QBER — Eve's random-basis interaction acts exactly like extra
misalignment on the signal term. The added error applies to both the
overall and the single-photon error rates. Because the abort threshold in
the simulators is 0.11, the rate vanishes once E_mu crosses ~11% — the
chart therefore shows attacked links dying earlier, or dying everywhere at
high intensity.

Everything is pure math: no RNG, no DB, no IO — trivially testable.
"""

from __future__ import annotations

import math
from typing import Any

# Sifting fractions — identical to what run_bb84 / run_b92 produce.
SIFTING_FRACTION = {"bb84": 0.5, "b92": 0.25}

# Intercept-resend adds sifted QBER ≈ I/4 (BB84) or I/3 (B92); measured in
# scripts/test_attacks.py and derived from Eve's random-basis statistics.
ATTACK_QBER_SLOPE = {"bb84": 0.25, "b92": 1.0 / 3.0}

PROTOCOLS = ("bb84", "b92")

# Defaults (typical fiber link values; all overridable via query params).
DEFAULT_ALPHA_DB_KM = 0.2       # fiber attenuation, dB/km
DEFAULT_ETA_DET = 0.6           # detector efficiency (fraction)
DEFAULT_DCR_PER_GATE = 3.0e-6   # dark-count probability per gate per detector
DEFAULT_MISALIGNMENT = 0.015    # baseline optical misalignment QBER
DEFAULT_MU = 0.2                # WCP mean photon number (security-driven)
DEFAULT_F_EC = 1.16             # EC inefficiency factor
DEFAULT_CLOCK_HZ = 1.0e8        # system clock (pulses/s) -> bits/s conversion
DEFAULT_MAX_DISTANCE_KM = 300.0
DEFAULT_STEP_KM = 5.0


def h2(p: float) -> float:
    """Shannon binary entropy in bits, guarded at the edges."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -p * math.log2(p) - (1.0 - p) * math.log2(1.0 - p)


def channel_transmittance(distance_km: float, alpha_db_km: float) -> float:
    """Fiber transmittance: eta_ch = 10^(-alpha * d / 10)."""
    return 10.0 ** (-alpha_db_km * max(0.0, distance_km) / 10.0)


def skr_per_pulse(
    protocol: str,
    distance_km: float,
    *,
    alpha_db_km: float = DEFAULT_ALPHA_DB_KM,
    eta_det: float = DEFAULT_ETA_DET,
    dcr_per_gate: float = DEFAULT_DCR_PER_GATE,
    misalignment: float = DEFAULT_MISALIGNMENT,
    mu: float = DEFAULT_MU,
    f_ec: float = DEFAULT_F_EC,
    attack_intensity: float = 0.0,
) -> dict[str, float]:
    """Asymptotic secret key rate in bits per pulse at one distance.

    Returns a dict with skr (bits/pulse, clamped at 0), qber (E_mu) and the
    intermediate gains — handy for tests and for the API readouts.
    """
    if protocol not in SIFTING_FRACTION:
        raise ValueError(f"unknown protocol {protocol!r}")
    q = SIFTING_FRACTION[protocol]

    eta = channel_transmittance(distance_km, alpha_db_km) * eta_det
    p1 = mu * math.exp(-mu)
    y_sig = 1.0 - math.exp(-eta * mu)
    y0 = 2.0 * dcr_per_gate

    q_mu = y0 + y_sig - y0 * y_sig
    e_mu = (0.5 * y0 + misalignment * y_sig) / q_mu

    y1 = eta + 2.0 * dcr_per_gate * (1.0 - eta)
    q1 = p1 * y1
    e1 = (dcr_per_gate + misalignment * eta) / y1

    # Intercept-resend: measured sifted-QBER slope (I/4 BB84, I/3 B92),
    # folded into both error terms like extra misalignment.
    if attack_intensity > 0.0:
        added = ATTACK_QBER_SLOPE[protocol] * min(1.0, attack_intensity)
        e_mu = min(e_mu + added, 0.5)
        e1 = min(e1 + added, 0.5)

    rate = q * (q1 * (1.0 - h2(e1)) - q_mu * f_ec * h2(e_mu))
    return {
        "skr_per_pulse": max(0.0, rate),
        "qber": e_mu,
        "eta_channel": channel_transmittance(distance_km, alpha_db_km),
        "eta_total": eta,
        "q_mu": q_mu,
        "q1": q1,
        "e1": e1,
    }


def skr_curve(
    protocol: str,
    *,
    alpha_db_km: float = DEFAULT_ALPHA_DB_KM,
    eta_det: float = DEFAULT_ETA_DET,
    dcr_per_gate: float = DEFAULT_DCR_PER_GATE,
    misalignment: float = DEFAULT_MISALIGNMENT,
    mu: float = DEFAULT_MU,
    f_ec: float = DEFAULT_F_EC,
    clock_hz: float = DEFAULT_CLOCK_HZ,
    attack_intensity: float = 0.0,
    max_distance_km: float = DEFAULT_MAX_DISTANCE_KM,
    step_km: float = DEFAULT_STEP_KM,
) -> dict[str, Any]:
    """Evaluate the rate over a distance grid and derive readouts.

    Returns the curve for the chart plus the derived cutoff distance (first
    grid point where the rate hits zero and stays there) and the peak SKR.
    """
    if step_km <= 0:
        raise ValueError("step_km must be positive")
    if max_distance_km <= 0:
        raise ValueError("max_distance_km must be positive")

    points: list[dict[str, float]] = []
    cutoff_km: float | None = None
    peak_skr = 0.0
    peak_distance = 0.0

    n_steps = int(round(max_distance_km / step_km))
    for i in range(n_steps + 1):
        d = min(max_distance_km, i * step_km)
        r = skr_per_pulse(
            protocol,
            d,
            alpha_db_km=alpha_db_km,
            eta_det=eta_det,
            dcr_per_gate=dcr_per_gate,
            misalignment=misalignment,
            mu=mu,
            f_ec=f_ec,
            attack_intensity=attack_intensity,
        )
        skr_bps = r["skr_per_pulse"] * clock_hz
        if skr_bps <= 0.0 and cutoff_km is None:
            # Confirm it stays dead (avoid a single noisy zero being the cutoff).
            nxt = skr_per_pulse(
                protocol,
                min(max_distance_km, d + step_km),
                alpha_db_km=alpha_db_km,
                eta_det=eta_det,
                dcr_per_gate=dcr_per_gate,
                misalignment=misalignment,
                mu=mu,
                f_ec=f_ec,
                attack_intensity=attack_intensity,
            )
            if nxt["skr_per_pulse"] * clock_hz <= 0.0:
                cutoff_km = d
        if skr_bps > peak_skr:
            peak_skr = skr_bps
            peak_distance = d
        points.append(
            {
                "distance_km": round(d, 3),
                "skr_bps": skr_bps,
                "qber": r["qber"],
            }
        )

    return {
        "protocol": protocol,
        "curve": points,
        "cutoff_km": cutoff_km,
        "peak_skr_bps": peak_skr,
        "peak_distance_km": peak_distance,
        "params": {
            "alpha_db_km": alpha_db_km,
            "eta_det": eta_det,
            "dcr_per_gate": dcr_per_gate,
            "misalignment": misalignment,
            "mu": mu,
            "f_ec": f_ec,
            "clock_hz": clock_hz,
            "attack_intensity": attack_intensity,
            "sifting_fraction": SIFTING_FRACTION[protocol],
        },
    }
