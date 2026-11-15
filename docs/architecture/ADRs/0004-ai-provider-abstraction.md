# ADR 0004 — AI provider abstraction

- Status: Accepted
- Date: 2026-11-16

## Decision

- Domain code depends on an **`AIGateway`** with task-level methods (`run_task(task_name, input) -> validated output`). It never imports a provider SDK.
- **Adapters** implement a small `ProviderAdapter` protocol (`complete_json(model, system, messages, schema, max_tokens, timeout) -> ProviderResult`). Initial adapters: Anthropic Messages API and an OpenAI-compatible Chat Completions adapter (covers many hosted providers). Both are implemented with `httpx`, keeping dependencies small. A deterministic `fake` adapter is used in tests and when no key is configured.
- **Task registry**: each task has a versioned prompt template, a Pydantic output schema, default model, max output tokens and budget. Results are stored with `task`, `prompt_version`, `schema_version`, `provider`, `model`, token usage and cost estimate.
- **Validation**: output must parse and validate against the schema; one repair retry for format errors only; otherwise the task fails without touching canonical data.
- **Rate limits**: a 429/overloaded response sets a provider cooldown (respecting `retry-after`). Fallback to another *user-configured* provider is optional and off by default. Keys are never rotated to evade quotas.
- **Secrets**: API keys are encrypted with AES-GCM (via `cryptography`) using a key derived from the `UNJOBLESS_MASTER_KEY` environment secret. The API stores ciphertext + a SHA-256 fingerprint and returns only `sk-…abcd`-style masks. Keys never appear in logs (redaction processor) or responses.
- **Prompt-injection defence**: untrusted content is wrapped in clearly delimited data blocks; system prompts instruct the model to treat it as data; the model has **no tools**; outputs are schema-validated and only ever written to review/draft records.
- **Data minimisation**: matching and extraction tasks receive redacted profile data (no phone/email/address).

## Consequences

Losing `UNJOBLESS_MASTER_KEY` makes stored AI keys unrecoverable (they must be re-entered); everything else restores normally. This is documented in backup/restore.
