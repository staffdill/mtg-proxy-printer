from __future__ import annotations

import hmac
from functools import wraps

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

auth_bp = Blueprint("auth", __name__)


def _safe_next(nxt: str | None) -> str:
    """Return nxt only if it is a local relative path; else search URL.

    Rejects protocol-relative (//…), backslashes, and CR/LF which browsers
    can treat as open redirects.
    """
    search = url_for("main.search")
    if not nxt:
        return search
    if not nxt.startswith("/") or nxt.startswith("//"):
        return search
    if "\\" in nxt or "\r" in nxt or "\n" in nxt:
        return search
    return nxt


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            # Only preserve next for safe methods; POST-only routes would
            # become a broken GET after re-login.
            if request.method in ("GET", "HEAD"):
                return redirect(url_for("auth.login", next=request.path))
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("main.search"))
    error = None
    if request.method == "POST":
        offered = request.form.get("password") or ""
        expected = current_app.config["PASSWORD"]
        if hmac.compare_digest(offered.encode("utf-8"), expected.encode("utf-8")):
            session["logged_in"] = True
            session.permanent = True
            nxt = _safe_next(request.args.get("next"))
            return redirect(nxt)
        error = "Wrong password."
    return render_template("login.html", error=error)


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
