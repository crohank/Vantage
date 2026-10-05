"""The generative step and its grounding guard.

Offline, against a fake gateway. The guard is the point: an explanation that
asserts a figure the filing does not contain is discarded, because a
plausible sentence about a number nobody wrote is the exact failure this
project exists to avoid.
"""

from __future__ import annotations

import json

import pytest

from vantage.domain.filing import FilingSection, SectionId, Span
from vantage.domain.finding import (
    ChangeType,
    Finding,
    FindingKind,
    Materiality,
    Provenance,
)
from vantage.engines.explain import (
    Explanation,
    explain,
    explain_one,
    ungrounded_numbers,
)
from vantage.llm.gateway import LLMResponse, LLMUnavailable, Provider

ACCESSION = "0000320193-25-000079"
TEXT = "Two customers accounted for 39% of net sales in 2025, up from 31%."


def section(text: str = TEXT) -> FilingSection:
    return FilingSection(
        accession=ACCESSION,
        cik="0000320193",
        section_id=SectionId.RISK_FACTORS,
        heading="Item 1A. Risk Factors",
        order=0,
        text=text,
    )


def finding(score: float = 0.8, text: str = TEXT) -> Finding:
    sec = section(text)
    return Finding(
        id=f"f-{score}-{len(text)}",
        kind=FindingKind.DIFF,
        cik="0000320193",
        ticker="AAPL",
        section_id=SectionId.RISK_FACTORS,
        change_type=ChangeType.ADDED,
        current_span=Span.from_section(sec, 0, len(text)),
        current_accession=ACCESSION,
        materiality=Materiality(score=score),
        provenance=Provenance(git_sha="test"),
    )


class FakeGateway:
    def __init__(self, payload: object = None, *, raises: Exception | None = None) -> None:
        self.payload = payload
        self.raises = raises
        self.calls = 0

    def is_configured(self, provider: Provider) -> bool:
        return True

    async def complete(self, prompt: str, **kw: object) -> LLMResponse:
        self.calls += 1
        if self.raises:
            raise self.raises
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return LLMResponse(
            text=text,
            model="fake-model",
            provider=Provider.GEMINI,
            prompt_tokens=10,
            completion_tokens=10,
            latency_ms=1.0,
        )


GOOD = {
    "summary": "Customer concentration rose to 39% of net sales.",
    "rationale": "Two customers now account for 39%, up from 31%.",
    "topic": "concentration",
}


class TestUngroundedNumbers:
    def test_figures_present_in_the_source_are_fine(self) -> None:
        e = Explanation(**GOOD)
        assert ungrounded_numbers(e, TEXT) == set()

    def test_catches_a_fabricated_figure(self) -> None:
        e = Explanation(
            summary="Customer concentration rose to 72% of net sales.",
            rationale="Two customers now account for 72%.",
            topic="concentration",
        )
        assert ungrounded_numbers(e, TEXT) == {"72"}

    def test_ignores_single_digits(self) -> None:
        # "two customers" and ordinary prose numerals are too common to flag.
        e = Explanation(
            summary="Two customers dominate.", rationale="Only 2 matter.", topic="concentration"
        )
        assert ungrounded_numbers(e, TEXT) == set()

    def test_normalises_currency_and_separators(self) -> None:
        e = Explanation(summary="A $1,200 charge.", rationale="It is 1200.", topic="financial")
        assert ungrounded_numbers(e, "The charge was $1,200 in total.") == set()


class TestExplainOne:
    async def test_attaches_summary_rationale_and_model_provenance(self) -> None:
        result = await explain_one(FakeGateway(GOOD), finding())  # type: ignore[arg-type]
        assert result.summary == GOOD["summary"]
        assert result.rationale == GOOD["rationale"]
        assert result.provenance.model == "fake-model"
        assert result.provenance.prompt_name == "explain"

    async def test_discards_an_explanation_that_invents_a_figure(self) -> None:
        bad = {
            "summary": "Concentration reached 72% of sales.",
            "rationale": "Up sharply.",
            "topic": "concentration",
        }
        result = await explain_one(FakeGateway(bad), finding())  # type: ignore[arg-type]
        # The finding survives; only the sentence about it is dropped. The
        # quoted span is still true.
        assert result.summary == ""
        assert result.current_span is not None

    async def test_survives_a_provider_outage(self) -> None:
        result = await explain_one(  # type: ignore[arg-type]
            FakeGateway(raises=LLMUnavailable("gemini is down")), finding()
        )
        assert result.summary == ""

    async def test_survives_an_unexpected_exception(self) -> None:
        # The docstring promises it never raises, so it must also hold for
        # errors that are not LLMError, such as a transport failure.
        result = await explain_one(  # type: ignore[arg-type]
            FakeGateway(raises=RuntimeError("socket exploded")), finding()
        )
        assert result.summary == ""

    async def test_survives_an_unusable_response_shape(self) -> None:
        result = await explain_one(FakeGateway("not json at all"), finding())  # type: ignore[arg-type]
        assert result.summary == ""

    async def test_rejects_a_response_missing_required_fields(self) -> None:
        result = await explain_one(FakeGateway({"summary": "only this"}), finding())  # type: ignore[arg-type]
        assert result.summary == ""


class TestExplainBatch:
    async def test_explains_only_the_most_material(self) -> None:
        # Explaining all of a 200-finding run would cost more than the rest
        # of the pipeline and nobody reads past the top.
        findings = [
            finding(score=s, text=TEXT + " " * i) for i, s in enumerate([0.9, 0.8, 0.7, 0.6])
        ]
        gateway = FakeGateway(GOOD)
        result = await explain(gateway, findings, limit=2)  # type: ignore[arg-type]

        assert gateway.calls == 2
        assert sum(1 for f in result if f.summary) == 2

    async def test_preserves_input_order(self) -> None:
        findings = [finding(score=s, text=TEXT + " " * i) for i, s in enumerate([0.1, 0.9, 0.5])]
        result = await explain(FakeGateway(GOOD), findings, limit=3)  # type: ignore[arg-type]
        assert [f.id for f in result] == [f.id for f in findings]

    async def test_empty_input_makes_no_calls(self) -> None:
        gateway = FakeGateway(GOOD)
        assert await explain(gateway, [], limit=5) == []  # type: ignore[arg-type]
        assert gateway.calls == 0


class TestGatewayConfiguration:
    @pytest.mark.parametrize("value", ["", "   "])
    def test_a_blank_key_is_not_configured(
        self, value: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # An unset variable parses to SecretStr("") rather than None. Reading
        # that as configured meant Groq was sent a bare "Bearer " header,
        # which httpx refuses to serialise, crashing the run.
        from vantage.config import get_settings
        from vantage.llm.gateway import LLMGateway

        monkeypatch.setenv("GROQ_API_KEY", value)
        get_settings.cache_clear()
        try:
            assert LLMGateway().is_configured(Provider.GROQ) is False
        finally:
            get_settings.cache_clear()

    def test_a_real_key_is_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from vantage.config import get_settings
        from vantage.llm.gateway import LLMGateway

        monkeypatch.setenv("GROQ_API_KEY", "gsk_realish")
        get_settings.cache_clear()
        try:
            assert LLMGateway().is_configured(Provider.GROQ) is True
        finally:
            get_settings.cache_clear()
