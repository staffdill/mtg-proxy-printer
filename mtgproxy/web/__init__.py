"""LAN web UI over the card catalog (search, queue, build, history)."""
from __future__ import annotations

import atexit
from pathlib import Path

from flask import Flask

from mtgproxy.catalog import Catalog


def create_app(config: dict | None = None) -> Flask:
    cfg = dict(config or {})
    password = cfg.get("PASSWORD", "")
    if not password:
        raise ValueError("web UI password is required (set PASSWORD / MTGPROXY_WEB_PASSWORD)")

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["SECRET_KEY"] = cfg.get("SECRET_KEY") or "dev-only-change-me"

    app.config["PASSWORD"] = password
    app.config["DB_PATH"] = Path(cfg.get("DB_PATH", "catalog.db"))
    app.config["IMAGES_DIR"] = Path(cfg.get("IMAGES_DIR", "catalog/images"))
    app.config["SHEETS_ROOT"] = Path(cfg.get("SHEETS_ROOT", "."))
    app.config["TESTING"] = bool(cfg.get("TESTING", False))

    cat = Catalog(db_path=app.config["DB_PATH"], images_dir=app.config["IMAGES_DIR"])
    app.extensions["catalog"] = cat

    @app.teardown_appcontext
    def _close_catalog(exc=None):
        # Catalog is process-long; only close when the app is torn down in tests
        # via explicit close. Keep connection open across requests.
        pass

    # Flask has no teardown_app; close catalog at process exit.
    def _shutdown():
        c = app.extensions.get("catalog")
        if c is not None:
            c.close()

    atexit.register(_shutdown)

    # Blueprints registered in later tasks; for now register a stub login redirect.
    from mtgproxy.web.auth import auth_bp, login_required
    from mtgproxy.web import routes

    app.register_blueprint(auth_bp)
    app.register_blueprint(routes.bp)

    return app
