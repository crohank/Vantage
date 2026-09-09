"""LLM access: one primary per task, one declared fallback, real backoff.

Replaces a seven-name model waterfall that walked
gemini-2.5-flash to gemini-pro on any failure. Three things were wrong with
that, and they are the requirements this module is written against:

- A 429 advanced to a *different model on the same project quota*, so a rate
  limit burned all seven attempts instead of waiting. Rate limits need
  backoff, not a different model.
- Success mutated the shared client's model name, so one 404 silently
  repointed every later call in the process. Which model answered was not
  knowable after the fact.
- JSON came from asking for it and splitting on markdown fences. Providers
  offer schema-constrained decoding; using it removes a whole class of parse
  failure.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from vantage.config import get_settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GROQ_BASE = "https://api.groq.com/openai/v1"

# Providers answer 429 with Retry-After sometimes and nothing other times.
# These bound the wait when the header is missing.
_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 30.0
_MAX_ATTEMPTS = 4

# After this many consecutive failures the provider is considered down and
# calls fail fast until the cooldown expires. Without it, a provider outage
# turns every request into four slow retries.
_BREAKER_THRESHOLD = 5
_BREAKER_COOLDOWN_SECONDS = 60.0


class Provider(StrEnum):
    GEMINI = "gemini"
    GROQ = "groq"


class LLMError(RuntimeError):
    pass


class LLMNotConfigured(LLMError):
    """No API key for the requested provider."""


class LLMRateLimited(LLMError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMUnavailable(LLMError):
    """5xx, transport failure, or an open circuit breaker."""


class LLMResponse(BaseModel):
    """One completion plus what it cost.

    Token counts come from the provider when reported. `tokens_estimated`
    records when they did not, so cost figures are never silently presented as
    measured when they were inferred from character count.
    """

    text: str
    model: str
    provider: Provider
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tokens_estimated: bool = False
    latency_ms: float = 0.0
    attempts: int = 1

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class _Breaker:
    failures: int = 0
    opened_at: float | None = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= _BREAKER_THRESHOLD:
            self.opened_at = time.monotonic()

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    @property
    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.monotonic() - self.opened_at >= _BREAKER_COOLDOWN_SECONDS:
            # Allow one probe through rather than resetting outright, so a
            # provider that is still down reopens on the next failure.
            self.opened_at = None
            self.failures = _BREAKER_THRESHOLD - 1
            return False
        return True


def estimate_tokens(text: str) -> int:
    """Rough count for providers that report none. About 4 chars per token."""
    return max(1, len(text) // 4)


class LLMGateway:
    """Provider-agnostic completion with retry, breaker and structured output."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._settings = get_settings()
        self._client = client
        self._owns_client = client is None
        self._breakers: dict[Provider, _Breaker] = {p: _Breaker() for p in Provider}
        # Set by callers that want every call attributed to a run. The old
        # code took these as optional kwargs that three of four call sites
        # forgot, so most telemetry landed with a null analysis id.
        self.on_call: Callable[[LLMResponse, str], Awaitable[None]] | None = None

    async def __aenter__(self) -> LLMGateway:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("LLMGateway must be used as an async context manager")
        return self._client

    def is_configured(self, provider: Provider) -> bool:
        if provider is Provider.GEMINI:
            return self._settings.gemini_api_key is not None
        return self._settings.groq_api_key is not None

    async def complete(
        self,
        prompt: str,
        *,
        provider: Provider = Provider.GEMINI,
        model: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 2048,
        response_schema: dict[str, Any] | None = None,
        agent: str = "unknown",
        fallback: Provider | None = None,
    ) -> LLMResponse:
        """One completion.

        `fallback` is a single declared alternative used only when the primary
        provider is unconfigured or its breaker is open. It is deliberately
        not a chain.
        """
        try:
            return await self._complete_on(
                provider,
                prompt,
                model=model,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_schema=response_schema,
                agent=agent,
            )
        except (LLMNotConfigured, LLMUnavailable) as exc:
            if fallback is None or fallback is provider:
                raise
            log.warning("provider %s unavailable (%s), falling back to %s", provider, exc, fallback)
            return await self._complete_on(
                fallback,
                prompt,
                model=None,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_schema=response_schema,
                agent=agent,
            )

    async def _complete_on(
        self,
        provider: Provider,
        prompt: str,
        *,
        model: str | None,
        temperature: float,
        max_output_tokens: int,
        response_schema: dict[str, Any] | None,
        agent: str,
    ) -> LLMResponse:
        if not self.is_configured(provider):
            raise LLMNotConfigured(f"no API key configured for {provider.value}")

        breaker = self._breakers[provider]
        if breaker.is_open:
            raise LLMUnavailable(
                f"{provider.value} circuit breaker open after "
                f"{_BREAKER_THRESHOLD} consecutive failures"
            )

        started = time.monotonic()
        last_error: Exception | None = None

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                if provider is Provider.GEMINI:
                    response = await self._call_gemini(
                        prompt, model, temperature, max_output_tokens, response_schema
                    )
                else:
                    response = await self._call_groq(
                        prompt, model, temperature, max_output_tokens, response_schema
                    )
                breaker.record_success()
                response.latency_ms = (time.monotonic() - started) * 1000
                response.attempts = attempt
                if self.on_call is not None:
                    await self.on_call(response, agent)
                return response

            except LLMRateLimited as exc:
                last_error = exc
                if attempt == _MAX_ATTEMPTS:
                    break
                # Honour the provider's own guidance when present. Retrying a
                # rate limit against a different model on the same quota, as
                # the old client did, does not help.
                await asyncio.sleep(exc.retry_after or _jittered_backoff(attempt))

            except LLMUnavailable as exc:
                last_error = exc
                breaker.record_failure()
                if attempt == _MAX_ATTEMPTS:
                    break
                await asyncio.sleep(_jittered_backoff(attempt))

            except LLMError:
                # 4xx other than 429: bad request, bad key, safety block.
                # Retrying sends the identical request and fails identically.
                breaker.record_failure()
                raise

        breaker.record_failure()
        raise LLMUnavailable(
            f"{provider.value} failed after {_MAX_ATTEMPTS} attempts: {last_error}"
        ) from last_error

    async def _call_gemini(
        self,
        prompt: str,
        model: str | None,
        temperature: float,
        max_output_tokens: int,
        response_schema: dict[str, Any] | None,
    ) -> LLMResponse:
        key = self._settings.gemini_api_key
        assert key is not None
        name = model or self._settings.generation_model

        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        }
        if response_schema is not None:
            # Schema-constrained decoding. Removes the fence-splitting that
            # the previous implementation relied on.
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = response_schema

        resp = await self._http.post(
            f"{GEMINI_BASE}/models/{name}:generateContent",
            # Header rather than query string: a key in a URL leaks into
            # logs, proxies and browser history.
            headers={"x-goog-api-key": key.get_secret_value()},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": generation_config,
            },
        )
        _raise_for_status(resp, Provider.GEMINI)

        payload = resp.json()
        candidates = payload.get("candidates") or []
        if not candidates:
            reason = payload.get("promptFeedback", {}).get("blockReason", "no candidates")
            raise LLMError(f"gemini returned no candidates: {reason}")

        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()

        usage = payload.get("usageMetadata") or {}
        prompt_tokens = usage.get("promptTokenCount")
        completion_tokens = usage.get("candidatesTokenCount")
        estimated = prompt_tokens is None or completion_tokens is None

        return LLMResponse(
            text=text,
            model=name,
            provider=Provider.GEMINI,
            prompt_tokens=prompt_tokens if prompt_tokens is not None else estimate_tokens(prompt),
            completion_tokens=(
                completion_tokens if completion_tokens is not None else estimate_tokens(text)
            ),
            tokens_estimated=estimated,
        )

    async def _call_groq(
        self,
        prompt: str,
        model: str | None,
        temperature: float,
        max_output_tokens: int,
        response_schema: dict[str, Any] | None,
    ) -> LLMResponse:
        key = self._settings.groq_api_key
        assert key is not None
        name = model or self._settings.cross_judge_model

        body: dict[str, Any] = {
            "model": name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        if response_schema is not None:
            # Groq's OpenAI-compatible surface takes json_object rather than a
            # schema, so the schema still has to be described in the prompt.
            body["response_format"] = {"type": "json_object"}

        resp = await self._http.post(
            f"{GROQ_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {key.get_secret_value()}"},
            json=body,
        )
        _raise_for_status(resp, Provider.GROQ)

        payload = resp.json()
        choices = payload.get("choices") or []
        if not choices:
            raise LLMError("groq returned no choices")
        text = (choices[0].get("message", {}).get("content") or "").strip()

        usage = payload.get("usage") or {}
        return LLMResponse(
            text=text,
            model=name,
            provider=Provider.GROQ,
            prompt_tokens=usage.get("prompt_tokens", estimate_tokens(prompt)),
            completion_tokens=usage.get("completion_tokens", estimate_tokens(text)),
            tokens_estimated="usage" not in payload,
        )

    async def complete_structured(
        self,
        prompt: str,
        schema: type[T],
        *,
        provider: Provider = Provider.GEMINI,
        model: str | None = None,
        temperature: float = 0.2,
        agent: str = "unknown",
        fallback: Provider | None = None,
    ) -> tuple[T, LLMResponse]:
        """A completion validated into a Pydantic model.

        One repair attempt on a validation failure, feeding the error back.
        Beyond that the prompt or schema is wrong and retrying wastes quota.
        """
        json_schema = _gemini_schema(schema)
        response = await self.complete(
            prompt,
            provider=provider,
            model=model,
            temperature=temperature,
            response_schema=json_schema,
            agent=agent,
            fallback=fallback,
        )

        try:
            return schema.model_validate_json(_strip_fences(response.text)), response
        except (ValidationError, ValueError) as first_error:
            log.warning("structured output failed validation, attempting one repair")
            repair = (
                f"{prompt}\n\n"
                f"A previous attempt produced output that failed validation.\n"
                f"Output was:\n{response.text[:2000]}\n\n"
                f"Validation error:\n{first_error}\n\n"
                f"Return only JSON matching the schema."
            )
            retry = await self.complete(
                repair,
                provider=provider,
                model=model,
                temperature=0.0,
                response_schema=json_schema,
                agent=f"{agent}:repair",
                fallback=fallback,
            )
            try:
                return schema.model_validate_json(_strip_fences(retry.text)), retry
            except (ValidationError, ValueError) as second_error:
                raise LLMError(
                    f"structured output failed validation twice for {schema.__name__}: "
                    f"{second_error}"
                ) from second_error


def _jittered_backoff(attempt: int) -> float:
    """Exponential with full jitter, to avoid a synchronized retry storm."""
    ceiling = min(_BACKOFF_MAX_SECONDS, _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
    return random.uniform(0, ceiling)


def _raise_for_status(resp: httpx.Response, provider: Provider) -> None:
    if resp.status_code < 400:
        return
    detail = resp.text[:300]
    if resp.status_code == 429:
        raise LLMRateLimited(
            f"{provider.value} rate limited: {detail}",
            retry_after=_parse_retry_after(resp),
        )
    if resp.status_code >= 500:
        raise LLMUnavailable(f"{provider.value} {resp.status_code}: {detail}")
    if resp.status_code in (401, 403):
        raise LLMNotConfigured(f"{provider.value} rejected the API key ({resp.status_code})")
    raise LLMError(f"{provider.value} {resp.status_code}: {detail}")


def _parse_retry_after(resp: httpx.Response) -> float | None:
    raw = resp.headers.get("retry-after")
    if not raw:
        return None
    try:
        return min(float(raw), _BACKOFF_MAX_SECONDS)
    except ValueError:
        # The HTTP-date form is legal but rare here, and a fixed wait is
        # better than parsing it wrong.
        return _BACKOFF_MAX_SECONDS


def _strip_fences(text: str) -> str:
    """Remove markdown fences a model may add despite JSON mode.

    Schema-constrained decoding makes this rare, but a fallback provider
    without schema support can still wrap its output.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    body = stripped.split("```", 2)
    if len(body) < 2:
        return stripped
    inner = body[1]
    if inner.startswith("json"):
        inner = inner[4:]
    return inner.strip()


def _gemini_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Convert a Pydantic schema to the subset Gemini accepts.

    Gemini rejects `$defs`, `$ref`, `additionalProperties` and several
    validation keywords, so references are inlined and unknown keys dropped.
    """
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})
    pruned = _prune(_inline_refs(raw, defs))
    assert isinstance(pruned, dict)
    return pruned


def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            target = defs.get(ref.split("/")[-1], {})
            merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
            return _inline_refs(merged, defs)
        return {k: _inline_refs(v, defs) for k, v in node.items()}
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


_ALLOWED_SCHEMA_KEYS = frozenset(
    {"type", "format", "description", "nullable", "enum", "items", "properties", "required"}
)


def _prune(node: Any) -> Any:
    """Keep only the schema keywords Gemini accepts.

    `properties` is handled separately because its keys are field names, not
    keywords: filtering them as keywords empties the object.
    """
    if isinstance(node, list):
        return [_prune(v) for v in node]
    if not isinstance(node, dict):
        return node

    # Pydantic spells Optional[X] as anyOf[X, null]. Gemini has no anyOf, so
    # collapse to the non-null branch and mark it nullable.
    if "anyOf" in node:
        branches = [b for b in node["anyOf"] if isinstance(b, dict) and b.get("type") != "null"]
        if branches:
            collapsed = _prune(branches[0])
            if isinstance(collapsed, dict):
                collapsed["nullable"] = True
                if "description" in node:
                    collapsed["description"] = node["description"]
                return collapsed

    out: dict[str, Any] = {}
    for key, value in node.items():
        if key not in _ALLOWED_SCHEMA_KEYS:
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {field: _prune(sub) for field, sub in value.items()}
        else:
            out[key] = _prune(value)
    return out
