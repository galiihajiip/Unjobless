#!/usr/bin/env sh
# Restore an Unjobless backup directory into the running Compose deployment.
#
#   deploy/scripts/restore.sh /path/to/unjobless-YYYYMMDDTHHMMSSZ
#
# 1. copies the backup into the `backups` volume (owned by the app user, uid 10001);
# 2. verifies checksums;
# 3. restores the database + files and runs migrations (`unjobless restore --yes`);
# 4. restarts api and worker.
# Run from the repository root on the target server. The target .env must contain the SAME
# UNJOBLESS_MASTER_KEY as the source server, or stored AI keys must be re-entered afterwards.
set -eu

SRC="${1:?usage: restore.sh /path/to/unjobless-<timestamp>}"
NAME="$(basename "$SRC")"
[ -f "$SRC/manifest.json" ] || { echo "Not a backup directory: $SRC" >&2; exit 1; }

echo "==> Copying $NAME into the backups volume"
docker compose cp "$SRC" "api:/data/backups/"
docker compose exec -T -u root api chown -R 10001:10001 "/data/backups/$NAME"

echo "==> Verifying checksums"
docker compose exec -T api unjobless verify-backup "/data/backups/$NAME"

echo "==> Restoring (this replaces the current database and files)"
docker compose exec -T api unjobless restore "/data/backups/$NAME" --yes

echo "==> Restarting services"
docker compose restart api worker
echo "Done. Sign in with the source instance's owner password."
