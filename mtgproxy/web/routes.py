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

from mtgproxy.catalog import CardNotFound, InvalidQuantity
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
    try:
        card_id = int(request.form.get("card_id", ""))
        qty = int(request.form.get("qty", "1"))
    except ValueError:
        flash("Invalid card or quantity.")
        return redirect(url_for("main.search"))
    queue_name = (request.form.get("queue_name") or "reprints").strip() or "reprints"
    try:
        card = _catalog().add_to_queue(queue_name, qty=qty, card_id=card_id)
    except (CardNotFound, InvalidQuantity) as e:
        flash(str(e))
        return redirect(url_for("main.search", q=request.form.get("q", "")))
    flash(f"Added {qty}× {card.name} ({card.variant_label}) to {queue_name!r}.")
    return redirect(url_for("main.queue", queue_name=queue_name))


@bp.get("/queues/<queue_name>")
@login_required
def queue(queue_name: str):
    items = _catalog().list_queue(queue_name)
    return render_template(
        "queue.html",
        queue_name=queue_name,
        items=items,
        build_result=None,
        print_cmd=None,
    )


@bp.post("/queues/<queue_name>/build")
@login_required
def build_queue(queue_name: str):
    out_dir = Path(current_app.config["SHEETS_ROOT"]) / f"sheets-{queue_name}"
    try:
        result = _catalog().build_queue(queue_name, out_dir)
    except OSError as e:
        flash(f"Build failed: {e}")
        return redirect(url_for("main.queue", queue_name=queue_name))
    items = _catalog().list_queue(queue_name)
    print_cmd = (
        f"python -m mtgproxy.cricut.printing --sheets {out_dir} --queue {queue_name}"
    )
    return render_template(
        "queue.html",
        queue_name=queue_name,
        items=items,
        build_result=result,
        print_cmd=print_cmd,
    )


@bp.get("/cards/<int:card_id>/history")
@login_required
def history(card_id: int):
    try:
        card = _catalog().resolve(card_id=card_id)
    except CardNotFound:
        abort(404)
    rows = _catalog().history(card_id=card_id)
    enriched = []
    for r in rows:
        snap = Path(r["image_snapshot_path"])
        enriched.append({"row": r, "snap_ok": snap.is_file()})
    return render_template("history.html", card=card, entries=enriched)


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
