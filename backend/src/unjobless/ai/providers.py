"""Provider adapters. Domain code never imports these directly — it goes through `ai.gateway`.

Each adapter implements `complete_json(...)`: send a system prompt + user content, require a
JSON object matching `schema`, return the parsed object plus usage. Adapters raise typed
ProviderError subclasses so the gateway can apply cooldowns and (optional) fallback policy.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5-5"
# First-party list prices (USD per million tokens), used only when the owner has not configured prices.
KNOWN_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-2": (8.0, 40.0),
}


class ProviderError(Exception):
    retryable = False

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ProviderRateLimited(ProviderError):
    """429 / quota / overloaded. The gateway sets a cooldown; it never rotates keys to evade it."""

    retryable = True

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class ProviderUnavailable(ProviderError):
    """5xx, timeouts, connection failures."""

    retryable = True


class ProviderAuthError(ProviderError):
    pass


class ProviderBadRequest(ProviderError):
    pass


class ProviderRefused(ProviderError):
    """The model declined (safety refusal). Not retried."""


@dataclass
class ProviderResult:
    data: dict[str, Any]
    model: str
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    raw_text: str


class ProviderAdapter(Protocol):
    kind: str

    def complete_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        max_tokens: int,
        effort: str,
        timeout: float,
    ) -> ProviderResult: ...


def _retry_after(headers: Any) -> float | None:
    try:
        v = headers.get("retry-after") if headers is not None else None
        return float(v) if v else None
    except (TypeError, ValueError):
        return None


class AnthropicAdapter:
    """Claude via the official `anthropic` SDK (Messages API).

    - Structured output with `output_config.format` (JSON schema) — the first text block is valid JSON.
    - Effort is set explicitly per task (Claude Opus 5.5 defaults to `medium`; thinking is always on).
    - Server-side refusal fallback (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`)
      re-runs a declined request on Anthropic's recommended fallback model inside the same call.
    - SDK auto-retries are limited to 1; longer waits become gateway cooldowns.
    """

    kind = "anthropic"
    FALLBACK_BETA = "server-side-fallback-2026-07-01"

    def __init__(self, api_key: str, base_url: str | None = None, use_refusal_fallback: bool = True):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key, base_url=base_url or None, max_retries=1)
        self.use_refusal_fallback = use_refusal_fallback

    def complete_json(self, *, model, system, user, schema, max_tokens, effort, timeout):  # type: ignore[no-untyped-def]
        a = self._anthropic
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        }
        if self.use_refusal_fallback:
            kwargs["betas"] = [self.FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        started = time.monotonic()
        try:
            resp = self.client.with_options(timeout=timeout).beta.messages.create(**kwargs)
        except a.RateLimitError as e:
            raise ProviderRateLimited("Provider rate limit reached.", _retry_after(e.response.headers)) from e
        except a.AuthenticationError as e:
            raise ProviderAuthError("The API key was rejected by the provider.") from e
        except a.PermissionDeniedError as e:
            raise ProviderAuthError("The API key lacks permission for this model.") from e
        except a.NotFoundError as e:
            raise ProviderBadRequest(f"Model {model!r} was not found for this key.") from e
        except a.BadRequestError as e:
            raise ProviderBadRequest(
                f"Provider rejected the request: {getattr(e, 'message', '')[:300]}"
            ) from e
        except a.APIStatusError as e:
            if e.status_code == 529:
                raise ProviderRateLimited("Provider is overloaded.", _retry_after(e.response.headers)) from e
            if e.status_code >= 500:
                raise ProviderUnavailable(f"Provider error {e.status_code}.") from e
            raise ProviderBadRequest(f"Provider error {e.status_code}.") from e
        except a.APITimeoutError as e:
            raise ProviderUnavailable("Provider timed out.") from e
        except a.APIConnectionError as e:
            raise ProviderUnavailable("Could not reach the provider.") from e
        latency = int((time.monotonic() - started) * 1000)
        if resp.stop_reason == "refusal":
            category = getattr(getattr(resp, "stop_details", None), "category", None)
            raise ProviderRefused(f"The model declined this request (category: {category or 'unspecified'}).")
        if resp.stop_reason == "max_tokens":
            raise ProviderBadRequest("Output hit the token limit before the JSON was complete.")
        text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ProviderBadRequest("Provider returned invalid JSON.") from e
        usage = getattr(resp, "usage", None)
        return ProviderResult(
            data=data,
            model=getattr(resp, "model", model),
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            latency_ms=latency,
            raw_text=text,
        )


class OpenAICompatibleAdapter:
    """Generic adapter for non-Anthropic providers exposing an OpenAI-style Chat Completions API
    with JSON-schema response formats. Used only for providers the owner configures explicitly."""

    kind = "openai_compatible"

    def __init__(self, api_key: str, base_url: str, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            transport=transport, headers={"Authorization": f"Bearer {api_key}"}, trust_env=False
        )

    def complete_json(self, *, model, system, user, schema, max_tokens, effort, timeout):  # type: ignore[no-untyped-def]
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": schema, "strict": True},
            },
        }
        started = time.monotonic()
        try:
            r = self.client.post(f"{self.base_url}/chat/completions", json=body, timeout=timeout)
        except httpx.TimeoutException as e:
            raise ProviderUnavailable("Provider timed out.") from e
        except httpx.HTTPError as e:
            raise ProviderUnavailable("Could not reach the provider.") from e
        if r.status_code == 429:
            raise ProviderRateLimited("Provider rate limit reached.", _retry_after(r.headers))
        if r.status_code in (401, 403):
            raise ProviderAuthError("The API key was rejected by the provider.")
        if r.status_code >= 500:
            raise ProviderUnavailable(f"Provider error {r.status_code}.")
        if r.status_code >= 400:
            raise ProviderBadRequest(f"Provider error {r.status_code}.")
        payload = r.json()
        choice = (payload.get("choices") or [{}])[0]
        if choice.get("finish_reason") == "content_filter":
            raise ProviderRefused("The model declined this request.")
        text = (choice.get("message") or {}).get("content") or ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ProviderBadRequest("Provider returned invalid JSON.") from e
        usage = payload.get("usage") or {}
        return ProviderResult(
            data=data,
            model=payload.get("model", model),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=int((time.monotonic() - started) * 1000),
            raw_text=text,
        )


class FakeAdapter:
    """Deterministic offline adapter for tests and demos. `handler(task_marker, user)` returns a dict."""

    kind = "fake"

    def __init__(self, handler: Callable[[str, str, dict[str, Any]], dict[str, Any]] | None = None):
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, *, model, system, user, schema, max_tokens, effort, timeout):  # type: ignore[no-untyped-def]
        self.calls.append({"model": model, "system": system, "user": user, "effort": effort})
        if self.handler is None:
            raise ProviderUnavailable("Fake provider has no handler configured.")
        data = self.handler(system, user, schema)
        return ProviderResult(
            data=data,
            model=model,
            input_tokens=len(user) // 4,
            output_tokens=50,
            latency_ms=1,
            raw_text=json.dumps(data),
        )


def build_adapter(kind: str, api_key: str | None, base_url: str | None) -> ProviderAdapter:
    if kind == "anthropic":
        if not api_key:
            raise ProviderAuthError("No API key configured for this provider.")
        return AnthropicAdapter(api_key, base_url)
    if kind == "openai_compatible":
        if not api_key or not base_url:
            raise ProviderAuthError("This provider needs both an API key and a base URL.")
        return OpenAICompatibleAdapter(api_key, base_url)
    if kind == "fake":
        from unjobless.ai import fake_registry

        return FakeAdapter(fake_registry.HANDLER)
    raise ProviderBadRequest(f"Unknown provider kind {kind!r}.")
