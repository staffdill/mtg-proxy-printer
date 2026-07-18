from functools import wraps

from flask import Blueprint, current_app, redirect, request, session, url_for

auth_bp = Blueprint("auth", __name__)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@auth_bp.get("/login")
def login():
    from flask import render_template_string
    return render_template_string("<h1>login stub</h1>"), 200


@auth_bp.post("/login")
def login_post():
    return redirect("/login")


@auth_bp.post("/logout")
@auth_bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
