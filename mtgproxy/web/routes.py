from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from mtgproxy.web.auth import login_required

bp = Blueprint("main", __name__)


def _catalog():
    return current_app.extensions["catalog"]


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
def card_image(card_id):
    abort(404)
