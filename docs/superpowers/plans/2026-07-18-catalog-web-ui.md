# Catalog Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a LAN-accessible Flask UI over the existing card catalog so you can search cards (with thumbnails), queue by id, build sheets, and view print history behind a single shared password.

**Architecture:** New package `mtgproxy/web/` with `create_app()` factory, session auth, Jinja templates, and light HTMX for search/add without a SPA. All mutations call `Catalog` methods; build writes `sheets-<queue>/` under a configurable root and displays the CLI print command. Partial name search is added to `Catalog.search(..., partial=False)` so the CLI stays exact-match by default.

**Tech Stack:** Python 3.13, Flask, Jinja2 (via Flask), HTMX (CDN script tag — no npm), pytest + Flask test client, existing Pillow/sqlite catalog.

**Spec:** `docs/superpowers/specs/2026-07-18-catalog-web-ui-design.md`

## Global Constraints

- Catalog-only: no Design Space / print automation from the browser.
- Password is **required** to start the server (flag or `MTGPROXY_WEB_PASSWORD`). Empty password is a hard error.
- CLI flags override env when both are set.
- Session secret: `--secret` / `MTGPROXY_WEB_SECRET`; if missing, generate ephemeral and log a warning.
- Bind default `0.0.0.0:8765` for LAN.
- UI always adds to queue by `card_id`, never by bare name.
- Image routes must reject path traversal; only serve under configured `images_dir` (including `snapshots/`).
- Add `flask` to `requirements.txt`. No Node/npm.
- All web tests use temp catalog paths (`tmp_path`); never the real repo `catalog.db`.
- Existing tests must stay green. Full suite: `python -m pytest tests/ -q`.
- Trusted LAN only — not public internet. Document in RUNBOOK briefly.

## File map

| Path | Responsibility |
|------|----------------|
| `mtgproxy/catalog.py` | Add `partial=` to `search` |
| `mtgproxy/web/__init__.py` | `create_app(config)` factory, attach catalog, teardown |
| `mtgproxy/web/__main__.py` | CLI entry: parse args, require password, run server |
| `mtgproxy/web/auth.py` | login/logout helpers, `login_required` decorator |
| `mtgproxy/web/routes.py` | Blueprints: search, queue, build, history, images |
| `mtgproxy/web/templates/base.html` | Shell, nav, flash |
| `mtgproxy/web/templates/login.html` | Password form |
| `mtgproxy/web/templates/search.html` | Search form + results region |
| `mtgproxy/web/templates/partials/results.html` | HTMX results partial |
| `mtgproxy/web/templates/queue.html` | Queue list + build |
| `mtgproxy/web/templates/history.html` | Print history |
| `mtgproxy/web/templates/404.html` / `500.html` | Error pages |
| `mtgproxy/web/static/app.css` | Dark practical styles |
| `tests/test_catalog.py` | Partial search tests |
| `tests/test_web.py` | Auth + routes integration |
| `requirements.txt` | `flask>=3.0` |
| `docs/RUNBOOK.md` | How to run the web UI on LAN |

---

### Task 1: Partial search on `Catalog.search`

**Files:**
- Modify: `mtgproxy/catalog.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Produces: `Catalog.search(self, name: str, *, partial: bool = False) -> list[CardRecord]`
  - `partial=False` (default): exact match, case-insensitive (current behavior).
  - `partial=True`: case-insensitive substring via `LIKE '%' || ? || '%'`; empty/whitespace `name` returns `[]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_catalog.py`:

```python
def test_search_partial_matches_substring(tmp_path):
    cat = _catalog(tmp_path)
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", _card_image(tmp_path))
    cat.catalog_card("Lightning Bolt", "chocobo-deck", "chocobo-deck", _card_image(tmp_path, name="Bolt"))

    matches = cat.search("ring", partial=True)

    assert len(matches) == 1
    assert matches[0].name == "Sol Ring"


def test_search_partial_is_case_insensitive(tmp_path):
    cat = _catalog(tmp_path)
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", _card_image(tmp_path))

    matches = cat.search("SOL", partial=True)

    assert len(matches) == 1


def test_search_exact_still_requires_full_name(tmp_path):
    cat = _catalog(tmp_path)
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", _card_image(tmp_path))

    assert cat.search("ring", partial=False) == []
    assert len(cat.search("Sol Ring", partial=False)) == 1


def test_search_partial_empty_query_returns_nothing(tmp_path):
    cat = _catalog(tmp_path)
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", _card_image(tmp_path))

    assert cat.search("", partial=True) == []
    assert cat.search("   ", partial=True) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_catalog.py -k "partial or exact_still" -v`

Expected: FAIL — `search() got an unexpected keyword argument 'partial'` (or similar).

- [ ] **Step 3: Write the implementation**

Replace `Catalog.search` in `mtgproxy/catalog.py` with:

```python
    def search(self, name: str, *, partial: bool = False) -> list[CardRecord]:
        needle = (name or "").strip()
        if not needle:
            return []
        if partial:
            rows = self.conn.execute(
                "SELECT * FROM cards WHERE name LIKE '%' || ? || '%' "
                "ESCAPE '\\' ORDER BY name, variant_label",
                (needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_"),),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM cards WHERE name = ? ORDER BY variant_label",
                (needle,),
            ).fetchall()
        return [_row_to_record(r) for r in rows]
```

Note: SQLite `LIKE` is case-insensitive for ASCII when using the default NOCASE collations on `name` if the column has `COLLATE NOCASE` (it does). Escaping `%`/`_` in the user needle prevents wildcard injection.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_catalog.py -v`

Expected: PASS (all catalog tests, including new ones).

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/catalog.py tests/test_catalog.py
git commit -m "feat: Catalog.search partial substring match for web UI"
```

---

### Task 2: Flask app factory + dependency

**Files:**
- Create: `mtgproxy/web/__init__.py`
- Modify: `requirements.txt`
- Test: `tests/test_web.py`

**Interfaces:**
- Produces: `create_app(config: dict | None = None) -> flask.Flask`
  - Config keys used: `SECRET_KEY` (str), `PASSWORD` (str, required non-empty), `DB_PATH` (Path|str), `IMAGES_DIR` (Path|str), `SHEETS_ROOT` (Path|str), `TESTING` (bool, optional).
  - App stores a live `Catalog` on `app.extensions["catalog"]` (or `g` via before_request); closes on teardown.
  - If `PASSWORD` missing/empty when not building a bare app for unit tests of config validation — tests always pass an explicit password.
- Produces: installable dependency `flask>=3.0` in requirements.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web.py`:

```python
from pathlib import Path

import pytest
from PIL import Image


def _card_png(path: Path, color="red"):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (60, 84), color).save(path)
    return path


def _app(tmp_path, password="secret"):
    from mtgproxy.web import create_app
    from mtgproxy.catalog import Catalog

    db = tmp_path / "catalog.db"
    images = tmp_path / "images"
    sheets = tmp_path / "sheets-root"
    sheets.mkdir()
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "PASSWORD": password,
            "DB_PATH": db,
            "IMAGES_DIR": images,
            "SHEETS_ROOT": sheets,
        }
    )
    return app


def _client(tmp_path, password="secret"):
    app = _app(tmp_path, password=password)
    return app, app.test_client()


def test_create_app_rejects_empty_password(tmp_path):
    from mtgproxy.web import create_app

    with pytest.raises(ValueError, match="password"):
        create_app(
            {
                "SECRET_KEY": "x",
                "PASSWORD": "",
                "DB_PATH": tmp_path / "c.db",
                "IMAGES_DIR": tmp_path / "img",
                "SHEETS_ROOT": tmp_path,
            }
        )


def test_unauthenticated_root_redirects_to_login(tmp_path):
    _, client = _client(tmp_path)
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_web.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'mtgproxy.web'` (and/or Flask missing).

- [ ] **Step 3: Write the implementation**

Add to `requirements.txt`:

```
flask>=3.0
```

Create `mtgproxy/web/__init__.py`:

```python
"""LAN web UI over the card catalog (search, queue, build, history)."""
from __future__ import annotations

from pathlib import Path

from flask import Flask

from mtgproxy.catalog import Catalog


def create_app(config: dict | None = None) -> Flask:
    cfg = dict(config or {})
    password = cfg.get("PASSWORD", "")
    if not password:
        raise ValueError("web UI password is required (set PASSWORD / MTGPROXY_WEB_PASSWORD)")

    app = Flask(__name__)
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

    @app.teardown_app
    def _shutdown(exc=None):
        cat = app.extensions.get("catalog")
        if cat is not None:
            cat.close()

    # Blueprints registered in later tasks; for now register a stub login redirect.
    from mtgproxy.web.auth import auth_bp, login_required
    from mtgproxy.web import routes

    app.register_blueprint(auth_bp)
    app.register_blueprint(routes.bp)

    return app
```

**Important for this task only if routes/auth do not exist yet:** implement minimal stubs so imports work:

Create `mtgproxy/web/auth.py` (minimal for Task 2; expanded in Task 3):

```python
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
```

Create `mtgproxy/web/routes.py` (minimal):

```python
from flask import Blueprint, redirect, url_for

from mtgproxy.web.auth import login_required

bp = Blueprint("main", __name__)


@bp.get("/")
@login_required
def search():
    return "search stub"
```

Install flask: `python -m pip install "flask>=3.0"`

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_web.py -v`

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add requirements.txt mtgproxy/web/__init__.py mtgproxy/web/auth.py mtgproxy/web/routes.py tests/test_web.py
git commit -m "feat: Flask app factory for catalog web UI"
```

---

### Task 3: Login / logout with shared password

**Files:**
- Modify: `mtgproxy/web/auth.py`
- Create: `mtgproxy/web/templates/base.html`, `mtgproxy/web/templates/login.html`
- Create: `mtgproxy/web/static/app.css` (minimal: enough for login + dark body)
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `create_app`, `login_required`, `app.config["PASSWORD"]`
- Produces: working `GET/POST /login`, `GET|POST /logout`; session key `logged_in=True` after success; `hmac.compare_digest` for password check.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web.py`:

```python
def test_wrong_password_stays_on_login(tmp_path):
    _, client = _client(tmp_path, password="correct")
    resp = client.post("/login", data={"password": "wrong"}, follow_redirects=True)
    assert resp.status_code == 200
    assert b"wrong" in resp.data.lower() or b"invalid" in resp.data.lower()
    # Still cannot see search
    resp2 = client.get("/")
    assert resp2.status_code == 302


def test_correct_password_reaches_search(tmp_path):
    _, client = _client(tmp_path, password="correct")
    resp = client.post("/login", data={"password": "correct"}, follow_redirects=True)
    assert resp.status_code == 200
    # After Task 4 this is the real search page; for now any 200 after login is ok
    # if root is no longer a redirect:
    resp2 = client.get("/")
    assert resp2.status_code == 200


def test_logout_clears_session(tmp_path):
    _, client = _client(tmp_path, password="correct")
    client.post("/login", data={"password": "correct"})
    client.get("/logout")
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_web.py -k "password or logout" -v`

Expected: FAIL on message content / real form (stub login does not validate).

- [ ] **Step 3: Write the implementation**

Replace `mtgproxy/web/auth.py` with:

```python
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


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("auth.login", next=request.path))
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
            nxt = request.args.get("next") or url_for("main.search")
            if not nxt.startswith("/"):
                nxt = url_for("main.search")
            return redirect(nxt)
        error = "Wrong password."
    return render_template("login.html", error=error)


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
```

Create `mtgproxy/web/templates/base.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}MTG Proxy Catalog{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='app.css') }}">
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
</head>
<body>
  {% if session.get('logged_in') %}
  <nav class="nav">
    <a href="{{ url_for('main.search') }}">Search</a>
    <a href="{{ url_for('main.queue', queue_name='reprints') }}">reprints</a>
    <a href="{{ url_for('main.queue', queue_name='one-offs') }}">one-offs</a>
    <form class="nav-queue" method="get" action="#" onsubmit="location.href='/queues/'+encodeURIComponent(this.q.value);return false;">
      <input name="q" placeholder="queue name" size="12">
      <button type="submit">Go</button>
    </form>
    <a href="{{ url_for('auth.logout') }}">Log out</a>
  </nav>
  {% endif %}
  {% with messages = get_flashed_messages() %}
    {% if messages %}
    <ul class="flash">
      {% for m in messages %}<li>{{ m }}</li>{% endfor %}
    </ul>
    {% endif %}
  {% endwith %}
  <main class="main">
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

Create `mtgproxy/web/templates/login.html`:

```html
{% extends "base.html" %}
{% block title %}Login — MTG Proxy Catalog{% endblock %}
{% block content %}
<h1>Catalog login</h1>
<p class="muted">Shared password for LAN access. Not for the public internet.</p>
{% if error %}<p class="error">{{ error }}</p>{% endif %}
<form method="post" class="login-form">
  <label>Password
    <input type="password" name="password" autofocus required>
  </label>
  <button type="submit">Log in</button>
</form>
{% endblock %}
```

Create `mtgproxy/web/static/app.css`:

```css
:root {
  --bg: #12141a;
  --panel: #1c1f28;
  --text: #e8eaf0;
  --muted: #9aa3b5;
  --accent: #6ea8fe;
  --danger: #f07178;
  --border: #2a3040;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.45;
}
.nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1rem;
  align-items: center;
  padding: 0.75rem 1rem;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
}
.nav a { color: var(--accent); text-decoration: none; }
.main { padding: 1rem; max-width: 960px; margin: 0 auto; }
.muted { color: var(--muted); }
.error { color: var(--danger); }
.flash { list-style: none; padding: 0.5rem 1rem; background: #243018; }
.login-form label { display: flex; flex-direction: column; gap: 0.35rem; max-width: 20rem; }
.login-form input, .login-form button, button, input {
  font: inherit;
  padding: 0.45rem 0.6rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text);
}
button { cursor: pointer; background: #2a3a5c; border-color: #3d5280; }
button:hover { filter: brightness(1.1); }
```

Ensure Flask finds templates/static: in `create_app`, if needed set

```python
app = Flask(__name__, template_folder="templates", static_folder="static")
```

(default relative to the `web` package works when `__name__` is `mtgproxy.web`).

Update `routes.search` temporarily to return a real template or plain “Search” string with 200 — keep as `return render_template("search.html", q="", results=None)` once Task 4 templates exist; for Task 3 use:

```python
@bp.get("/")
@login_required
def search():
    return render_template("search.html", q="", results=None)
```

and a minimal `search.html` extending base:

```html
{% extends "base.html" %}
{% block content %}<h1>Search</h1>{% endblock %}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_web.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/web/ tests/test_web.py
git commit -m "feat: web UI login with shared password session"
```

---

### Task 4: Search page with partial results + thumbnails hook

**Files:**
- Modify: `mtgproxy/web/routes.py`
- Create/modify: `mtgproxy/web/templates/search.html`, `mtgproxy/web/templates/partials/results.html`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `Catalog.search(name, partial=True)`, `login_required`
- Produces:
  - `GET /` — full search page
  - `GET /search?q=` — same page; if `HX-Request` header, return results partial only
  - Result rows include link to history and form to add (wired in Task 6)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web.py`:

```python
def _login(client, password="secret"):
    return client.post("/login", data={"password": password})


def _seed_card(tmp_path, app, name="Sol Ring", variant="chocobo-deck"):
    from mtgproxy.catalog import Catalog
    cat = app.extensions["catalog"]
    src = _card_png(tmp_path / f"{name}.png")
    return cat.catalog_card(name, variant, variant, src)


def test_search_partial_shows_card_name(tmp_path):
    app, client = _client(tmp_path)
    _seed_card(tmp_path, app)
    _login(client)
    resp = client.get("/search?q=ring")
    assert resp.status_code == 200
    assert b"Sol Ring" in resp.data
    assert b"chocobo-deck" in resp.data


def test_search_empty_query_does_not_dump_catalog(tmp_path):
    app, client = _client(tmp_path)
    _seed_card(tmp_path, app)
    _login(client)
    resp = client.get("/search?q=")
    assert resp.status_code == 200
    assert b"Sol Ring" not in resp.data
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_web.py -k search_partial -v`

Expected: FAIL (404 or name not in body).

- [ ] **Step 3: Write the implementation**

Update `mtgproxy/web/routes.py`:

```python
from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from mtgproxy.catalog import CardNotFound, InvalidQuantity
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
```

`search.html`:

```html
{% extends "base.html" %}
{% block title %}Search — MTG Proxy Catalog{% endblock %}
{% block content %}
<h1>Search</h1>
<form class="search-form"
      hx-get="{{ url_for('main.search') }}"
      hx-target="#results"
      hx-swap="innerHTML"
      hx-push-url="true">
  <input type="search" name="q" value="{{ q }}" placeholder="Card name…" autofocus>
  <button type="submit">Search</button>
</form>
<div id="results">
  {% include "partials/results.html" %}
</div>
{% endblock %}
```

`partials/results.html`:

```html
{% if results is none %}
  <p class="muted">Type part of a card name to search the catalog.</p>
{% elif not results %}
  <p class="muted">No cards match “{{ q }}”.</p>
{% else %}
  <ul class="card-list">
  {% for c in results %}
    <li class="card-row">
      <img class="thumb" src="{{ url_for('main.card_image', card_id=c.id) }}" alt="" width="90" height="126" loading="lazy">
      <div class="card-meta">
        <strong>{{ c.name }}</strong>
        <span class="muted">{{ c.variant_label }}</span>
        <span class="muted">printed {{ c.times_printed }}× · last {{ c.last_printed_at or 'never' }}</span>
        <a href="{{ url_for('main.history', card_id=c.id) }}">History</a>
      </div>
      <form class="add-form" method="post" action="{{ url_for('main.add_to_queue') }}">
        <input type="hidden" name="card_id" value="{{ c.id }}">
        <label>Qty <input type="number" name="qty" value="1" min="1" style="width:4rem"></label>
        <label>Queue <input type="text" name="queue_name" value="reprints" size="10"></label>
        <button type="submit">Add</button>
      </form>
    </li>
  {% endfor %}
  </ul>
{% endif %}
```

Add CSS for `.card-list`, `.card-row`, `.thumb` (flex row, gap, panel background).

Stub routes referenced above so templates do not 500 before later tasks — register temporary placeholders in the same file:

```python
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
    from flask import abort
    abort(404)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_web.py -v`

Expected: PASS (image 404 is fine for img tags in tests that only check HTML text).

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/web/ tests/test_web.py
git commit -m "feat: web search with partial name match"
```

---

### Task 5: Safe card (and snapshot) image routes

**Files:**
- Modify: `mtgproxy/web/routes.py`
- Test: `tests/test_web.py`

**Interfaces:**
- Produces:
  - `GET /images/cards/<int:card_id>` → file at `card.image_path` if under `images_dir`
  - `GET /images/snapshots/<path:rel>` → only if resolved path is under `images_dir / "snapshots"`
- Helper: `_safe_send(path: Path) -> Response` raises 404 if outside root.

- [ ] **Step 1: Write the failing tests**

```python
def test_card_image_returns_png(tmp_path):
    app, client = _client(tmp_path)
    cid = _seed_card(tmp_path, app)
    _login(client)
    resp = client.get(f"/images/cards/{cid}")
    assert resp.status_code == 200
    assert resp.content_type.startswith("image/")


def test_card_image_unknown_id_is_404(tmp_path):
    _, client = _client(tmp_path)
    _login(client)
    assert client.get("/images/cards/99999").status_code == 404


def test_snapshot_path_traversal_rejected(tmp_path):
    _, client = _client(tmp_path)
    _login(client)
    resp = client.get("/images/snapshots/../../outside.png")
    assert resp.status_code in (400, 404)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_web.py -k image -v`

Expected: FAIL (404 on valid card image).

- [ ] **Step 3: Write the implementation**

```python
from pathlib import Path

from flask import abort, send_file


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


@bp.get("/images/cards/<int:card_id>")
@login_required
def card_image(card_id: int):
    try:
        card = _catalog().resolve(card_id=card_id)
    except CardNotFound:
        abort(404)
    path = Path(card.image_path)
    root = Path(current_app.config["IMAGES_DIR"])
    if not path.is_file() or not _is_under(path, root):
        abort(404)
    return send_file(path)


@bp.get("/images/snapshots/<path:rel>")
@login_required
def snapshot_image(rel: str):
    root = Path(current_app.config["IMAGES_DIR"]) / "snapshots"
    path = (root / rel).resolve()
    if not path.is_file() or not _is_under(path, root):
        abort(404)
    return send_file(path)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_web.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/web/routes.py tests/test_web.py
git commit -m "feat: serve catalog card images with path safety checks"
```

---

### Task 6: Add to queue (by card id)

**Files:**
- Modify: `mtgproxy/web/routes.py`
- Test: `tests/test_web.py`

**Interfaces:**
- Produces: `POST /queue/add` with form fields `card_id`, `qty`, `queue_name`
- On success: flash + redirect to `/queues/<queue_name>`
- On `InvalidQuantity` / `CardNotFound`: flash error + redirect back

- [ ] **Step 1: Write the failing tests**

```python
def test_add_to_queue_by_id(tmp_path):
    app, client = _client(tmp_path)
    cid = _seed_card(tmp_path, app)
    _login(client)
    resp = client.post(
        "/queue/add",
        data={"card_id": cid, "qty": 2, "queue_name": "reprints"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Sol Ring" in resp.data
    assert b"2" in resp.data
    items = app.extensions["catalog"].list_queue("reprints")
    assert len(items) == 1
    assert items[0][1] == 2


def test_add_rejects_qty_zero(tmp_path):
    app, client = _client(tmp_path)
    cid = _seed_card(tmp_path, app)
    _login(client)
    client.post("/queue/add", data={"card_id": cid, "qty": 0, "queue_name": "reprints"})
    assert app.extensions["catalog"].list_queue("reprints") == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_web.py -k add_to_queue -v`

Expected: FAIL (queue empty).

- [ ] **Step 3: Write the implementation**

```python
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
```

Implement real `queue` view (list only) in the same step so redirect target works — or minimal HTML listing. Full queue page is Task 7; minimal:

```python
@bp.get("/queues/<queue_name>")
@login_required
def queue(queue_name: str):
    items = _catalog().list_queue(queue_name)
    return render_template("queue.html", queue_name=queue_name, items=items, build_result=None)
```

`queue.html` (list portion):

```html
{% extends "base.html" %}
{% block title %}Queue {{ queue_name }}{% endblock %}
{% block content %}
<h1>Queue: {{ queue_name }}</h1>
{% if not items %}
  <p class="muted">This queue is empty.</p>
{% else %}
  <ul>
  {% for card, qty in items %}
    <li>{{ qty }}× {{ card.name }} ({{ card.variant_label }})</li>
  {% endfor %}
  </ul>
{% endif %}
{% endblock %}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_web.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/web/ tests/test_web.py
git commit -m "feat: web UI add card to queue by id"
```

---

### Task 7: Build queue from the web UI

**Files:**
- Modify: `mtgproxy/web/routes.py`, `mtgproxy/web/templates/queue.html`
- Test: `tests/test_web.py`

**Interfaces:**
- Produces: `POST /queues/<queue_name>/build`
- `out_dir = Path(SHEETS_ROOT) / f"sheets-{queue_name}"`
- Renders build summary + print command:
  `python -m mtgproxy.cricut.printing --sheets <out_dir> --queue <queue_name>`

- [ ] **Step 1: Write the failing tests**

```python
def test_build_queue_writes_sheet(tmp_path):
    app, client = _client(tmp_path)
    cat = app.extensions["catalog"]
    for i in range(4):
        name = f"Card {i}"
        src = _card_png(tmp_path / f"{name}.png")
        cat.catalog_card(name, "v", "v", src)
        cat.add_to_queue("reprints", qty=1, name=name, variant_label="v")
    _login(client)
    resp = client.post("/queues/reprints/build", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Built" in resp.data or b"sheet" in resp.data.lower()
    out = Path(app.config["SHEETS_ROOT"]) / "sheets-reprints"
    assert any(out.glob("sheet*.png"))
    assert b"--queue reprints" in resp.data
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_web.py -k build_queue -v`

Expected: FAIL (404 on build route).

- [ ] **Step 3: Write the implementation**

```python
from pathlib import Path

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
```

Extend `queue.html` with Build form and result panel:

```html
<form method="post" action="{{ url_for('main.build_queue', queue_name=queue_name) }}">
  <button type="submit">Build full sheets</button>
</form>
{% if build_result %}
  <div class="build-result">
    {% if build_result.sheets %}
      <p>Built {{ build_result.sheets|length }} sheet(s) ({{ build_result.built_cards }} cards).</p>
      {% if build_result.leftover_cards %}
        <p>{{ build_result.leftover_cards }} card(s) left in '{{ queue_name }}' — not enough for a full sheet yet.</p>
      {% endif %}
      <p class="muted">Print command (copy):</p>
      <pre>{{ print_cmd }}</pre>
    {% else %}
      <p>'{{ queue_name }}' has {{ build_result.leftover_cards }} card(s) — not enough for a full sheet yet.</p>
    {% endif %}
  </div>
{% endif %}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_web.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/web/ tests/test_web.py
git commit -m "feat: build queue sheets from web UI"
```

---

### Task 8: Print history page

**Files:**
- Modify: `mtgproxy/web/routes.py`
- Create: `mtgproxy/web/templates/history.html`
- Test: `tests/test_web.py`

**Interfaces:**
- Produces: `GET /cards/<int:card_id>/history`
- 404 if card missing
- Lists `print_history` rows; snapshot img if file exists via snapshot route or direct safe send

- [ ] **Step 1: Write the failing tests**

```python
def test_history_lists_print(tmp_path):
    app, client = _client(tmp_path)
    cat = app.extensions["catalog"]
    src = _card_png(tmp_path / "Sol Ring.png")
    cat.catalog_sheet([src], deck_or_queue="sheets-test", sheet_file="sheet_01.png")
    cat.record_print("sheets-test", "sheet_01.png")
    card = cat.resolve(name="Sol Ring", variant_label="sheets-test")
    _login(client)
    resp = client.get(f"/cards/{card.id}/history")
    assert resp.status_code == 200
    assert b"sheet_01.png" in resp.data
    assert b"sheets-test" in resp.data


def test_history_unknown_card_404(tmp_path):
    _, client = _client(tmp_path)
    _login(client)
    assert client.get("/cards/99999/history").status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_web.py -k history -v`

Expected: FAIL.

- [ ] **Step 3: Write the implementation**

```python
@bp.get("/cards/<int:card_id>/history")
@login_required
def history(card_id: int):
    try:
        card = _catalog().resolve(card_id=card_id)
    except CardNotFound:
        abort(404)
    rows = _catalog().history(card_id=card_id)
    # Attach whether snapshot file exists for template
    enriched = []
    for r in rows:
        snap = Path(r["image_snapshot_path"])
        enriched.append({"row": r, "snap_ok": snap.is_file()})
    return render_template("history.html", card=card, entries=enriched)
```

`history.html`:

```html
{% extends "base.html" %}
{% block title %}History — {{ card.name }}{% endblock %}
{% block content %}
<h1>{{ card.name }} <span class="muted">({{ card.variant_label }})</span></h1>
<p class="muted">Printed {{ card.times_printed }}× · last {{ card.last_printed_at or 'never' }}</p>
{% if not entries %}
  <p class="muted">Never printed.</p>
{% else %}
  <ul class="history">
  {% for e in entries %}
    <li>
      <time>{{ e.row['printed_at'] }}</time>
      {{ e.row['deck_or_queue'] }} / {{ e.row['sheet_file'] }}
    </li>
  {% endfor %}
  </ul>
{% endif %}
<p><a href="{{ url_for('main.search', q=card.name) }}">Back to search</a></p>
{% endblock %}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_web.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/web/ tests/test_web.py
git commit -m "feat: web UI print history page"
```

---

### Task 9: CLI entrypoint + RUNBOOK

**Files:**
- Create: `mtgproxy/web/__main__.py`
- Modify: `docs/RUNBOOK.md` (add a short “Catalog web UI” section near the top or after catalog mentions)
- Test: optional small test for arg parsing of password requirement without binding a port

**Interfaces:**
- Produces: `python -m mtgproxy.web` with flags from the spec
- Flags override env; password required

- [ ] **Step 1: Write the failing test**

```python
def test_main_refuses_missing_password(monkeypatch, capsys):
    from mtgproxy.web.__main__ import main
    monkeypatch.delenv("MTGPROXY_WEB_PASSWORD", raising=False)
    rc = main(["--db", "x.db"])  # no password
    assert rc == 2
    assert "password" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Run to verify fail**

Run: `python -m pytest tests/test_web.py::test_main_refuses_missing_password -v`

Expected: FAIL — cannot import main.

- [ ] **Step 3: Implementation**

`mtgproxy/web/__main__.py`:

```python
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
```

For `test_main_refuses_missing_password` only — does not call `app.run`.

Add RUNBOOK section:

```markdown
## Catalog web UI (LAN)

Thin browser UI over the catalog (search, queue, build, history). Does **not** drive Design Space.

```bat
set MTGPROXY_WEB_PASSWORD=your-shared-password
set MTGPROXY_WEB_SECRET=long-random-string
python -m mtgproxy.web --host 0.0.0.0 --port 8765
```

Open `http://<this-pc-lan-ip>:8765/` on your phone or another PC. Trusted home LAN only — not the public internet. Do not run CLI catalog writes and the web UI against the same DB at the same time if you can avoid it.
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_web.py tests/test_catalog.py -v`

Expected: PASS.

Run full suite: `python -m pytest tests/ -q`

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/web/__main__.py docs/RUNBOOK.md tests/test_web.py
git commit -m "feat: python -m mtgproxy.web entrypoint and RUNBOOK notes"
```

---

### Task 10: Polish — 404/500 templates, CSS for card grid, session cookie flags

**Files:**
- Modify: `mtgproxy/web/__init__.py` (SESSION_COOKIE_HTTPONLY, SAMESITE)
- Create: `mtgproxy/web/templates/404.html`, `500.html`
- Modify: `mtgproxy/web/static/app.css`
- Test: smoke already covered; optional `test_session_cookie_flags` reading app.config

- [ ] **Step 1: Write test**

```python
def test_session_cookie_flags(tmp_path):
    app = _app(tmp_path)
    assert app.config.get("SESSION_COOKIE_HTTPONLY", True) is True
    assert app.config.get("SESSION_COOKIE_SAMESITE", "Lax") in ("Lax", "lax")
```

- [ ] **Step 2: Run — may pass already or fail**

- [ ] **Step 3: In `create_app` after Flask():**

```python
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # SESSION_COOKIE_SECURE left False — LAN is usually HTTP

    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("500.html"), 500
```

Minimal error templates extending base. Tighten CSS for `.card-row` (flex, wrap on mobile).

- [ ] **Step 4: Full suite**

Run: `python -m pytest tests/ -q`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/web/ tests/test_web.py
git commit -m "chore: web UI session cookie flags and error pages"
```

---

## Manual smoke (after all tasks)

```bat
set MTGPROXY_WEB_PASSWORD=dev
set MTGPROXY_WEB_SECRET=devsecret
python -m mtgproxy.web --port 8765 --db catalog.db --images-dir catalog/images
```

1. Open login, wrong password fails, right password works.
2. Search a fragment of a real catalogued card.
3. Add 1 to reprints; open queue; add until ≥4 slots; Build; confirm `sheets-reprints/` and print command.
4. Open History for a card that has been printed.

---

## Spec coverage checklist (self-review)

| Spec requirement | Task |
|------------------|------|
| Flask + Jinja + HTMX | 2–4 |
| LAN bind 0.0.0.0:8765 | 9 |
| Shared password required | 2, 3, 9 |
| Flags override env | 9 |
| Ephemeral secret warning | 9 |
| Partial search | 1, 4 |
| Add by card_id | 6 |
| Queue list | 6–7 |
| Build → sheets-`<queue>` | 7 |
| Print command with `--queue` | 7 |
| History page | 8 |
| Safe image serving | 5 |
| Tests for auth/search/add/build/history/path | 2–8 |
| RUNBOOK LAN note | 9 |
| No print automation | (out of scope — no task) |
