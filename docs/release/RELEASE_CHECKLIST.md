# Release checklist

Run before tagging a release. Every item must pass, or the release notes must explain why.

## Code quality
- [ ] `cd backend && uv run ruff check src tests && uv run ruff format --check src tests`
- [ ] `cd backend && uv run mypy` → 0 issues
- [ ] `cd backend && uv run pytest` → all pass (needs the dev Postgres: `make dev-db`)
- [ ] `cd backend && uv run alembic check` → no drift; new migrations reviewed by hand
- [ ] `pnpm lint:web && pnpm typecheck:web && pnpm test:web && pnpm build:web`
- [ ] `cd backend && uv run unjobless eval-signals` → test-set precision unchanged or better

## Security
- [ ] `uvx pip-audit -r <(uv export --frozen --no-dev --no-emit-project)` → no known vulnerabilities
- [ ] `pnpm audit --prod` → no known vulnerabilities
- [ ] No secrets in the diff (`git diff | grep -iE "sk-|api_key|password="`)
- [ ] `docs/security/SECURITY_REVIEW.md` updated; no open high/critical findings

## Deployment
- [ ] `docker compose up -d --build` from empty volumes → all services healthy
- [ ] `deploy/scripts/smoke_test.py <url> --password … --insecure --live-source` passes
- [ ] Backup → restore into a second project → `smoke_test.py --phase verify` passes
- [ ] Response headers include HSTS + CSP; `http://` redirects to `https://`

## Product acceptance (playbook §25, spot-check in the UI)
- [ ] Setup → CV upload → review → confirm → preferences
- [ ] URL batch with one failing URL → partial success + paste fallback
- [ ] Paste import → review → confirm as vacancy / as lead
- [ ] Compare rejects a third vacancy; unknowns stay Unknown
- [ ] Tailor → accept/reject claims → export PDF and DOCX open
- [ ] Track → mark applied manually → history recorded
- [ ] PWA install prompt available over HTTPS; offline shows the shell + banner only

## Docs
- [ ] README, operator handbook, deployment and migration guides match the actual commands
- [ ] `docs/release/KNOWN_LIMITATIONS.md` current
