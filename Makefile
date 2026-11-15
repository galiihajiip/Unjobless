.PHONY: dev-db dev-api dev-worker dev-web migrate test lint typecheck fmt check

dev-db:      ; docker compose -f compose.dev.yaml up -d --wait
dev-api:     ; cd backend && uv run unjobless serve --reload
dev-worker:  ; cd backend && uv run unjobless worker
dev-web:     ; pnpm dev:web
migrate:     ; cd backend && uv run unjobless migrate
fmt:         ; cd backend && uv run ruff format src tests && uv run ruff check --fix src tests; pnpm format
lint:        ; cd backend && uv run ruff check src tests && uv run ruff format --check src tests; pnpm lint:web
typecheck:   ; cd backend && uv run mypy; pnpm typecheck:web
test:        ; cd backend && uv run pytest; pnpm test:web
check: lint typecheck test
