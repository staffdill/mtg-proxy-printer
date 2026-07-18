# Card Catalog & Reprint Queues — Design Spec

**Date:** 2026-07-18
**Status:** Approved design, ready for implementation planning

## Goal

The proxy pipeline currently has no persistent memory of what's been printed. Sheets are
flat, anonymous images (`sheet_01.png`, ...) and — for the One Piece PDF path — even the
individual card images before tiling are anonymous (`card_001.png`, ...). There is no way
to answer "have we printed this card before," and no way to build a small sheet from a
handful of specific cards without hand-assembling an input folder.

This adds a catalog that:

1. Remembers every card ever imported, by name (and by *variant*, since the same card
   name — e.g. "Sol Ring" — may legitimately be reprinted from different source art over
   time).
2. Lets you search that catalog and add specific cards, with a quantity, to a named queue
   (`one-offs`, `reprints`, or anything else you want to call one).
3. Builds a queue into ordinary `sheet_NN.png` files — the same shape `cli.py` already
   produces — so `upload.py`/`printing.py` need no changes to print them.
4. Automatically tracks print history, tied to `printing.py`'s existing per-sheet success
   signal, with no extra step to remember.

**Explicitly out of scope for this spec:**

- Bleed/cut consistency. That's a hardware/calibration checklist item (Print Then Cut
  calibration, Base Material selection), not new code — see `docs/RUNBOOK.md`.
- A user interface. This spec is CLI-only, matching how the rest of this tool works today.
  A UI is a natural follow-up once there's a catalog with real operations to expose, but
  it's a separate design.
- Retroactively cataloguing existing decks (chocobo-deck, robin, masayoshi, etc.). Only
  decks built through `cli.py`/`separate.py` after this ships get catalogued. No backfill.

## Architecture

New module `mtgproxy/catalog.py`, backed by SQLite (`catalog.db` in the repo root, via
Python's stdlib `sqlite3` — no new dependency). A relational store fits because every
requirement here is a query ("find this card," "what's queued," "when was this last
printed") — a flat JSON/YAML file would fight that as the catalog grows.

Alongside the DB, `catalog/images/` holds the catalog's **own copy** of each card's
single-card image, named by a slug of `(name, variant_label)`. The catalog owns this copy
rather than pointing at `cards/`, `cards-onepiece/`, etc. so that cleaning up those loose
working folders later can't silently break a lookup or a reprint.

## Data model

```sql
CREATE TABLE cards (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL COLLATE NOCASE,
    variant_label   TEXT NOT NULL,       -- defaults to deck-of-origin; can be overridden
    source_deck     TEXT NOT NULL,       -- the deck this variant was actually imported from
    image_path      TEXT NOT NULL,       -- catalog's own copy, under catalog/images/
    first_imported_at TEXT NOT NULL,
    times_printed   INTEGER NOT NULL DEFAULT 0,
    last_printed_at TEXT,
    UNIQUE (name, variant_label COLLATE NOCASE)
);

CREATE TABLE print_history (
    id                INTEGER PRIMARY KEY,
    card_id           INTEGER NOT NULL REFERENCES cards(id),
    deck_or_queue     TEXT NOT NULL,
    sheet_file        TEXT NOT NULL,
    image_snapshot_path TEXT NOT NULL,   -- the exact image printed, even if the card's
                                          -- canonical image_path is later re-imported
    printed_at        TEXT NOT NULL
);

CREATE TABLE queue_items (
    id          INTEGER PRIMARY KEY,
    card_id     INTEGER NOT NULL REFERENCES cards(id),
    queue_name  TEXT NOT NULL,
    quantity    INTEGER NOT NULL,
    added_at    TEXT NOT NULL,
    UNIQUE (card_id, queue_name)
);

CREATE TABLE sheet_contents (
    id              INTEGER PRIMARY KEY,
    deck_or_queue   TEXT NOT NULL,
    sheet_file      TEXT NOT NULL,
    position        INTEGER NOT NULL,    -- 0-3, the sheet's 2x2 grid slot
    card_id         INTEGER NOT NULL REFERENCES cards(id)
);
```

### Identity model

A card is identified by `(name, variant_label)`, not by name alone. Re-importing the same
name **and** the same variant label updates that row in place (new image replaces the old,
`first_imported_at` untouched). A new `variant_label` for an existing name creates a new
row — this is how "Sol Ring, but different art each time" is represented: each art gets
its own catalog entry, and `add`/`search` disambiguate between them explicitly rather than
guessing.

`variant_label` defaults to the deck-of-origin (the `--out` folder's name) at import time,
so a card only gets multiple variants when it's genuinely re-imported from a different
deck/source — no extra typing for the common case of a card that only ever has one
version on file. An explicit override (e.g. `"Judge Promo"`) can be supplied via the
manifest instead, when the default deck-name label isn't descriptive enough.

`print_history` is append-only and keeps its own snapshot path so a card's full print
history stays traceable to exactly what art was used at each point in time, independent
of the canonical `cards.image_path` being updated later.

## Integration points

### `separate.py` — new `--manifest` flag

A text file, one card name per line, in the same order cards come out of the PDF
(top-to-bottom, left-to-right — the order `extract_cards_from_pdf` already walks
placements, which already preserves duplicate quantities via repeated placements). When
given, output files are named after the real card name instead of `card_NNN.png`. This is
the only change needed in `separate.py` — everything downstream then sees a named file,
exactly like the MTG/MPC-Autofill path already does today.

### `cli.py` — automatic cataloguing at sheet-build time

`cli.py` already has every card's resolved path and knows which sheet/grid position it
lands on (`batch.build_sheets` chunks `cards_per_sheet` at a time). At this point it now
also, per card:

- creates or updates the `(name, variant_label)` row in `cards` (variant defaults to the
  `--out` folder's basename)
- copies the card's image into `catalog/images/` if new or changed
- inserts a `sheet_contents` row: `(deck_or_queue=<out folder name>, sheet_file, position,
  card_id)`

This runs for **every** `cli.py` invocation, not just queue builds — so `sheet_contents`
covers ordinary full-deck runs too, and `printing.py`'s hook (below) works uniformly for
both.

### `printing.py` — automatic print history + queue draining

When a sheet clears the print gate successfully (the existing `reset_after_print` success
point — no new gate logic, no new risk to the live-hardware flow), it looks up that
sheet's rows in `sheet_contents` and, for each card:

- appends a `print_history` row
- bumps `times_printed` / `last_printed_at` on the `cards` row
- if `deck_or_queue` is a queue name: decrements `queue_items.quantity` by the number of
  positions consumed for that card, deleting the row at zero (this is the actual
  "consumed on print" moment)

**Fails soft, not hard.** If a sheet has no matching `sheet_contents` row (an old deck
folder printed before this feature existed, or a hand-built sheet outside the normal
flow), this logs a warning and continues. `printing.py` is a carefully-tuned live-hardware
script; catalog bookkeeping must never be able to block or break an actual print run. A
halted/unprinted sheet leaves its cards' queue rows untouched, so resuming with
`--start-at` (as today) just picks up where it left off — no double-counting, no lost
queue state.

### New: `catalog.py build <queue_name> --out <folder>`

Not a modification to the print pipeline — a new producer that feeds it. Resolves a
queue's cards to their owned images and calls the same `build_sheets`/`save_sheets`
functions `cli.py` already uses, writing `sheet_NN.png` into a normal deck-shaped folder
and recording `sheet_contents` for it exactly as `cli.py` does. From there it's just
`upload.py`/`printing.py` as normal.

Uses a non-zero `GeometryConfig(bleed_mm=3)` regardless of what's in the queue — mixing
MTG (bleed) and One Piece (face-only) cards on the same built sheet works correctly as-is
because `layout.source_has_bleed()` auto-detects per-image from aspect ratio; a non-zero
`bleed_mm` is required for that detection to run at all (it short-circuits to "no bleed"
when `bleed_mm <= 0`), so `build` must never pass `0` even for an all-face-only queue.

### Quantity and sub-4 sheets

`add` takes `--qty N` (default 1), stored on `queue_items.quantity`.

`build` flattens the queue into individual card slots (respecting quantity), **oldest
`added_at` first**, and builds full sheets only from complete groups of 4 — a 2×2 grid
left partially empty by `layout.py` would waste a full sheet of paper and blade time on
1-3 cards. Any remainder (1-3 leftover slots) stays queued untouched. `build` reports what
happened, e.g.:

```
Built 2 sheet(s) (8 cards). 3 card(s) left in 'reprints' — not enough for a full sheet yet.
```

This makes `build` safe to call repeatedly as more cards are added — it's a no-op on the
leftover until it crosses a multiple of 4.

## CLI command surface

```
python -m mtgproxy.catalog search "sol ring"
    # lists every variant: index, name, variant_label, first imported, times printed, last printed

python -m mtgproxy.catalog add "sol ring" --variant chocobo-deck --to reprints --qty 3
    # or: --id 42 --to reprints, when the row is already known from a search

python -m mtgproxy.catalog list reprints
    # shows what's currently queued, before committing to a build

python -m mtgproxy.catalog build reprints --out ./sheets-reprints
    # tiles complete groups of 4 into sheet_NN.png files; reports any leftover

python -m mtgproxy.catalog history "sol ring" --variant chocobo-deck
    # print_history for that specific variant
```

## Error handling & edge cases

- Name matching is case-insensitive (`COLLATE NOCASE`).
- `add` refuses to guess when a name matches multiple variants and neither `--variant` nor
  `--id` is given — same discipline as the rest of this codebase (never risk queuing or
  printing the wrong card). It prints the disambiguating list instead.
- `build` on an empty or sub-4 queue is a no-op with a clear message, not an error.
- A missing owned image file (deleted from `catalog/images/` by hand, disk issue, etc.)
  fails `build` loudly for that card rather than silently producing a sheet with a blank
  grid position.
- `printing.py`'s hook fails soft (see above) — a missing `sheet_contents` match warns and
  continues; it never halts a live print run.

## Testing

New `tests/test_catalog.py`, following the existing style — real SQLite against a temp
file, no mocking, matching how this suite already avoids fakes where the real thing is
cheap:

- schema creation, add/search, case-insensitive name matching, variant disambiguation
  (refuses to guess on an ambiguous `add`)
- quantity add → partial print → correct remaining quantity
- `build`'s FIFO flattening and sub-4 leftover behavior (0, 3, 4, 5, 8 cards → correct
  sheet count + correct leftover)
- `cli.py` integration: building sheets populates `cards` + `sheet_contents` correctly,
  including the deck-of-origin variant default
- `printing.py` integration: a successful sheet updates `print_history` and decrements
  queue quantity; a sheet with no matching `sheet_contents` row logs a warning and does
  not raise
- `separate.py`'s manifest-driven naming produces correctly-named output files in PDF
  placement order

## Follow-ups (not in this spec)

- A UI over `catalog.py`'s operations.
- Retroactive cataloguing of existing decks already printed before this shipped.
- Bleed/cut consistency work (calibration-driven, not code).
