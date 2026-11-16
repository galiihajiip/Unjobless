# Security review — release candidate 0.1.0 (2026-11-16)

Scope: the whole repository at the time of writing. Method: code review against the playbook's Block 42 checklist, automated tests, dependency audits and a live Docker deployment check.

## Results by area

| Area | Status | Notes |
|---|---|---|
| Authentication & sessions | ✅ | Single owner, one-time bootstrap with setup token in production, argon2id, throttling, keyed session hashes, idle/absolute expiry, revocation. |
| Authorization | ✅ | All private routes behind a router-level dependency; automated test enumerates every OpenAPI route anonymously. |
| CSRF / CORS / headers | ✅ | CSRF header bound to the session; same-origin only (no CORS middleware); HSTS, CSP, XFO DENY, nosniff, no-referrer at Caddy; API CSP `default-src 'none'`. |
| SSRF & URL import | ✅ | See threat T6. Live-tested: TLS with IP pinning + SNI works against real HTTPS sites. |
| File uploads | ✅ | Magic sniffing, size limits, image bomb guard, macro DOCX rejection, sandboxed OCR subprocess. |
| HTML parsing / browser isolation | ✅ | lexbor/trafilatura parsing only; **no headless browser in v1**. |
| XSS | ✅ | No raw HTML rendering in the SPA; strict CSP. |
| SQL injection | ✅ | Parameterised ORM queries. |
| Secrets & logging | ✅ | Encrypted at rest; masked in API; redaction processor for keys, cookies, auth headers and CV text fields; secrets only from env. |
| Private data access | ✅ | CVs/exports served only through authenticated routes with `no-store`; files stored `0600` in a private volume. |
| Dependencies | ✅ | `pip-audit` (runtime lock) and `pnpm audit --prod`: **no known vulnerabilities** on 2026-11-16. |
| Containers & network | ✅ | Non-root, read-only rootfs, `no-new-privileges`, internal DB network, only proxy ports published. |
| Backups | ✅ | Restricted permissions; checksums; master key held separately. |
| Prompt injection / LLM actions | ✅ | No tools given to models; schema validation; AI can never verify a vacancy; verbatim-evidence check. |
| Retention / deletion | ✅ | Raw-document retention setting; documents cited as evidence are never deleted; operational tables pruned. |
| Collection policy | ✅ | Default-disabled sources, policy review, robots.txt, exclusions, honest User-Agent. |

## Open findings

| Severity | Finding | Status |
|---|---|---|
| Medium | Login throttling counts per client IP from Caddy. Behind another proxy/CDN, all clients could share one IP. | Documented in VPS guide; acceptable for a single-owner instance. |
| Low | No passkey/2FA in v1 (password only). | Known limitation; strong password + throttling. |
| Low | The robots.txt check for user-initiated URL imports is conservative and may block pages a browser could open; the paste fallback covers this. | By design. |
| Low | The Caddy CSP allows `'unsafe-inline'` styles (React inline style attributes). Scripts remain `'self'` only. | Accepted. |
| Info | Docker publishes ports through iptables and can bypass `ufw`; only 80/443 are published. | Documented. |

**No unresolved high or critical findings.** The release can be declared a personal-use release candidate.

## Checks run for this review

- Backend: `ruff`, `ruff format --check`, `mypy` (0 issues), `pytest` (all passing; 73% line coverage).
- Frontend: `eslint`, `tsc`, `vitest` (20 tests incl. render of every route), production build.
- `alembic check` (no drift), down/up migration cycle.
- `docker compose up -d --build` from empty volumes, then `deploy/scripts/smoke_test.py` end to end, then backup → restore into a second clean stack → verify.
