"""AI plain-language summaries of completed QKD runs.

Given a finished run's essentials (protocol, QBER, attack type/intensity,
ML classification, abort state), asks an LLM for a 2-4 sentence explanation
in plain language. Server-side only: the API key lives in the ``OPENAI_API_KEY``
env var and is never sent to the browser.

Any OpenAI-compatible chat-completions API works — configure via
``OPENAI_BASE_URL`` + ``OPENAI_MODEL`` (Groq, Together, a local vLLM, ...).
When no key is configured (or the call fails), a deterministic rule-based
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
    "You explain quantum key distribution simulations to non-experts. "
    "You are given the facts of one completed run. Reply with 2-4 short "
    "sentences of plain language: what happened, whether the key is safe "
    "or the run aborted, and what the attack (if any) means. No markdown, "
    "no lists, no preamble — plain prose only. Never invent numbers that "
    "are not in the facts."
)


def build_summary_prompt(run_facts: dict[str, Any]) -> str:
    """Render the run's facts as the user-side prompt."""
    lines = [f"{key}: {value}" for key, value in run_facts.items()]
    return "\n".join(lines)


def _fallback_summary(run_facts: dict[str, Any]) -> str:
    """Deterministic rule-based summary used when no LLM is configured.

    Keeps the feature functional (and testable) with zero external deps.
    """
    protocol = str(run_facts.get("protocol", "QKD")).upper()
    qber = float(run_facts.get("qber") or 0.0)
    attack = run_facts.get("attack_type") or "no attack"
    intensity = float(run_facts.get("attack_intensity") or 0.0)
    ml = run_facts.get("ml_predicted_class")
    aborted = bool(run_facts.get("aborted"))

    parts: list[str] = []
    if aborted:
        parts.append(
            f"This {protocol} run was aborted: the measured QBER of "
            f"{qber * 100:.1f}% crossed the 11% security threshold, so the "
            "channel is treated as compromised and no key was kept."
        )
    else:
        parts.append(
            f"This {protocol} run established a shared secret key with a "
            f"measured QBER of {qber * 100:.1f}%, comfortably within the "
            "security threshold."
        )
    if attack == "no attack":
        parts.append("The channel was clean — no eavesdropper was simulated.")
    else:
        spelled = attack.replace("_", " ")
        article = "An" if spelled[0].lower() in "aeiou" else "A"
        parts.append(f"{article} {spelled} attack ran at intensity {intensity:.0%}.")
    if ml and ml not in ("none", attack):
        parts.append(f"The ML classifier flagged the traffic as {ml.replace('_', ' ')}.")
    elif ml == attack and attack != "no attack":
        parts.append(
            f"The ML classifier independently identified the attack as "
            f"{ml.replace('_', ' ')}."
        )
    return " ".join(parts[:4])


async def summarize_run(run_facts: dict[str, Any]) -> dict[str, str]:
    """Return ``{"summary": str, "summary_source": "llm" | "fallback"}``.

    ``run_facts`` keys: protocol, qber, attack_type, attack_intensity,
    aborted, abort_reason, ml_predicted_class, ml_probabilities,
    sifted_count, final_key_length.
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
        "max_tokens": 160,
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
