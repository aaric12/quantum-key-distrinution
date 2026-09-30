"""AI plain-language summaries of completed QKD runs.

Given a finished run's essentials (protocol, QBER, attack type/intensity,
ML classification, abort state), produce a short educational explanation of
the run. Both paths follow the same four-part structure:

1. **What happened** — the outcome in plain language.
2. **Why it happened** — the mechanism, tied to this run's actual numbers.
3. **What it means for security** — the abort decision and why the ~11%
   line is the accepted threshold for this protocol class.
4. **A one-line pointer back to theory** — which educational page deepens
   the exact concept this run demonstrated.

Server-side only: the LLM API key lives in the ``OPENAI_API_KEY`` env var
and is never sent to the browser.

Any OpenAI-compatible chat-completions API works — configure via
``OPENAI_BASE_URL`` + ``OPENAI_MODEL`` (Groq, Together, a local vLLM, ...).
When no key is configured (or the call fails), a deterministic template
summary is returned instead so the Simulate page always has something to
show; the response carries ``summary_source: "llm" | "fallback"`` so the UI
can be honest about where the words came from.

Timeouts are tight (5 s connect / 15 s total): a summary is a nice-to-have
glazed over a completed simulation, never a reason to hang the request.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings

TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)

_SYSTEM_PROMPT = (
    "You explain quantum key distribution simulations to students learning "
    "the physics. You are given the facts of one completed run. Reply with a "
    "short explanation in plain prose (two short paragraphs at most, no "
    "markdown, no lists, no headings) covering exactly these four points: "
    "(1) What happened: the outcome in plain language. "
    "(2) Why it happened: connect the specific numbers to the underlying "
    "mechanism — do not merely restate the numbers. For example, an "
    "intercept-resend attacker must guess a basis and guesses wrong on half "
    "of the qubits she intercepts; a wrong-basis measurement re-prepares the "
    "qubit so Bob's bit becomes a coin flip, which is why QBER lands near "
    "intensity/4 rather than intensity/2. "
    "(3) What it means for security: whether the run aborted or the key "
    "survived, and in one clause why the ~11% QBER abort line is the "
    "accepted threshold for this protocol class (above it, privacy "
    "amplification can no longer guarantee Eve's information is squeezed "
    "out). "
    "(4) End with exactly one sentence starting 'If you're learning this:' "
    "pointing to the relevant theory page — the BB84 or B92 protocol page, "
    "Foundations, Comparison, or the Glossary entry for the attack involved. "
    "Never invent numbers that are not in the facts."
)


def build_summary_prompt(run_facts: dict[str, Any]) -> str:
    """Render the run's facts as the user-side prompt."""
    lines = [f"{key}: {value}" for key, value in run_facts.items()]
    return "\n".join(lines)


def _pct(x: float) -> str:
    """Format a fraction as a percentage string, e.g. 0.2537 -> '25.4%'."""
    return f"{x * 100:.1f}%"


def _mechanism_sentence(
    attack: str | None,
    protocol: str,
    intensity: float,
    qber: float,
    noise: float,
    pns_stats: dict[str, Any] | None = None,
) -> str:
    """The 'why it happened' part: mechanism tied to this run's numbers.

    Real reasoning per attack type and per protocol — never a generic
    'attack detected' string.
    """
    if attack == "intercept_resend":
        wrong_basis = intensity / 2  # Eve guesses Alice's basis wrongly half the time
        if protocol == "b92":
            # B92: wrong-basis outcomes are often conclusive-but-wrong, so the
            # damage per attacked qubit is ~intensity/3 (see scripts/test_attacks).
            expected = intensity / 3
            b92_note = (
                " B92 runs hotter than BB84: a wrong-basis measurement here "
                "frequently yields a conclusive-but-wrong bit instead of a "
                "discard, so the error rate approaches intensity/3 rather "
                "than intensity/4."
            )
        else:
            expected = intensity / 4
            b92_note = ""
        return (
            f"Eve intercepted {_pct(intensity)} of the pulses and measured "
            f"each in a basis she guessed: half those guesses are wrong, and "
            f"a wrong-basis measurement destroys the state and re-prepares "
            f"it in her basis, turning Bob's eventual bit into a coin flip. "
            f"That is why the QBER lands near "
            f"{'intensity/3' if protocol == 'b92' else 'intensity/4'} ≈ "
            f"{_pct(expected)} (measured: {_pct(qber)}) — from "
            f"{_pct(wrong_basis)} disturbed pulses, only the ones that also "
            f"survived sifting show up as errors — not intensity/2."
            f"{b92_note}"
        )
    if attack == "pns":
        base = (
            "PNS is the quiet attack: Eve performs a number-resolving "
            "measurement, splits multi-photon pulses, keeps one photon for "
            "after the basis announcement, and suppresses the pulses she "
            "siphoned — every bit that survives sifting is error-free"
        )
        detail = ""
        if pns_stats:
            levels = pns_stats.get("levels") or []
            rates = [
                (lvl.get("mu", 0.0), lvl.get("loss_rate", 0.0))
                for lvl in levels
                if lvl.get("sent")
            ]
            spread = pns_stats.get("observed_spread")
            floor = pns_stats.get("noise_floor")
            z = pns_stats.get("anomaly_z")
            if rates:
                table = ", ".join(f"μ={mu:.3g} → {_pct(lr)} loss" for mu, lr in rates)
                detail += f" (QBER {_pct(qber)} on those bits). This run's decoy loss rates: {table}"
            else:
                detail += f" (QBER {_pct(qber)} on those bits)"
            if spread is not None and floor is not None and floor > 0:
                detail += (
                    f" — a loss spread of {spread:.3f} against a binomial "
                    f"noise floor of {floor:.3f}"
                )
                if z is not None:
                    verdict = "well past" if z > 3.0 else "within"
                    detail += f" ({z:.1f}σ, {verdict} the 3σ decoy flag)"
                detail += "."
            else:
                detail += "; this run's decoy table stayed inside the noise floor."
        else:
            detail += f" (QBER {_pct(qber)} on those bits)"
        return (
            base
            + detail
            + " Her only unavoidable footprint is *which* pulses vanish: "
            "honest loss is intensity-independent, but suppression tied to "
            "multi-photon richness varies with intensity, so the per-level "
            "loss rates diverge — that is the whole point of decoy states."
        )
    if attack == "trojan":
        return (
            f"Trojan-horse probing drives light into Alice's own apparatus "
            f"and reads modulator reflections; in this model that appears as "
            f"localized error patches — a fixed 20% of transmission blocks "
            f"flip bits at 0.5×intensity — so errors cluster in space "
            f"instead of scattering uniformly, and QBER lands at "
            f"{_pct(qber)} (intensity {intensity:.0%}), far below "
            f"intercept-resend's at the same knob. That quietness is exactly "
            f"what makes THA dangerous in practice."
        )
    if noise > 0:
        return (
            f"The channel was noisy but clean: each pulse independently "
            f"flipped with probability {_pct(noise)}, and those random flips "
            f"— not an eavesdropper — are what the QBER sample measured. "
            f"Plain noise of this kind is fully recoverable: error "
            f"correction repairs it and privacy amplification charges for "
            f"the parity bits revealed along the way."
        )
    return (
        "The channel was clean and no attack ran: Alice and Bob happened to "
        "choose matching bases on about half the transmissions (sifting), "
        "and the QBER sample over the rest found essentially no errors — "
        "the ideal-channel outcome."
    )


def _security_sentence(
    aborted: bool, qber: float, pns_stats: dict[str, Any] | None = None
) -> str:
    """The 'what it means for security' part: verdict + why the 11% line.

    For PNS runs the decoy-state verdict is folded in: the pipeline aborts
    on QBER alone, so a flagged-but-not-aborted PNS run must say plainly
    that the decoy statistics — not the QBER — are what give Eve away.
    """
    flagged = bool((pns_stats or {}).get("flagged"))
    z = (pns_stats or {}).get("anomaly_z")
    if aborted:
        return (
            f"Security verdict: aborted — measured QBER {_pct(qber)} crossed "
            f"the ~11% line, the boundary beyond which observed errors can "
            f"no longer be explained by honest channel noise alone, so Alice "
            f"and Bob must assume Eve's information about the sifted key "
            f"exceeds what privacy amplification can remove, and the key is "
            f"discarded."
        )
    verdict = (
        f"Security verdict: the key survived — measured QBER {_pct(qber)} "
        f"sits below the ~11% abort line, the point beyond which the "
        f"protocol can no longer bound how much Eve knows; under it, error "
        f"correction repairs the damage and privacy amplification compresses "
        f"the key by enough to erase any partial information she holds."
    )
    if flagged:
        verdict += (
            f" But note: the decoy-state analysis flagged PNS ({z:.1f}σ past "
            f"the noise floor) even though the QBER test passed — a real "
            f"link would treat this key as compromised, because QBER alone "
            f"can never see this attack."
        )
    return verdict


def _pointer_sentence(attack: str | None, protocol: str) -> str:
    """One-line callout connecting the run back to the relevant theory page."""
    if attack == "pns":
        return (
            "If you're learning this: see the Glossary's photon-number-"
            "splitting and decoy-states entries for why QBER alone never "
            "catches this attack."
        )
    if attack == "trojan":
        return (
            "If you're learning this: see the Glossary's Trojan-horse entry "
            "for why error clustering, not the QBER level, is the signature "
            "to look for."
        )
    if attack == "intercept_resend":
        page = "the B92 protocol page" if protocol == "b92" else "the BB84 protocol page"
        return (
            f"If you're learning this: see {page}'s attack notes for why "
            f"basis randomization turns Eve's measurement into a "
            f"{'~33%' if protocol == 'b92' else '~25%'} QBER signature."
        )
    if protocol == "b92":
        return (
            "If you're learning this: see the B92 protocol page for why "
            "conclusive-outcome sifting keeps only a quarter of the bits."
        )
    return (
        "If you're learning this: see the BB84 protocol page for why "
        "sifting exists and what the 11% threshold protects."
    )


def _fallback_summary(run_facts: dict[str, Any]) -> str:
    """Deterministic template summary used when no LLM is configured.

    Builds a real explanation from the actual run values — per-attack and
    per-protocol mechanism reasoning, not a generic 'attack detected'
    string — in the same four-part structure the LLM is asked to follow:
    what happened, why it happened, security verdict, theory pointer.
    """
    protocol = str(run_facts.get("protocol", "bb84")).lower()
    proto = protocol.upper()
    qber = float(run_facts.get("qber") or 0.0)
    attack = run_facts.get("attack_type") or None
    intensity = float(run_facts.get("attack_intensity") or 0.0)
    noise = float(run_facts.get("noise") or 0.0)
    ml = run_facts.get("ml_predicted_class")
    aborted = bool(run_facts.get("aborted"))
    final_key_length = run_facts.get("final_key_length")
    sifted_count = run_facts.get("sifted_count")
    pns_stats = run_facts.get("pns_stats")
    attack_label = (attack or "no attack").replace("_", " ")

    # --- Part 1: what happened (in plain language) -------------------------
    key_bits = final_key_length if final_key_length is not None else 0
    if aborted:
        what = (
            f"This {proto} run was aborted: the measured QBER of {_pct(qber)} "
            f"crossed the 11% security threshold, so the channel is treated "
            f"as compromised and no key was kept."
        )
    else:
        attacked = f" under a {attack_label} attack" if attack else ""
        what = (
            f"This {proto} run{attacked} established a shared secret key of "
            f"{key_bits} bits from {sifted_count if sifted_count is not None else 0} "
            f"sifted bits, at a measured QBER of {_pct(qber)}."
        )

    # --- Part 2: why it happened (mechanism, per attack/protocol) ----------
    why = _mechanism_sentence(attack, protocol, intensity, qber, noise, pns_stats)

    # --- Part 3: security verdict ------------------------------------------
    security = _security_sentence(aborted, qber, pns_stats)

    # --- Part 4: theory-page pointer ----------------------------------------
    pointer = _pointer_sentence(attack, protocol)

    # Optional ML cross-check, folded in when it adds information.
    ml_note = ""
    if ml and ml not in ("none", "unknown"):
        if attack and ml == attack:
            ml_note = (
                f" The ML classifier independently identified the traffic as "
                f"{str(ml).replace('_', ' ')}."
            )
        else:
            ml_note = (
                f" The ML classifier flagged the traffic as "
                f"{str(ml).replace('_', ' ')}."
            )

    return f"{what} {why} {ml_note} {security} {pointer}".strip()


async def summarize_run(run_facts: dict[str, Any]) -> dict[str, str]:
    """Return ``{"summary": str, "summary_source": "llm" | "fallback"}``.

    ``run_facts`` keys: protocol, qber, attack_type, attack_intensity,
    aborted, abort_reason, ml_predicted_class, ml_probabilities,
    sifted_count, final_key_length, and optionally noise and pns_stats
    (the PNS decoy-loss table when that attack ran).
    """
    settings = get_settings()

    if not settings.openai_api_key:
        return {"summary": _fallback_summary(run_facts), "summary_source": "fallback"}

    payload = {
        "model": settings.openai_model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": build_summary_prompt(run_facts)},
        ],
        "max_tokens": 400,
        "temperature": 0.4,
    }
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            summary = " ".join(str(content).split())
            if not summary:
                raise ValueError("empty completion")
            return {"summary": summary, "summary_source": "llm"}
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        # Degrade gracefully: a broken/unauthorized LLM must never break the
        # run endpoint that already succeeded.
        return {"summary": _fallback_summary(run_facts), "summary_source": "fallback"}
