#!/usr/bin/env bash
#
# Unjobless Auto-Commit & Push runner
# Runs the atomic semantic commit daemon in foreground or background.
#

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "Starting Unjobless Auto-Commit Daemon..."
exec python3 scripts/auto_commit_push.py "$@"
