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
    args = parser.parse_args(argv)

    if args.command == "serve":
        import uvicorn

        uvicorn.run("unjobless.main:app", host=args.host, port=args.port, reload=args.reload, proxy_headers=True)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
