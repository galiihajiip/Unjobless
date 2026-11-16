# Migrating Unjobless to another server

## What must move

| Item | Where | How |
|---|---|---|
| Database + files | backup directory | `unjobless backup` (pg_dump + files tarball + checksummed manifest) |
| `UNJOBLESS_MASTER_KEY` | your password manager | copy into the new `.env` |
| Other `.env` values | old server | copy; regenerate `POSTGRES_PASSWORD` if you like (a fresh DB is created) |
| TLS certificates | `caddy_data` | not needed; Caddy obtains new ones |

Nothing depends on the old server's filesystem or any managed service.

## Procedure

1. **Old server:** `docker compose exec api unjobless backup`, then copy the newest `unjobless-<timestamp>` directory to the new server (`docker compose cp api:/data/backups/<name> ./` then `scp`).
2. **New server:** follow [VPS.md](VPS.md) steps 1–3 using the **same `UNJOBLESS_MASTER_KEY`**, and `docker compose up -d --build`. Do not create an owner account; the restore brings it back.
3. **Restore:** `deploy/scripts/restore.sh ./unjobless-<timestamp>`. This copies the backup into the volume with correct ownership, verifies checksums, runs `pg_restore`, extracts files, applies migrations and restarts services.
4. **Check:** sign in with the old password, then run `docker compose exec api unjobless integrity-check`. Expect `missing_count: 0`, and `master_key_matches: true` if AI keys were stored.
5. **DNS cutover:** point the record at the new IP. Expect downtime equal to the DNS TTL plus restore time (minutes for a personal instance). Lower the TTL a day before.
6. **Rollback:** the old server is untouched. Point DNS back if anything is wrong.

## Test performed (Block 40) — 2026-11-16

Two independent Compose projects ran on one machine (`unjobless` on 8443 and `unjobless-restore` on 9443, separate volumes):

1. Stack A was deployed from empty. `smoke_test.py --phase seed` created the owner, uploaded a synthetic CV (processed by the worker), confirmed the profile, imported and confirmed two pasted vacancies, compared them, tailored and exported a PDF, tracked an application, and collected a live Greenhouse board (254 jobs → 256 total vacancies).
2. `unjobless backup` on A: 1.55 MB database dump plus a 76 KB files tarball, with a manifest.
3. Stack B was deployed from empty with the same master key. The backup was copied in, `verify-backup` reported ok, and `restore --yes` completed. The integrity check found 0 missing files and 256 vacancies/raw documents.
4. `smoke_test.py --phase verify` against B passed: owner login, vacancies with source references, comparison, tailored CV, exported PDF bytes and original CV bytes all present.

Issue found and fixed: `docker compose cp` keeps host ownership, so the non-root app could not read the copied backup. `restore.sh` now `chown`s the directory to uid 10001.
