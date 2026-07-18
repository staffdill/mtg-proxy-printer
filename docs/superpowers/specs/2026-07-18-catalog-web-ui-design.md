# Catalog Web UI — Design Spec

**Date:** 2026-07-18
**Status:** Approved design, ready for implementation planning
**Depends on:** `docs/superpowers/specs/2026-07-18-card-catalog-design.md` (implemented)

## Goal

Expose the card catalog's day-to-day operations through a simple browser UI so you can
search by name, see art thumbnails, queue reprints/one-offs with quantities, build full
sheets, and inspect print history — without typing CLI flags.

The UI is a thin layer over `mtgproxy.catalog.Catalog`. It does **not** drive Design Space
or the printer. After a successful build it shows the same hand-off command the CLI already
prints (`python -m mtgproxy.cricut.printing --sheets … --queue …`).

## Constraints (from product decisions)

| Decision | Choice |
|----------|--------|
| Scope | Catalog only (search, queue, build, history) |
| Access | LAN (`0.0.0.0`), not public internet |
| Auth | Single shared password |
| Find cards | Search + thumbnails (not a full-catalog grid as the primary UX) |
| Stack | Flask + Jinja + light HTMX |

## Explicitly out of scope

- Upload / print / Design Space automation from the browser
- Multi-user accounts, OAuth, or production-grade auth
- Retroactive cataloguing of old decks
- Public deployment (cloud, reverse proxy hardening beyond basic notes)
- Gradio/Streamlit or a SPA framework (React/Vue)

## Architecture

New package `mtgproxy/web/`:

```
mtgproxy/web/
  __init__.py       # create_app(config) factory
  __main__.py       # python -m mtgproxy.web
  auth.py           # login, logout, session gate
  routes.py         # pages + HTMX partials
  templates/        # Jinja HTML
  static/           # app.css (+ minimal JS only if HTMX alone is not enough)
```

**Process model:** one long-lived Flask process on the Windows print machine (or any
machine that can read/write the same `catalog.db` and `catalog/images/`). SQLite stays
file-backed; the web process is the only concurrent writer expected in normal use (CLI
and web should not hammer the DB at the same time — document as usage discipline).

**Dependencies:** add `flask` to `requirements.txt`. Prefer vendoring HTMX via a pinned
static file (or CDN only if we document offline risk); no Node/npm build step.

**Config (env and/or CLI flags):**

| Name | Purpose | Default |
|------|---------|---------|
| `MTGPROXY_WEB_PASSWORD` / `--password` | Shared login password | **required** (refuse to start without one) |
| `MTGPROXY_WEB_SECRET` / `--secret` | Flask session signing key | required in production-ish use; if missing, generate ephemeral and log a warning (sessions invalidate on restart) |
| `--host` | Bind address | `0.0.0.0` |
| `--port` | Port | `8765` |
| `--db` | Catalog database path | `catalog.db` |
| `--images-dir` | Owned images dir | `catalog/images` |
| `--sheets-root` | Parent dir for build output | `.` (writes `sheets-<queue>/`) |

Run:

```text
set MTGPROXY_WEB_PASSWORD=...
set MTGPROXY_WEB_SECRET=...
python -m mtgproxy.web --host 0.0.0.0 --port 8765
```

Then open `http://<machine-lan-ip>:8765/` from phone or another PC.

## Mapping UI → catalog API

| UI action | Catalog / filesystem |
|-----------|----------------------|
| Search | Extended search (see below); display `CardRecord` fields + thumbnail from `image_path` |
| Add to queue | `add_to_queue(..., card_id=..., qty=...)` — **always by id** from the UI |
| List queue | `list_queue(queue_name)` |
| Build | `build_queue(queue_name, out_dir)` with `out_dir = sheets_root / f"sheets-{queue_name}"` |
| History | `history(card_id=...)` |
| Thumbnails | `GET` that streams a file under `images_dir` (or snapshots) after path-safety checks |

### Search behavior change

CLI `Catalog.search` today is exact name equality (`WHERE name = ?`). The web UX needs
substring match. Implementation options (pick one in the plan; recommended first):

1. **Preferred:** add `Catalog.search(name, *, partial: bool = False)` (or a separate
   `search_partial`) so CLI stays exact and web uses partial, case-insensitive
   `LIKE '%' || ? || '%'` with `COLLATE NOCASE` semantics.
2. Keep exact search only — rejected for this product; users will type fragments.

Add-from-UI always uses `card_id` so variant disambiguation is visual (one row per
variant), never name-only guessing.

## Screens

### Login — `GET/POST /login`

- Single password field.
- On success: set session (`logged_in=True`), redirect to search.
- On failure: re-render with error; no user enumeration beyond “wrong password”.
- Unauthenticated access to any other route → redirect to `/login`.

### Search — `GET /` (and HTMX partial for results)

- Query field: card name fragment.
- Results: list/grid of cards with:
  - thumbnail (~120px)
  - name, variant_label, times_printed, last_printed_at
  - qty input (default 1), queue name input (default `reprints`), **Add** button
- Empty query: prompt to type; no full-catalog dump.
- No matches: clear empty state.

### Queues — `GET /queues/<queue_name>`

- Current `list_queue` rows (qty × name × variant).
- **Build** button → POST → run `build_queue` → flash/result panel:
  - sheets written (paths or count)
  - leftover count message (same wording spirit as CLI)
  - copyable print command including `--queue <queue_name>`
- Empty queue: say so; Build still allowed (no-op soft result).

### History — `GET /cards/<id>/history`

- Resolve card by id; 404 if missing.
- Chronological `print_history` rows: `printed_at`, `deck_or_queue`, `sheet_file`.
- If `image_snapshot_path` exists on disk, show a small thumbnail; else omit image.

### Navigation (logged-in shell)

- Search · Queue shortcut (reprints / one-offs / free-text field) · Log out
- Minimal single CSS file; practical dark UI; no third-party CSS framework required.

## Auth & security

- **Password required at process start.** Empty/missing password → exit with error (do not
  start an open LAN server by accident).
- Compare password with `hmac.compare_digest`.
- Session cookie: HttpOnly, `SameSite=Lax`, signed with Flask `SECRET_KEY`.
- Serve only files whose resolved path is under the configured `images_dir` (and
  snapshots subdir). Reject path traversal.
- CSRF: same-origin POSTs + session cookie are acceptable for home LAN v1; document that
  this is not hardened for hostile networks.
- **Not for the public internet.** RUNBOOK note: use on trusted LAN only.

## Error handling

| Case | Behavior |
|------|----------|
| Not logged in | Redirect to login |
| Wrong password | Inline error |
| `CardNotFound` / bad id | 404 page or flash |
| `InvalidQuantity` | Flash / form error |
| Build leftover &lt; 4 | Soft success message, exit path still 200 |
| Missing owned image during build | Error message, no partial silent blank |
| Missing thumbnail file | Placeholder image/icon, page still 200 |
| Unexpected exception | Generic 500 template; log server-side |

Catalog open/read errors during a request fail that request clearly; do not crash the
whole process if a single handler fails.

## Testing

New `tests/test_web.py` using Flask test client + temp catalog (same style as
`tests/test_catalog.py`):

- unauthenticated `/` redirects to login
- wrong password rejected; correct password reaches search
- search partial match returns catalogued cards
- add-by-id updates queue; list queue page shows qty
- build with 4 cards creates sheet files under configured sheets root
- history page lists a recorded print (seed via `Catalog.record_print`)
- image route refuses paths outside images_dir

No browser E2E, no live Design Space. Full existing suite must remain green.

## File / CLI surface summary

```text
python -m mtgproxy.web [--host 0.0.0.0] [--port 8765]
                       [--db catalog.db] [--images-dir catalog/images]
                       [--sheets-root .]
                       [--password ...] [--secret ...]
```

Password/secret may come from env instead of flags (flags override env if both set —
define one rule in the plan and stick to it: **flags override env**).

## Follow-ups (not this release)

- Optional CSRF tokens / rate-limit login
- Browse-all catalog grid page
- Trigger or status for print jobs
- HTTPS via reverse proxy docs
- Multi-device shared secret rotation UX

## Success criteria

1. From a phone on the LAN, log in with the shared password.
2. Search a fragment of a known card name; see thumbnail + variants.
3. Add qty to `reprints`; see it on the queue page.
4. With ≥4 queued slots, Build produces `sheet_*.png` and shows the `--queue` print command.
5. History for a printed card shows entries without using the CLI.
6. Tests cover auth gate + main flows without hardware.
