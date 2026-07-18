from flask import Blueprint, render_template

from mtgproxy.web.auth import login_required

bp = Blueprint("main", __name__)


@bp.get("/")
@login_required
def search():
    return render_template("search.html", q="", results=None)


@bp.get("/queues/<queue_name>")
@login_required
def queue(queue_name: str):
    # Stub until queue UI task; keeps base.html nav url_for working.
    return f"queue stub: {queue_name}", 200
