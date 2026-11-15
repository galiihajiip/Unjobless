"""Command-line entry point: `unjobless <command>`."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="unjobless")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    sub.add_parser("migrate", help="apply database migrations")
    sub.add_parser("worker", help="run the background worker")
    sub.add_parser("seed", help="load development fixtures (non-production only)")
    sub.add_parser("gen-key", help="print a new random urlsafe secret")
    b = sub.add_parser("backup", help="create a verified backup (database + files + manifest)")
    b.add_argument("--keep", type=int, default=7)
    r = sub.add_parser("restore", help="restore a backup directory into this deployment")
    r.add_argument("path")
    r.add_argument("--yes", action="store_true", help="confirm overwriting the current data")
    v = sub.add_parser("verify-backup", help="check a backup's checksums")
    v.add_argument("path")
    sub.add_parser("integrity-check", help="verify stored file references and key decryption")
    sub.add_parser("eval-signals", help="print opportunity-signal evaluation report")
    args = parser.parse_args(argv)

    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "unjobless.main:app", host=args.host, port=args.port, reload=args.reload, proxy_headers=True
        )
    elif args.command == "migrate":
        from unjobless.db.migrate import upgrade_head

        upgrade_head()
    elif args.command == "worker":
        from unjobless.jobs.worker import run_worker

        run_worker()
    elif args.command == "seed":
        from unjobless.db.seed import seed

        seed()
    elif args.command == "gen-key":
        import base64
        import secrets

        print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("="))
    elif args.command in ("backup", "restore", "verify-backup", "integrity-check"):
        import json
        from pathlib import Path

        from unjobless.ops import backup as ops

        if args.command == "backup":
            res = ops.create_backup(keep=args.keep)
        elif args.command == "restore":
            res = ops.restore(Path(args.path), confirm=args.yes)
        elif args.command == "verify-backup":
            res = ops.verify(Path(args.path))
        else:
            res = ops.integrity_check()
        print(json.dumps(res, indent=2, default=str))
    elif args.command == "eval-signals":
        from unjobless.evaluation.signals_eval import render_markdown, run

        print(render_markdown(run()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
