"""PDF rendering of report snapshots via reportlab.

Kept as a separate module so the (relatively heavy) reportlab import only
happens when a PDF is actually requested. Renders the self-contained
snapshot: header, run summary table, ML classification, AI summary, stage
log, and the key-rate curve as a line chart. Pure function of (title,
payload) — no DB, no request objects, trivially testable.
"""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_ACCENT = colors.HexColor("#0e7c66")
_ALERT = colors.HexColor("#c2410c")
_INK = colors.HexColor("#1f2937")
_MUTED = colors.HexColor("#6b7280")

# Symmetric-log y mapping shared by the chart (mirrors the frontend).
_Y_MAX = 6.0  # log10 ceiling ~ peak-rate scale


def _y(v: float, chart_h: float) -> float:
    if v <= 0:
        return 0.0
    import math

    return min(1.0, math.log10(v + 1) / _Y_MAX) * chart_h


class _KeyRateChart(Flowable):
    """Minimal line chart for the key-rate curves (clean vs attacked)."""

    def __init__(self, keyrate: dict[str, Any], width: float, height: float):
        super().__init__()
        self.keyrate = keyrate
        self.width = width
        self.height = height

    def wrap(self, availWidth: float, availHeight: float):
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        w, h = self.width, self.height
        pad_l, pad_r, pad_t, pad_b = 34, 8, 10, 18
        plot_w = w - pad_l - pad_r
        plot_h = h - pad_t - pad_b

        curves = [
            ("clean", self.keyrate.get("clean_curve") or []),
            ("attacked", self.keyrate.get("attacked_curve") or []),
        ]
        x_max = max(
            (p["distance_km"] for _, pts in curves for p in pts), default=300.0
        ) or 300.0
        x_max = min(x_max, 300.0)

        def px(km: float) -> float:
            return pad_l + (km / x_max) * plot_w

        def py(v: float) -> float:
            return pad_b + _y(v, plot_h)

        # Gridlines at 10^0..10^6 bps.
        canvas.setStrokeColor(colors.HexColor("#d1d5db"))
        canvas.setLineWidth(0.4)
        canvas.setFont("Helvetica", 6)
        canvas.setFillColor(_MUTED)
        for p in range(0, 7):
            v = 10.0**p
            if py(v) > pad_b + plot_h:
                continue
            canvas.line(pad_l, py(v), w - pad_r, py(v))
            label = f"{v/1e6:g}M" if v >= 1e6 else (f"{v/1e3:g}k" if v >= 1e3 else f"{v:g}")
            canvas.drawRightString(pad_l - 3, py(v) - 2, label)

        # Axis frame.
        canvas.setStrokeColor(_INK)
        canvas.setLineWidth(0.8)
        canvas.rect(pad_l, pad_b, plot_w, plot_h, stroke=1, fill=0)

        for key, style in (("clean", _ACCENT), ("attacked", _ALERT)):
            pts = self.keyrate.get(f"{key}_curve") or []
            if len(pts) >= 2:
                path = canvas.beginPath()
                for i, p in enumerate(pts):
                    x_, y_ = px(p["distance_km"]), py(max(0.0, p["skr_bps"]))
                    if i == 0:
                        path.moveTo(x_, y_)
                    else:
                        path.lineTo(x_, y_)
                canvas.setStrokeColor(style)
                canvas.setLineWidth(1.1)
                canvas.drawPath(path, stroke=1, fill=0)

        # Cutoff markers.
        for key, style in (("clean_cutoff_km", _ACCENT), ("attacked_cutoff_km", _ALERT)):
            km = self.keyrate.get(key)
            if km is not None:
                canvas.setStrokeColor(style)
                canvas.setLineWidth(0.6)
                canvas.setDash(2, 2)
                canvas.line(px(km), pad_b, px(km), pad_b + plot_h)
                canvas.setDash()
                canvas.setFont("Helvetica", 6)
                canvas.setFillColor(style)
                canvas.drawString(px(km) + 2, pad_b + plot_h - 7, f"{km:g} km")

        # Axis labels.
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(_MUTED)
        for km in range(0, int(x_max) + 1, 50):
            canvas.drawCentredString(px(km), pad_b - 10, f"{km}")
        canvas.drawCentredString(pad_l + plot_w / 2, pad_b - 16, "distance (km)")
        canvas.saveState()
        canvas.translate(8, pad_b + plot_h / 2)
        canvas.rotate(90)
        canvas.drawCentredString(0, 0, "secret key rate (bps)")
        canvas.restoreState()


def render_report_pdf(title: str, payload: dict[str, Any]) -> bytes:
    """Render one report snapshot to PDF bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=title or "QKD simulation report",
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "H1x", parent=styles["Title"], fontSize=16, textColor=_INK, spaceAfter=2
    )
    sub = ParagraphStyle(
        "Subx", parent=styles["Normal"], fontSize=8.5, textColor=_MUTED, spaceAfter=10
    )
    h2 = ParagraphStyle(
        "H2x", parent=styles["Heading2"], fontSize=11.5, textColor=_ACCENT,
        spaceBefore=12, spaceAfter=4,
    )
    body = ParagraphStyle("Bodyx", parent=styles["Normal"], fontSize=9, leading=13)

    run = payload.get("run", {})
    attack = payload.get("attack", {})
    ml = payload.get("ml") or {}
    story: list[Flowable] = [
        Paragraph(title or "QKD simulation report", h1),
        Paragraph(
            f"Generated {payload.get('created_at', '')} · public read-only report",
            sub,
        ),
    ]

    # ---- Run summary -------------------------------------------------------
    qber = run.get("qber")
    rows = [
        ["Protocol", str(run.get("protocol", "—")).upper()],
        ["Qubits", str(run.get("n_qubits", "—"))],
        ["Seed", str(run.get("seed", "—"))],
        ["QBER", "—" if qber is None else f"{qber * 100:.2f}%"],
        ["Sifted key", f"{run.get('sifted_count', 0)} bits"],
        ["Final key", f"{run.get('final_key_length', 0)} bits"],
        [
            "Outcome",
            ("ABORTED" if run.get("aborted") else "Completed")
            + (f" — {run.get('abort_reason')}" if run.get("abort_reason") else ""),
        ],
        [
            "Attack",
            (attack.get("type") or "none")
            + f" @ {(attack.get('intensity') or 0) * 100:.0f}%"
            + (f" — {attack.get('description')}" if attack.get("description") else ""),
        ],
    ]
    tbl = Table(rows, colWidths=[32 * mm, 128 * mm])
    tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TEXTCOLOR", (0, 0), (0, -1), _INK),
                ("TEXTCOLOR", (1, 0), (1, -1), _INK),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story += [Paragraph("Run summary", h2), tbl]

    # ---- ML classification -------------------------------------------------
    story.append(Paragraph("ML attack classification", h2))
    if ml.get("predicted_class"):
        probs = ml.get("probabilities") or {}
        prob_rows = [["predicted", ml["predicted_class"]]] + [
            [name, f"{p * 100:.1f}%"] for name, p in sorted(
                probs.items(), key=lambda kv: kv[1], reverse=True
            )
        ]
        mt = Table(prob_rows, colWidths=[60 * mm, 30 * mm])
        mt.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
                    ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ]
            )
        )
        story.append(mt)
    else:
        story.append(Paragraph("Classifier artifact not available at snapshot time.", body))

    # ---- AI summary --------------------------------------------------------
    story.append(Paragraph("Summary", h2))
    src = payload.get("summary_source")
    label = {"llm": "AI summary", "fallback": "auto summary"}.get(src, "summary")
    story.append(Paragraph(payload.get("ai_summary") or "Not available.", body))
    story.append(Paragraph(f"<font size=7 color='#6b7280'>({label})</font>", body))

    # ---- Key-rate chart ----------------------------------------------------
    kr = payload.get("keyrate")
    if kr:
        story.append(Paragraph("Secret key rate vs distance", h2))
        chart = _KeyRateChart(kr, width=174 * mm, height=80 * mm)
        story.append(KeepTogether([chart]))
        story.append(
            Paragraph(
                f"Clean-link cutoff {kr.get('clean_cutoff_km', '—')} km · "
                f"attacked cutoff {kr.get('attacked_cutoff_km', '—')} km · "
                f"{str(kr.get('protocol', '')).upper()} sifting model",
                body,
            )
        )

    # ---- Stage log ---------------------------------------------------------
    stages = payload.get("stages") or []
    if stages:
        if len(story) > 8:
            story.append(PageBreak())
        story.append(Paragraph("Stage log", h2))
        for s in stages:
            pl = s.get("payload") or {}
            summary = pl.get("summary") or ""
            story.append(
                Paragraph(
                    f"<b>{s.get('stage_index', 0)}. {s.get('stage_name', '')}</b> — {summary}",
                    body,
                )
            )

    doc.build(story)
    return buf.getvalue()
