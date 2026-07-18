from __future__ import annotations

from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from mtgproxy.catalog import CardNotFound
from mtgproxy.web.auth import login_required

bp = Blueprint("main", __name__)


def _catalog():
    return current_app.extensions["catalog"]


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _safe_send(path: Path, root: Path):
    """Send a file only if it exists and resolves under root; else 404."""
    if not path.is_file() or not _is_under(path, root):
        abort(404)
    return send_file(path)


@bp.get("/")
@bp.get("/search")
@login_required
def search():
    q = (request.args.get("q") or "").strip()
    results = _catalog().search(q, partial=True) if q else None
    if request.headers.get("HX-Request") == "true":
        return render_template("partials/results.html", q=q, results=results)
    return render_template("search.html", q=q, results=results)


@bp.post("/queue/add")
@login_required
def add_to_queue():
    flash("Add not implemented yet")
    return redirect(url_for("main.search"))


@bp.get("/queues/<queue_name>")
@login_required
def queue(queue_name):
    return f"queue {queue_name}"


@bp.get("/cards/<int:card_id>/history")
@login_required
def history(card_id):
    return f"history {card_id}"


@bp.get("/images/cards/<int:card_id>")
@login_required
def card_image(card_id: int):
    try:
        card = _catalog().resolve(card_id=card_id)
    except CardNotFound:
        abort(404)
    path = Path(card.image_path)
    root = Path(current_app.config["IMAGES_DIR"])
    return _safe_send(path, root)


@bp.get("/images/snapshots/<path:rel>")
@login_required
def snapshot_image(rel: str):
    root = Path(current_app.config["IMAGES_DIR"]) / "snapshots"
    path = (root / rel).resolve()
    return _safe_send(path, root)
