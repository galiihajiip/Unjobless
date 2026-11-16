# Threat model

## Assets

1. The owner's CV, profile and application history (personal data).
2. AI provider API keys (money, account standing).
3. The owner's session (full access to 1–2).
4. The server and its internal services (Postgres, worker), reachable via SSRF.
5. Integrity of collected data (false vacancies cause wasted or harmful applications).

## Actors & entry points

| Actor | Entry point |
|---|---|
| Internet attacker | Public HTTPS endpoint (login, bootstrap, static files) |
| Malicious web content | Pages fetched by the importer or crawler; job posts; pasted text; uploaded files |
| Compromised / hostile source | ATS/API responses, RSS/sitemaps |
| Prompt-injection author | Any text that reaches an AI provider |
| Lost device / shared computer | Browser storage, installed PWA |

## Threats and mitigations

| # | Threat | Mitigation | Verified by |
|---|---|---|---|
| T1 | Brute-force login | argon2id, 5 failures/IP and 30 global per 15 min → 429 | `test_auth.py::test_login_throttled_after_failures` |
| T2 | Instance hijack before setup | One-time bootstrap; setup token required in production; DB singleton | `test_bootstrap_once_then_rejected`, `test_bootstrap_requires_setup_token_when_configured` |
| T3 | CSRF | Session-bound CSRF token header on all unsafe methods; SameSite cookies | `test_private_routes_require_auth_and_csrf` |
| T4 | Unauthenticated API/file access | Router-level `require_owner` dependency; every non-public route tested | `test_every_private_route_rejects_anonymous` |
| T5 | Session theft | HttpOnly+Secure cookies, keyed token hashes in DB, idle + absolute expiry, revoke/logout-all, password change revokes all | `test_password_change_revokes_sessions` |
| T6 | SSRF to Postgres/metadata/internal hosts | `SafeFetcher`: scheme/port allowlist, single-label/internal host block, DNS check of all A/AAAA records, IP pinning with SNI, redirect revalidation, embedded-IPv4 checks; `data` network internal | `test_safe_fetch.py` (40+ cases incl. rebinding, metadata, redirects) |
| T7 | Resource exhaustion via responses | Byte cap after decompression, declared-size rejection, total timeout, content-type allowlist | `test_body_capped…`, `test_decompression_bomb_capped` |
| T8 | Malicious uploads | Magic-byte sniffing (not the declared type), size limits, Pillow decompression-bomb guard, macro DOCX rejected, OCR in a subprocess with CPU/memory/time limits, no shell | `test_rejects_non_cv_files`, `media.py` |
| T9 | Stored XSS from scraped text | React escapes all text; no `dangerouslySetInnerHTML`; strict CSP (`script-src 'self'`); API CSP `default-src 'none'` | grep audit, CSP header check |
| T10 | SQL injection | ORM/parameterised queries only; the only f-string SQL uses constant table names (backup module) | grep audit |
| T11 | Prompt injection (job post tells the AI to verify itself / leak data) | Untrusted content wrapped and declared as data; models have no tools; schema-validated output; AI cannot set VERIFIED/LIKELY_OPEN; evidence must appear verbatim in the source or the value is dropped | `test_untrusted_content_is_delimited…`, `test_ai_values_without_verbatim_evidence_are_dropped`, `signals.classify_with_ai` |
| T12 | AI key leakage | AES-256-GCM with an HKDF-derived key from the env master key; masked hint only in API responses; log redaction of key patterns | `test_api_key_never_returned`, `test_api_key_encrypted_at_rest`, `test_redaction_processor` |
| T13 | Personal data sent to AI unnecessarily | Contact fields removed and emails/phones scrubbed before matching/tailoring prompts | `test_redaction` |
| T14 | Fabricated CV claims | Claims must cite profile fact IDs; new numbers/skills flagged and rejected by default; explicit confirmation needed | `test_tailoring_never_changes_master…`, `test_claim_with_issues_requires_explicit_confirmation` |
| T15 | Collection violating site rules | Sources disabled until a policy review; robots.txt enforced (cannot be disabled); exclusions; access walls never bypassed | `test_sources.py`, `test_crawler.py` |
| T16 | Private data cached on a shared device | Service worker precaches only the static shell; `/api` is NetworkOnly; API responses `Cache-Control: no-store` | `dist/sw.js` inspection |
| T17 | Container escape / lateral movement | Non-root uid, read-only rootfs, no-new-privileges, DB on internal network, only the proxy publishes ports | `compose.yaml` |
| T18 | Backup exposure | Backup dirs `0700`/files `0600`; AI keys stay encrypted inside dumps; master key kept separately | `ops/backup.py` |
