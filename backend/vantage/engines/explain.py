"""The generative half.

The aligner has already located the change. This step only classifies and
explains one, which is the whole point of the split: the model is never
asked to find anything, so it is never in a position to invent one.

Everything it produces is checked against the quoted text before it is kept.
An explanation that introduces a figure the filing does not contain is
discarded, because a plausible sentence about a number nobody wrote is the
exact failure this project exists to avoid.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from vantage.domain.finding import ChangeType, Finding
from vantage.llm.gateway import LLMError, LLMGateway, Provider

log = logging.getLogger(__name__)

# Explaining every change in a 200-finding run would cost more than the rest
# of the pipeline combined and nobody reads past the top of the list.
DEFAULT_LIMIT = 12

# Schema-constrained output. The previous system asked for JSON in prose and
# then split the reply on markdown fences.
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "One sentence, under 30 words, naming what changed.",
        },
        "rationale": {
            "type": "string",
            "description": "One or two sentences on why a reader should care.",
        },
        "topic": {
            "type": "string",
            "enum": [
                "regulation",
                "litigation",
                "competition",
                "supply_chain",
                "concentration",
                "financial",
                "cybersecurity",
                "personnel",
                "accounting",
                "other",
            ],
        },
    },
    "required": ["summary", "rationale", "topic"],
}

PROMPT = """You are reading one paragraph that changed between a company's \
two most recent annual filings. The change has already been located. Do not \
look for other changes.

Company: {ticker}
Section: {section}
Change: {change}

{body}

Describe this change in the given JSON shape.

Rules:
- Use only what the text above says. Introduce no figure, date, company or \
fact that does not appear in it.
- If the change is purely stylistic, say so plainly.
- Do not advise, predict, or say whether it is good or bad for the company.
"""


class Explanation(BaseModel):
    summary: str = Field(max_length=400)
    rationale: str = Field(max_length=800)
    topic: str


# Figures written in the explanation but absent from the source, which is the
# cheapest reliable way to catch a fabricated number. Matches percentages,
# money and bare numerals of two or more digits; single digits appear too
# often in ordinary prose to be worth flagging.
_NUMBER = re.compile(r"\$?\d[\d,]*\.?\d*%?")


def _numbers(text: str) -> set[str]:
    found = set()
    for raw in _NUMBER.findall(text):
        cleaned = raw.strip("$%").replace(",", "").rstrip(".")
        if cleaned and (len(cleaned.replace(".", "")) > 1):
            found.add(cleaned)
    return found


def ungrounded_numbers(explanation: Explanation, source: str) -> set[str]:
    """Figures the explanation asserts that the source text does not contain."""
    said = _numbers(f"{explanation.summary} {explanation.rationale}")
    had = _numbers(source)
    return said - had


def _body(finding: Finding) -> str:
    current = finding.current_span.quote if finding.current_span else ""
    prior = finding.prior_span.quote if finding.prior_span else ""

    if finding.change_type is ChangeType.REWORDED and prior and current:
        return f"Before:\n{prior}\n\nAfter:\n{current}"
    if finding.change_type is ChangeType.REMOVED and prior:
        return f"Removed text:\n{prior}"
    return f"Added text:\n{current or prior}"


def _source_text(finding: Finding) -> str:
    parts = [
        finding.current_span.quote if finding.current_span else "",
        finding.prior_span.quote if finding.prior_span else "",
    ]
    return "\n".join(p for p in parts if p)


async def explain_one(
    gateway: LLMGateway, finding: Finding, *, model: str | None = None
) -> Finding:
    """Explain one finding, or return it untouched.

    Never raises. An explanation is an enhancement to a finding that is
    already valid on its own, so a provider outage degrades the output rather
    than failing the run.
    """
    prompt = PROMPT.format(
        ticker=finding.ticker,
        section=finding.section_id.value.replace("_", " "),
        change=(finding.change_type.value if finding.change_type else finding.kind.value),
        body=_body(finding),
    )

    try:
        response = await gateway.complete(
            prompt,
            model=model,
            temperature=0.1,
            max_output_tokens=512,
            response_schema=RESPONSE_SCHEMA,
            agent="explain",
            fallback=Provider.GROQ,
        )
    except LLMError as exc:
        log.warning("explain failed for %s: %s", finding.id, exc)
        return finding
    except Exception as exc:
        # Deliberately broad. This is an enhancement to a finding that is
        # already valid, so nothing it can do should fail the run.
        log.warning("explain raised unexpectedly for %s: %s", finding.id, exc)
        return finding

    try:
        explanation = Explanation.model_validate_json(response.text)
    except ValidationError as exc:
        log.warning("explain returned an unusable shape for %s: %s", finding.id, exc)
        return finding

    invented = ungrounded_numbers(explanation, _source_text(finding))
    if invented:
        # Drop the explanation, keep the finding. The quoted span is still
        # true; only the sentence about it was not.
        log.warning(
            "discarding explanation for %s, it asserts figures absent from the filing: %s",
            finding.id,
            sorted(invented),
        )
        return finding

    return finding.model_copy(
        update={
            "summary": explanation.summary,
            "rationale": explanation.rationale,
            "provenance": finding.provenance.model_copy(
                update={"model": response.model, "prompt_name": "explain", "prompt_version": 1}
            ),
        }
    )


async def explain(
    gateway: LLMGateway,
    findings: list[Finding],
    *,
    limit: int = DEFAULT_LIMIT,
    model: str | None = None,
) -> list[Finding]:
    """Explain the most material findings, concurrently.

    Returns the full list in its original order, with the explained ones
    replaced.
    """
    ranked = sorted(findings, key=lambda f: f.materiality.score, reverse=True)
    chosen = {f.id for f in ranked[:limit]}
    if not chosen:
        return findings

    explained = await asyncio.gather(
        *(explain_one(gateway, f, model=model) for f in findings if f.id in chosen)
    )
    by_id = {f.id: f for f in explained}
    return [by_id.get(f.id, f) for f in findings]
