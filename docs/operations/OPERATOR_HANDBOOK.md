# Operator handbook

Day-to-day tasks for the owner of an Unjobless instance. Commands assume you are in the repository directory on the server.

## Check source health

- **UI:** Sources. Each card shows state, policy review, health badge, last success, last check and next check. Open a source for its run history, failed items and health events.
- Health meanings:
  - **Healthy:** last run succeeded.
  - **Degraded:** some items failed, or 1–2 failed runs.
  - **Failing:** 3 or more consecutive failed runs.
  - **Rate limited:** waiting for the source's retry time.
  - **Unavailable:** the source refused access, e.g. login needed, 403, robots.txt, or board not found. It is not bypassed; fix the configuration or disable the source.
- **CLI:** `docker compose logs --since 1h worker | grep run_` and `docker compose exec db psql -U unjobless -c "select id, source_id, status, error_code, finished_at from source_runs order by id desc limit 20"`.

## Pause, disable or exclude a source

- **Pause / resume:** on the source card. Queued runs are cancelled and a running run stops at its next checkpoint.
- **Disable:** open the source and record a policy review with *Denied*. This disables it immediately.
- **Never collect from a domain again:** Sources › Exclusion list. Any source on that domain is disabled, and URL imports from it are blocked.

## Rotate an AI API key

AI Studio › provider › **Replace key**. The new key is encrypted with your master key and only the last 4 characters are shown. Then click **Test connection**. To remove a key entirely, use **Delete key**.

If a provider is rate limited it cools down automatically. Unjobless does not switch keys or providers to get around a rate limit.

## Review unverified opportunity leads

Opportunity Signals lists leads, referrals and campaigns, each with its reason, evidence and ambiguity flags.

- **Not relevant:** hides the item.
- **I verified it — promote:** use only after checking the official source. It creates a vacancy marked as verified by you, keeping the original post as evidence.

## Correct bad extraction

- **Before saving:** Import Center › Review › edit fields, then confirm. Your edits are stored as corrections and audited.
- **After saving:** open the vacancy, then *Correct* (status) or *Report incorrect data*. To fix fields, re-import with corrections, or merge the item into the right vacancy.
- **Wrong merge:** Import Center › Duplicates, or the audit log entry, then *undo*.

## Verify a vacancy's status

On the vacancy page, check *Timeline* (first/last seen, last checked, last verified) and *Status history*. A missing listing on an approved ATS moves to *Status unknown*, never *Closed*. After checking the employer's page yourself, use **Correct** to set *Verified open*, *Closed* or *Expired* with a reason.

## Backups

- **Automatic:** daily at 03:17 UTC in the worker. Settings › *Backups to keep* sets how many are retained.
- **Manual:** Settings › Backups › *Create backup now*, or `docker compose exec api unjobless backup`.
- **Verify:** `docker compose exec api unjobless verify-backup /data/backups/<name>`.
- Copy backups off the server (see [VPS.md](../deployment/VPS.md) §5). Keep `UNJOBLESS_MASTER_KEY` in a password manager.

## Restore a backup

```bash
deploy/scripts/restore.sh /path/to/unjobless-<timestamp>
docker compose exec api unjobless integrity-check   # missing_count must be 0
```

This replaces the current data. Sign in with the password from the backed-up instance.

## Migrate to another VPS

Follow [MIGRATION.md](../deployment/MIGRATION.md): back up, deploy the new server with the **same master key**, run `restore.sh`, run the integrity check, then switch DNS. The old server stays as your rollback.

## Change your password or sign out devices

Settings › Security. Changing the password signs out every other session. *Sign out everywhere* revokes all sessions.

## Update the application

```bash
docker compose exec api unjobless backup && git pull && docker compose up -d --build
```

Migrations run automatically before the API and worker start.
