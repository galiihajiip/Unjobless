# syntax=docker/dockerfile:1.7
# Builds the PWA and serves it with Caddy (TLS, security headers, reverse proxy to the API).
FROM node:26-alpine AS web
WORKDIR /src
RUN corepack enable
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/
RUN --mount=type=cache,target=/root/.local/share/pnpm/store pnpm install --frozen-lockfile --filter "@unjobless/web..."
COPY apps/web apps/web
RUN pnpm --filter @unjobless/web build

FROM caddy:2-alpine
COPY deploy/caddy/Caddyfile /etc/caddy/Caddyfile
COPY --from=web /src/apps/web/dist /srv
