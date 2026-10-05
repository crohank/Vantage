"""LLM gateway.

Every test here corresponds to a failure mode of the seven-model waterfall
this replaced. No network: an httpx MockTransport stands in for the provider.
"""

import json

import httpx
import pytest
from pydantic import BaseModel

from vantage.config import get_settings
from vantage.llm.gateway import (
    _BREAKER_THRESHOLD,
    _MAX_ATTEMPTS,
    LLMError,
    LLMGateway,
    LLMNotConfigured,
    LLMResponse,
    LLMUnavailable,
    Provider,
    _gemini_schema,
    _parse_retry_after,
    _strip_fences,
)


class Verdict(BaseModel):
    summary: str
    material: bool


def gemini_body(text: str, *, prompt_tokens: int = 11, completion_tokens: int = 7) -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {
            "promptTokenCount": prompt_tokens,
            "candidatesTokenCount": completion_tokens,
        },
    }


def gateway_with(handler) -> LLMGateway:
    return LLMGateway(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.fixture(autouse=True)
def _keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Backoff is real. Waiting for it in tests is not."""

    async def instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr("vantage.llm.gateway.asyncio.sleep", instant)


class TestHappyPath:
    async def test_returns_text_and_provider_reported_tokens(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["x-goog-api-key"] == "test-gemini-key"
            # The key must not travel in the query string, where it leaks
            # into logs and proxies.
            assert "key=" not in str(request.url)
            return httpx.Response(200, json=gemini_body("a finding"))

        async with gateway_with(handler) as gw:
            result = await gw.complete("prompt")
        assert result.text == "a finding"
        assert result.prompt_tokens == 11
        assert result.completion_tokens == 7
        assert result.tokens_estimated is False
        assert result.attempts == 1

    async def test_marks_tokens_as_estimated_when_provider_omits_usage(self) -> None:
        def handler(_r: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"candidates": [{"content": {"parts": [{"text": "x"}]}}]}
            )

        async with gateway_with(handler) as gw:
            result = await gw.complete("prompt")
        # Cost built on an estimate must never be presented as measured.
        assert result.tokens_estimated is True

    async def test_model_used_is_reported(self) -> None:
        def handler(_r: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=gemini_body("ok"))

        async with gateway_with(handler) as gw:
            result = await gw.complete("prompt", model="gemini-2.5-flash")
        assert result.model == "gemini-2.5-flash"


class TestRateLimiting:
    async def test_429_retries_the_same_model_rather_than_switching(self) -> None:
        # The old client answered a 429 by trying the next model name on the
        # same project quota, which cannot help and burned every attempt.
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            if len(seen) < 3:
                return httpx.Response(429, text="quota exceeded")
            return httpx.Response(200, json=gemini_body("recovered"))

        async with gateway_with(handler) as gw:
            result = await gw.complete("prompt", model="gemini-2.5-flash")

        assert result.text == "recovered"
        assert result.attempts == 3
        assert len({url for url in seen}) == 1, "every retry must hit the same model"

    async def test_gives_up_after_the_attempt_budget(self) -> None:
        def handler(_r: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="quota exceeded")

        async with gateway_with(handler) as gw:
            with pytest.raises(LLMUnavailable, match=f"after {_MAX_ATTEMPTS} attempts"):
                await gw.complete("prompt")

    def test_retry_after_header_is_honoured(self) -> None:
        resp = httpx.Response(429, headers={"retry-after": "7"})
        assert _parse_retry_after(resp) == 7.0

    def test_retry_after_is_capped(self) -> None:
        resp = httpx.Response(429, headers={"retry-after": "99999"})
        parsed = _parse_retry_after(resp)
        assert parsed is not None and parsed <= 30.0

    def test_http_date_retry_after_falls_back_to_a_bounded_wait(self) -> None:
        resp = httpx.Response(429, headers={"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"})
        assert _parse_retry_after(resp) == 30.0


class TestErrorClassification:
    async def test_client_errors_are_not_retried(self) -> None:
        calls = 0

        def handler(_r: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(400, text="malformed request")

        async with gateway_with(handler) as gw:
            with pytest.raises(LLMError):
                await gw.complete("prompt")
        # Resending an identical bad request fails identically.
        assert calls == 1

    async def test_bad_key_is_reported_as_configuration(self) -> None:
        def handler(_r: httpx.Request) -> httpx.Response:
            return httpx.Response(403, text="permission denied")

        async with gateway_with(handler) as gw:
            with pytest.raises(LLMNotConfigured):
                await gw.complete("prompt", fallback=None)

    async def test_server_errors_are_retried(self) -> None:
        calls = 0

        def handler(_r: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls < 3:
                return httpx.Response(503, text="unavailable")
            return httpx.Response(200, json=gemini_body("ok"))

        async with gateway_with(handler) as gw:
            assert (await gw.complete("prompt")).text == "ok"
        assert calls == 3

    async def test_safety_block_with_no_candidates_is_an_error(self) -> None:
        def handler(_r: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})

        async with gateway_with(handler) as gw:
            with pytest.raises(LLMError, match="SAFETY"):
                await gw.complete("prompt")

    async def test_missing_key_raises_before_any_request(self, monkeypatch) -> None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "")
        get_settings.cache_clear()

        def handler(_r: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("must not reach the network")

        async with gateway_with(handler) as gw:
            gw._settings = get_settings().model_copy(update={"gemini_api_key": None})
            with pytest.raises(LLMNotConfigured):
                await gw.complete("prompt")


class TestCircuitBreaker:
    async def test_opens_after_consecutive_failures_and_fails_fast(self) -> None:
        calls = 0

        def handler(_r: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(503, text="down")

        async with gateway_with(handler) as gw:
            for _ in range(_BREAKER_THRESHOLD):
                with pytest.raises(LLMUnavailable):
                    await gw.complete("prompt")
            before = calls
            with pytest.raises(LLMUnavailable, match="circuit breaker open"):
                await gw.complete("prompt")

        # Once open, no further request is issued.
        assert calls == before


class TestFallback:
    async def test_falls_back_to_the_other_provider_once(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if "googleapis" in str(request.url):
                return httpx.Response(503, text="gemini down")
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "from groq"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3},
                },
            )

        async with gateway_with(handler) as gw:
            result = await gw.complete("prompt", fallback=Provider.GROQ)
        assert result.text == "from groq"
        assert result.provider is Provider.GROQ

    async def test_no_fallback_means_the_error_propagates(self) -> None:
        def handler(_r: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="down")

        async with gateway_with(handler) as gw:
            with pytest.raises(LLMUnavailable):
                await gw.complete("prompt", fallback=None)


class TestStructuredOutput:
    async def test_sends_a_schema_and_validates_the_result(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(
                200, json=gemini_body(json.dumps({"summary": "s", "material": True}))
            )

        async with gateway_with(handler) as gw:
            verdict, _ = await gw.complete_structured("prompt", Verdict)

        assert verdict.material is True
        config = captured["generationConfig"]
        assert config["responseMimeType"] == "application/json"
        assert set(config["responseSchema"]["properties"]) == {"summary", "material"}

    async def test_repairs_once_on_invalid_output(self) -> None:
        calls = 0

        def handler(_r: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(200, json=gemini_body('{"summary": "s"}'))
            return httpx.Response(
                200, json=gemini_body(json.dumps({"summary": "s", "material": False}))
            )

        async with gateway_with(handler) as gw:
            verdict, _ = await gw.complete_structured("prompt", Verdict)
        assert verdict.material is False
        assert calls == 2

    async def test_gives_up_after_one_repair(self) -> None:
        def handler(_r: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=gemini_body('{"nope": 1}'))

        async with gateway_with(handler) as gw:
            with pytest.raises(LLMError, match="failed validation twice"):
                await gw.complete_structured("prompt", Verdict)

    async def test_tolerates_fenced_json_from_a_provider_without_schema_support(self) -> None:
        def handler(_r: httpx.Request) -> httpx.Response:
            fenced = '```json\n{"summary": "s", "material": true}\n```'
            return httpx.Response(200, json=gemini_body(fenced))

        async with gateway_with(handler) as gw:
            verdict, _ = await gw.complete_structured("prompt", Verdict)
        assert verdict.summary == "s"


class TestSchemaConversion:
    def test_inlines_refs_that_gemini_rejects(self) -> None:
        class Inner(BaseModel):
            a: str

        class Outer(BaseModel):
            inner: Inner
            maybe: int | None = None

        blob = json.dumps(_gemini_schema(Outer))
        assert "$defs" not in blob
        assert "$ref" not in blob

    def test_preserves_nested_field_names(self) -> None:
        class Inner(BaseModel):
            a: str

        class Outer(BaseModel):
            items: list[Inner]

        schema = _gemini_schema(Outer)
        assert schema["properties"]["items"]["items"]["properties"].keys() == {"a"}

    def test_optional_becomes_nullable(self) -> None:
        class Outer(BaseModel):
            maybe: int | None = None

        assert _gemini_schema(Outer)["properties"]["maybe"]["nullable"] is True


class TestFenceStripping:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ('{"a":1}', '{"a":1}'),
            ('```json\n{"a":1}\n```', '{"a":1}'),
            ('```\n{"a":1}\n```', '{"a":1}'),
            ("  plain text  ", "plain text"),
        ],
    )
    def test_strips_known_wrappings(self, raw: str, expected: str) -> None:
        assert _strip_fences(raw) == expected


class TestTelemetryHook:
    async def test_every_call_is_reported_with_its_agent(self) -> None:
        # The old service took agent_name as an optional kwarg that three of
        # four call sites omitted, so telemetry could not be joined to a run.
        seen: list[tuple[str, str]] = []

        async def record(response: LLMResponse, agent: str) -> None:
            seen.append((agent, response.model))

        def handler(_r: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=gemini_body("ok"))

        async with gateway_with(handler) as gw:
            gw.on_call = record
            await gw.complete("prompt", agent="explain_change")

        assert len(seen) == 1
        assert seen[0][0] == "explain_change"
