from flask import Blueprint, redirect, url_for

from mtgproxy.web.auth import login_required

bp = Blueprint("main", __name__)


@bp.get("/")
@login_required
def search():
    return "search stub"
