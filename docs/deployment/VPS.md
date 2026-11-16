# VPS deployment (production)

Target: a clean Linux VPS (Debian 12/13 or Ubuntu 22.04/24.04, amd64 or arm64) with ≥ 2 vCPU, 4 GB RAM and 40 GB disk. Values in `<angle brackets>` are placeholders.

## 1. DNS

Create an `A` (and optionally `AAAA`) record for your subdomain, e.g. `jobs.<your-domain>`, pointing at the VPS IP. Wait until `dig +short jobs.<your-domain>` returns it. HTTPS, and therefore PWA installation, need this.

## 2. Server preparation

```bash
# as root or with sudo
apt-get update && apt-get -y upgrade
adduser --disabled-password unjobless && usermod -aG sudo unjobless
# SSH: key-only login
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config && systemctl reload ssh
# Firewall: only SSH + HTTP(S). PostgreSQL is never exposed.
apt-get install -y ufw && ufw default deny incoming && ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw enable
# Docker Engine + Compose plugin (official convenience script; review it first)
curl -fsSL https://get.docker.com -o get-docker.sh && less get-docker.sh && sh get-docker.sh
usermod -aG docker unjobless
```

Docker publishes container ports via iptables and can bypass `ufw` rules. That is safe here only because the sole published ports are 80/443 on `proxy`. Never add `ports:` to `db`, `api` or `worker`.

## 3. Install

```bash
su - unjobless
git clone <your-repository-url> unjobless && cd unjobless
cp .env.example .env && chmod 600 .env
docker compose run --rm --no-deps api unjobless gen-key   # run 3×: master key, session secret, DB password
nano .env
```

Set in `.env`:

| Variable | Value |
|---|---|
| `UNJOBLESS_ENV` | `production` |
| `UNJOBLESS_DOMAIN` | `jobs.<your-domain>` |
| `UNJOBLESS_PUBLIC_BASE_URL` | `https://jobs.<your-domain>` |
| `UNJOBLESS_MASTER_KEY` | generated; **also store it in your password manager** |
| `UNJOBLESS_SESSION_SECRET` | generated |
| `POSTGRES_PASSWORD` | generated |
| `UNJOBLESS_BOOTSTRAP_TOKEN` | optional; a random string you will type on the setup page |

```bash
docker compose up -d --build
docker compose ps        # db/api healthy, migrate exited 0, proxy + worker running
docker compose logs proxy | grep -i certificate   # Caddy obtains the Let's Encrypt certificate
```

Open `https://jobs.<your-domain>`, enter the setup token and create the owner account. If you did not set a token, read it with `docker compose exec api cat /data/files/bootstrap-token.txt`.

## 4. Security notes

- HTTPS only: Caddy redirects HTTP→HTTPS and sends HSTS. Session cookies are `Secure`, `HttpOnly` and `SameSite=Lax`. The CSRF cookie is `SameSite=Strict`.
- `FORWARDED_ALLOW_IPS="*"` is set for `api` because its port is reachable only from the proxy on the private `edge` network. The client IP used for login throttling therefore comes from Caddy.
- Upload size limit: 12 MB at the proxy, 10 MB in the app (`UNJOBLESS_MAX_UPLOAD_BYTES`).
- Restart policy: `unless-stopped` for every long-running service.
- The OpenAPI docs are disabled in production.

## 5. Backups

- The worker writes an automatic backup daily at 03:17 UTC to the `backups` volume and keeps the newest N (Settings › backups to keep, default 7).
- On demand: Settings › Backups, or `docker compose exec api unjobless backup`.
- Copy backups **off the server** regularly, for example a nightly cron on another machine:

```bash
# on your backup machine
rsync -a --delete unjobless@<vps>:/var/lib/docker/volumes/unjobless_backups/_data/ ~/unjobless-backups/
```

(Requires root-readable access on the VPS; alternatively `docker compose cp api:/data/backups ./backups-export` on the VPS and pull that.)

- Keep `UNJOBLESS_MASTER_KEY` separate from the backups. Without it, everything restores except stored AI API keys.

## 6. Update / redeploy

```bash
cd ~/unjobless
docker compose exec api unjobless backup        # always back up first
git pull
docker compose up -d --build                    # migrate runs automatically before api/worker start
docker compose ps && curl -fsS https://jobs.<your-domain>/api/health/ready
```

## 7. Rollback

1. `git checkout <previous-tag-or-commit>`
2. If the failed release ran a migration, restore the pre-update backup: `deploy/scripts/restore.sh <backup-dir>`. Down-migrations exist but restoring the backup is the supported path.
3. `docker compose up -d --build`

## 8. Logs & disk

- `docker compose logs --since 1h api worker` — structured JSON with secrets redacted.
- Log rotation is configured in Compose (10 MB × 5 per service).
- Watch disk usage of `pgdata`, `files` and `backups` with `docker system df -v`.

## 9. Restore / migrate to another server

See [MIGRATION.md](MIGRATION.md).
