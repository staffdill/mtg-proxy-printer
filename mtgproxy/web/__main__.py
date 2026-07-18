from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

from mtgproxy.catalog import DEFAULT_DB_PATH, DEFAULT_IMAGES_DIR
from mtgproxy.web import create_app


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LAN web UI for the card catalog.")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--db", default=str(DEFAULT_DB_PATH))
    p.add_argument("--images-dir", default=str(DEFAULT_IMAGES_DIR))
    p.add_argument("--sheets-root", default=".")
    p.add_argument("--password", default=None, help="Overrides MTGPROXY_WEB_PASSWORD.")
    p.add_argument("--secret", default=None, help="Overrides MTGPROXY_WEB_SECRET.")
    args = p.parse_args(argv)

    password = args.password if args.password is not None else os.environ.get("MTGPROXY_WEB_PASSWORD", "")
    if not password:
        print(
            "error: password required — set MTGPROXY_WEB_PASSWORD or pass --password",
            file=sys.stderr,
        )
        return 2

    secret = args.secret if args.secret is not None else os.environ.get("MTGPROXY_WEB_SECRET", "")
    if not secret:
        secret = secrets.token_hex(32)
        print(
            "warning: no MTGPROXY_WEB_SECRET/--secret; using ephemeral key "
            "(sessions reset on restart)",
            file=sys.stderr,
        )

    app = create_app(
        {
            "SECRET_KEY": secret,
            "PASSWORD": password,
            "DB_PATH": Path(args.db),
            "IMAGES_DIR": Path(args.images_dir),
            "SHEETS_ROOT": Path(args.sheets_root),
        }
    )
    # For unit test of missing password we return before run. When testing main
    # with password, avoid binding: detect TESTING via env optional.
    if os.environ.get("MTGPROXY_WEB_SMOKE") == "1":
        return 0
    app.run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
