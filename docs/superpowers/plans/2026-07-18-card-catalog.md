# Card Catalog & Reprint Queues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a SQLite-backed card catalog that remembers every imported card by name+variant, lets you queue specific cards (with quantity) into named batches like `one-offs`/`reprints`, and builds those queues into ordinary `sheet_NN.png` files the existing upload/print automation already understands — with automatic cataloguing at build time and automatic print-history tracking wired into `printing.py`'s existing success signal.

**Architecture:** New `mtgproxy/catalog.py` module wrapping a SQLite database (`cards`, `print_history`, `queue_items`, `sheet_contents`) plus a `catalog/images/` folder of owned card-image copies. `separate.py` gains a `--manifest` flag to name One Piece cards from a PDF. `cli.py` catalogs every card automatically at sheet-build time. `printing.py` logs print history and drains queues automatically when a sheet clears the print gate, failing soft so bookkeeping can never block a live print run.

**Tech Stack:** Python 3.13, stdlib `sqlite3` (no new dependency), Pillow (already a dependency), pytest.

**Spec:** `docs/superpowers/specs/2026-07-18-card-catalog-design.md`

## Global Constraints

- No new dependencies. `sqlite3` is stdlib; `requirements.txt` is not touched.
- The catalog owns its own copy of every card image under `catalog/images/` — it never references `cards/`, `cards-onepiece/`, or any other loose working folder directly.
- Card identity is `(name, variant_label)`, matched case-insensitively (`COLLATE NOCASE`). `variant_label` defaults to the deck-of-origin (the `--out`/queue folder's name) and is never derived from anything else in this plan — there is no manifest syntax for an explicit per-card variant override; that's a documented future extension, not built here (YAGNI — no concrete need for it yet beyond the deck-of-origin default).
- `printing.py` must never be blocked or crashed by catalog bookkeeping. Every catalog call from `printing.py` is wrapped to fail soft (log a warning, keep going).
- Queue draining ("consumed on print") happens **only** inside `printing.py`'s success hook (`Catalog.record_print`), never inside `Catalog.build_queue`. Calling `build` twice on the same queue before printing the first batch will double-build — this is a documented usage discipline (build, then print, before adding more or building again), matching this codebase's existing "Build the project LAST" style of documented-not-enforced rules in `docs/RUNBOOK.md`.
- Sheets are always a 2×2 grid (4 cards) — `GeometryConfig().cards_per_sheet == 4`. `Catalog.build_queue` only builds complete groups of 4, oldest-queued-first (FIFO by `added_at`), and leaves any remainder queued.
- All existing tests must keep passing. Any existing test that would create a `catalog.db`/`catalog/images/` in the repo root as a side effect must be updated to point at `tmp_path` instead.

---

### Task 1: Catalog core — schema, `catalog_card`, `catalog_sheet`

**Files:**
- Create: `mtgproxy/catalog.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Produces: `DEFAULT_DB_PATH: Path`, `DEFAULT_IMAGES_DIR: Path`, `CardRecord` (dataclass: `id, name, variant_label, source_deck, image_path, first_imported_at, times_printed, last_printed_at`), exceptions `CardNotFound`, `AmbiguousCard`, `SheetNotCatalogued`, class `Catalog` with `__init__(self, db_path: Path = DEFAULT_DB_PATH, images_dir: Path = DEFAULT_IMAGES_DIR)`, `close(self) -> None`, `catalog_card(self, name: str, variant_label: str, source_deck: str, image_path: Path) -> int`, `catalog_sheet(self, card_paths: list[Path], deck_or_queue: str, sheet_file: str, variant_label: str | None = None) -> None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_catalog.py`:

```python
from pathlib import Path

from PIL import Image

from mtgproxy.catalog import Catalog


def _card_image(tmp_path, name="Sol Ring", color="red"):
    path = tmp_path / f"{name}.png"
    Image.new("RGB", (60, 84), color).save(path)
    return path


def _catalog(tmp_path):
    return Catalog(db_path=tmp_path / "catalog.db", images_dir=tmp_path / "images")


def test_catalog_card_creates_a_new_row_and_owns_a_copy_of_the_image(tmp_path):
    cat = _catalog(tmp_path)
    src = _card_image(tmp_path)

    card_id = cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", src)

    row = cat.conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    assert row["name"] == "Sol Ring"
    assert row["variant_label"] == "chocobo-deck"
    assert row["times_printed"] == 0
    stored = Path(row["image_path"])
    assert stored != src  # it's a copy, not the original path
    assert stored.is_file()
    assert stored.is_relative_to(tmp_path / "images")


def test_catalog_card_is_case_insensitive_and_updates_in_place(tmp_path):
    cat = _catalog(tmp_path)
    src1 = _card_image(tmp_path, color="red")

    id1 = cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", src1)
    id2 = cat.catalog_card("sol ring", "chocobo-deck", "chocobo-deck", src1)

    assert id1 == id2
    count = cat.conn.execute("SELECT COUNT(*) AS n FROM cards").fetchone()["n"]
    assert count == 1


def test_catalog_card_with_a_new_variant_label_creates_a_second_row(tmp_path):
    cat = _catalog(tmp_path)
    src = _card_image(tmp_path)

    id1 = cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", src)
    id2 = cat.catalog_card("Sol Ring", "masayoshi", "masayoshi", src)

    assert id1 != id2
    count = cat.conn.execute("SELECT COUNT(*) AS n FROM cards").fetchone()["n"]
    assert count == 2


def test_catalog_sheet_records_one_card_per_position(tmp_path):
    cat = _catalog(tmp_path)
    a = _card_image(tmp_path, name="Sol Ring", color="red")
    b = _card_image(tmp_path, name="Lightning Bolt", color="blue")

    cat.catalog_sheet([a, b], deck_or_queue="sheets-test", sheet_file="sheet_01.png")

    rows = cat.conn.execute(
        "SELECT position, card_id FROM sheet_contents WHERE sheet_file = ? ORDER BY position",
        ("sheet_01.png",),
    ).fetchall()
    assert [r["position"] for r in rows] == [0, 1]
    names = cat.conn.execute("SELECT name FROM cards ORDER BY name").fetchall()
    assert [n["name"] for n in names] == ["Lightning Bolt", "Sol Ring"]


def test_catalog_sheet_defaults_variant_to_deck_or_queue(tmp_path):
    cat = _catalog(tmp_path)
    src = _card_image(tmp_path)

    cat.catalog_sheet([src], deck_or_queue="sheets-onepiece", sheet_file="sheet_01.png")

    row = cat.conn.execute("SELECT variant_label FROM cards WHERE name = 'Sol Ring'").fetchone()
    assert row["variant_label"] == "sheets-onepiece"


def test_catalog_sheet_strips_duplicate_placement_suffix_from_the_name(tmp_path):
    """separate.py names repeat placements 'Sol Ring.png', 'Sol Ring (2).png' -- both
    must catalog as the SAME card, not two different cards."""
    cat = _catalog(tmp_path)
    a = tmp_path / "Sol Ring.png"
    b = tmp_path / "Sol Ring (2).png"
    Image.new("RGB", (60, 84), "red").save(a)
    Image.new("RGB", (60, 84), "red").save(b)

    cat.catalog_sheet([a, b], deck_or_queue="sheets-onepiece", sheet_file="sheet_01.png")

    rows = cat.conn.execute("SELECT name FROM cards").fetchall()
    assert [r["name"] for r in rows] == ["Sol Ring"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mtgproxy.catalog'`

- [ ] **Step 3: Write the implementation**

Create `mtgproxy/catalog.py`:

```python
"""A persistent catalog of every card ever imported, so a specific card can be
looked up and re-queued for a one-off print or a reprint without hand-assembling
an input folder again.

A card's identity is (name, variant_label), not just name — the same card name
can legitimately have different source art on different imports (a fresh Sol
Ring scan every time, say), and the catalog keeps those as separate rows rather
than overwriting one with the other. variant_label defaults to the deck it was
imported from, so a card only grows extra variants when it's genuinely
re-imported from a different source.

The catalog owns a copy of every card image under images_dir, rather than
pointing back at cards/, cards-onepiece/, etc. Those working folders are free to
be reorganized or deleted later without breaking a lookup or a reprint.
"""
from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

DEFAULT_DB_PATH = Path("catalog.db")
DEFAULT_IMAGES_DIR = Path("catalog/images")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE,
    variant_label TEXT NOT NULL COLLATE NOCASE,
    source_deck TEXT NOT NULL,
    image_path TEXT NOT NULL,
    first_imported_at TEXT NOT NULL,
    times_printed INTEGER NOT NULL DEFAULT 0,
    last_printed_at TEXT,
    UNIQUE (name, variant_label)
);

CREATE TABLE IF NOT EXISTS print_history (
    id INTEGER PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES cards(id),
    deck_or_queue TEXT NOT NULL COLLATE NOCASE,
    sheet_file TEXT NOT NULL COLLATE NOCASE,
    image_snapshot_path TEXT NOT NULL,
    printed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS queue_items (
    id INTEGER PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES cards(id),
    queue_name TEXT NOT NULL COLLATE NOCASE,
    quantity INTEGER NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE (card_id, queue_name)
);

CREATE TABLE IF NOT EXISTS sheet_contents (
    id INTEGER PRIMARY KEY,
    deck_or_queue TEXT NOT NULL COLLATE NOCASE,
    sheet_file TEXT NOT NULL COLLATE NOCASE,
    position INTEGER NOT NULL,
    card_id INTEGER NOT NULL REFERENCES cards(id)
);
"""

#: separate.py disambiguates repeat placements of the same card name with a
#: " (2)", " (3)"... suffix so each placement gets its own file on disk. The
#: catalog strips it back off -- all those placements are the same card.
_DUP_SUFFIX = re.compile(r" \(\d+\)$")


class CardNotFound(RuntimeError):
    """No card matched the given name (and variant, if given)."""


class AmbiguousCard(RuntimeError):
    """A name matched more than one variant and the caller did not disambiguate.

    Fatal, deliberately: guessing which variant means guessing which physical
    card gets queued or reprinted.
    """


class SheetNotCatalogued(RuntimeError):
    """A sheet has no sheet_contents rows -- it was printed outside the
    catalogued flow (an old deck, or a hand-built sheet)."""


@dataclass(frozen=True)
class CardRecord:
    id: int
    name: str
    variant_label: str
    source_deck: str
    image_path: str
    first_imported_at: str
    times_printed: int
    last_printed_at: str | None


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _card_name_from_path(path: Path) -> str:
    return _DUP_SUFFIX.sub("", Path(path).stem)


def _row_to_record(row: sqlite3.Row) -> CardRecord:
    return CardRecord(
        id=row["id"],
        name=row["name"],
        variant_label=row["variant_label"],
        source_deck=row["source_deck"],
        image_path=row["image_path"],
        first_imported_at=row["first_imported_at"],
        times_printed=row["times_printed"],
        last_printed_at=row["last_printed_at"],
    )


class Catalog:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH, images_dir: Path = DEFAULT_IMAGES_DIR):
        self.images_dir = Path(images_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def catalog_card(self, name: str, variant_label: str, source_deck: str, image_path: Path) -> int:
        stored = self.images_dir / f"{_slug(name)}__{_slug(variant_label)}.png"
        Image.open(image_path).save(stored, "PNG")
        self.conn.execute(
            """
            INSERT INTO cards (name, variant_label, source_deck, image_path, first_imported_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name, variant_label) DO UPDATE SET
                source_deck = excluded.source_deck,
                image_path = excluded.image_path
            """,
            (name, variant_label, source_deck, str(stored), _now()),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM cards WHERE name = ? AND variant_label = ?",
            (name, variant_label),
        ).fetchone()
        return row["id"]

    def catalog_sheet(
        self,
        card_paths: list[Path],
        deck_or_queue: str,
        sheet_file: str,
        variant_label: str | None = None,
    ) -> None:
        label = variant_label or deck_or_queue
        for position, path in enumerate(card_paths):
            name = _card_name_from_path(Path(path))
            card_id = self.catalog_card(name, label, deck_or_queue, Path(path))
            self.conn.execute(
                "INSERT INTO sheet_contents (deck_or_queue, sheet_file, position, card_id) "
                "VALUES (?, ?, ?, ?)",
                (deck_or_queue, sheet_file, position, card_id),
            )
        self.conn.commit()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/catalog.py tests/test_catalog.py
git commit -m "feat: add card catalog core -- schema, catalog_card, catalog_sheet"
```

---

### Task 2: Search, resolve, queues, history

**Files:**
- Modify: `mtgproxy/catalog.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: `Catalog`, `CardRecord`, `_row_to_record`, `CardNotFound`, `AmbiguousCard` from Task 1.
- Produces: `Catalog.search(self, name: str) -> list[CardRecord]`, `Catalog.resolve(self, name: str | None = None, variant_label: str | None = None, card_id: int | None = None) -> CardRecord`, `Catalog.add_to_queue(self, queue_name: str, qty: int = 1, name: str | None = None, variant_label: str | None = None, card_id: int | None = None) -> CardRecord`, `Catalog.list_queue(self, queue_name: str) -> list[tuple[CardRecord, int]]`, `Catalog.history(self, name: str | None = None, variant_label: str | None = None, card_id: int | None = None) -> list[sqlite3.Row]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_catalog.py`:

```python
import pytest

from mtgproxy.catalog import AmbiguousCard, CardNotFound


def test_search_is_case_insensitive(tmp_path):
    cat = _catalog(tmp_path)
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", _card_image(tmp_path))

    matches = cat.search("sol ring")

    assert len(matches) == 1
    assert matches[0].name == "Sol Ring"


def test_search_returns_every_variant(tmp_path):
    cat = _catalog(tmp_path)
    src = _card_image(tmp_path)
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", src)
    cat.catalog_card("Sol Ring", "masayoshi", "masayoshi", src)

    matches = cat.search("Sol Ring")

    assert sorted(m.variant_label for m in matches) == ["chocobo-deck", "masayoshi"]


def test_resolve_raises_ambiguous_when_variant_not_given(tmp_path):
    cat = _catalog(tmp_path)
    src = _card_image(tmp_path)
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", src)
    cat.catalog_card("Sol Ring", "masayoshi", "masayoshi", src)

    with pytest.raises(AmbiguousCard):
        cat.resolve(name="Sol Ring")


def test_resolve_by_name_and_variant_picks_the_right_one(tmp_path):
    cat = _catalog(tmp_path)
    src = _card_image(tmp_path)
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", src)
    id2 = cat.catalog_card("Sol Ring", "masayoshi", "masayoshi", src)

    found = cat.resolve(name="Sol Ring", variant_label="masayoshi")

    assert found.id == id2


def test_resolve_raises_card_not_found_for_an_unknown_name(tmp_path):
    cat = _catalog(tmp_path)

    with pytest.raises(CardNotFound):
        cat.resolve(name="Nonexistent Card")


def test_add_to_queue_then_list_queue_round_trips(tmp_path):
    cat = _catalog(tmp_path)
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", _card_image(tmp_path))

    cat.add_to_queue("reprints", qty=3, name="Sol Ring", variant_label="chocobo-deck")

    items = cat.list_queue("reprints")
    assert len(items) == 1
    card, qty = items[0]
    assert card.name == "Sol Ring"
    assert qty == 3


def test_add_to_queue_twice_accumulates_quantity(tmp_path):
    cat = _catalog(tmp_path)
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", _card_image(tmp_path))

    cat.add_to_queue("reprints", qty=2, name="Sol Ring", variant_label="chocobo-deck")
    cat.add_to_queue("reprints", qty=1, name="Sol Ring", variant_label="chocobo-deck")

    _, qty = cat.list_queue("reprints")[0]
    assert qty == 3


def test_list_queue_on_an_empty_queue_returns_nothing(tmp_path):
    cat = _catalog(tmp_path)

    assert cat.list_queue("reprints") == []


def test_history_is_empty_for_a_never_printed_card(tmp_path):
    cat = _catalog(tmp_path)
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", _card_image(tmp_path))

    assert cat.history(name="Sol Ring", variant_label="chocobo-deck") == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: FAIL — `AttributeError: 'Catalog' object has no attribute 'search'` (and similar for the other new methods)

- [ ] **Step 3: Write the implementation**

Add these methods to the `Catalog` class in `mtgproxy/catalog.py` (after `catalog_sheet`):

```python
    def search(self, name: str) -> list[CardRecord]:
        rows = self.conn.execute(
            "SELECT * FROM cards WHERE name = ? ORDER BY variant_label",
            (name,),
        ).fetchall()
        return [_row_to_record(r) for r in rows]

    def resolve(
        self,
        name: str | None = None,
        variant_label: str | None = None,
        card_id: int | None = None,
    ) -> CardRecord:
        if card_id is not None:
            row = self.conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
            if row is None:
                raise CardNotFound(f"no card with id {card_id}")
            return _row_to_record(row)

        if name is None:
            raise CardNotFound("must give a name or --id")

        if variant_label is not None:
            row = self.conn.execute(
                "SELECT * FROM cards WHERE name = ? AND variant_label = ?",
                (name, variant_label),
            ).fetchone()
            if row is None:
                raise CardNotFound(f"no card named {name!r} with variant {variant_label!r}")
            return _row_to_record(row)

        matches = self.search(name)
        if not matches:
            raise CardNotFound(f"no card named {name!r}")
        if len(matches) > 1:
            listing = ", ".join(f"{m.variant_label!r} (id={m.id})" for m in matches)
            raise AmbiguousCard(
                f"{name!r} matches {len(matches)} variants: {listing} -- pass --variant or --id"
            )
        return matches[0]

    def add_to_queue(
        self,
        queue_name: str,
        qty: int = 1,
        name: str | None = None,
        variant_label: str | None = None,
        card_id: int | None = None,
    ) -> CardRecord:
        card = self.resolve(name=name, variant_label=variant_label, card_id=card_id)
        self.conn.execute(
            """
            INSERT INTO queue_items (card_id, queue_name, quantity, added_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(card_id, queue_name) DO UPDATE SET
                quantity = quantity + excluded.quantity
            """,
            (card.id, queue_name, qty, _now()),
        )
        self.conn.commit()
        return card

    def list_queue(self, queue_name: str) -> list[tuple[CardRecord, int]]:
        rows = self.conn.execute(
            """
            SELECT cards.*, queue_items.quantity AS qty
            FROM queue_items
            JOIN cards ON cards.id = queue_items.card_id
            WHERE queue_items.queue_name = ?
            ORDER BY queue_items.added_at
            """,
            (queue_name,),
        ).fetchall()
        return [(_row_to_record(r), r["qty"]) for r in rows]

    def history(
        self,
        name: str | None = None,
        variant_label: str | None = None,
        card_id: int | None = None,
    ) -> list[sqlite3.Row]:
        card = self.resolve(name=name, variant_label=variant_label, card_id=card_id)
        return self.conn.execute(
            "SELECT * FROM print_history WHERE card_id = ? ORDER BY printed_at",
            (card.id,),
        ).fetchall()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: PASS (15 tests)

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/catalog.py tests/test_catalog.py
git commit -m "feat: add catalog search, resolve, queueing, and history"
```

---

### Task 3: `build_queue` — FIFO flattening, skip sub-4 sheets

**Files:**
- Modify: `mtgproxy/catalog.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: `Catalog`, `CardRecord` from Tasks 1-2; `mtgproxy.batch.build_sheets(card_paths: list[Path], cfg: GeometryConfig, crop: bool = False, sticker: bool = False) -> list[Image.Image]`, `mtgproxy.batch.save_sheets(sheets: list[Image.Image], out_dir: Path, dpi=300, prefix="sheet") -> list[Path]`, `mtgproxy.geometry.GeometryConfig`.
- Produces: `BuildResult` (dataclass: `sheets: list[Path], built_cards: int, leftover_cards: int`), `Catalog.build_queue(self, queue_name: str, out_dir: Path) -> BuildResult`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_catalog.py`:

```python
def _seed_queue(cat, tmp_path, names, qty=1, queue_name="reprints"):
    for name in names:
        src = _card_image(tmp_path, name=name, color="red")
        cat.catalog_card(name, "chocobo-deck", "chocobo-deck", src)
        cat.add_to_queue(queue_name, qty=qty, name=name, variant_label="chocobo-deck")


def test_build_queue_with_fewer_than_4_cards_builds_nothing(tmp_path):
    cat = _catalog(tmp_path)
    _seed_queue(cat, tmp_path, ["Sol Ring", "Lightning Bolt"])

    result = cat.build_queue("reprints", tmp_path / "out")

    assert result.sheets == []
    assert result.built_cards == 0
    assert result.leftover_cards == 2


def test_build_queue_builds_full_groups_of_4_and_leaves_the_remainder(tmp_path):
    cat = _catalog(tmp_path)
    _seed_queue(cat, tmp_path, [f"Card {i}" for i in range(5)])  # 5 cards -> 1 sheet + 1 left

    result = cat.build_queue("reprints", tmp_path / "out")

    assert len(result.sheets) == 1
    assert result.built_cards == 4
    assert result.leftover_cards == 1
    assert all(p.is_file() for p in result.sheets)


def test_build_queue_uses_fifo_order(tmp_path):
    """The 4 EARLIEST-added cards fill the first sheet; a 5th, later card is
    the one left over -- not decided by name or insertion into sqlite."""
    cat = _catalog(tmp_path)
    for name in ["Card A", "Card B", "Card C", "Card D"]:
        src = _card_image(tmp_path, name=name, color="red")
        cat.catalog_card(name, "chocobo-deck", "chocobo-deck", src)
        cat.add_to_queue("reprints", qty=1, name=name, variant_label="chocobo-deck")
    # Added last -- must be the leftover, not one of the first 4.
    src = _card_image(tmp_path, name="Card E", color="blue")
    cat.catalog_card("Card E", "chocobo-deck", "chocobo-deck", src)
    cat.add_to_queue("reprints", qty=1, name="Card E", variant_label="chocobo-deck")

    cat.build_queue("reprints", tmp_path / "out")

    remaining = cat.list_queue("reprints")
    assert len(remaining) == 1
    assert remaining[0][0].name == "Card E"


def test_build_queue_does_not_touch_queue_items(tmp_path):
    """Draining the queue happens at PRINT time, not build time -- build_queue
    must leave queue_items alone so a halted/unprinted run can still resume."""
    cat = _catalog(tmp_path)
    _seed_queue(cat, tmp_path, [f"Card {i}" for i in range(4)])

    cat.build_queue("reprints", tmp_path / "out")

    remaining = cat.list_queue("reprints")
    assert len(remaining) == 4


def test_build_queue_records_sheet_contents_for_the_built_sheet(tmp_path):
    cat = _catalog(tmp_path)
    _seed_queue(cat, tmp_path, [f"Card {i}" for i in range(4)])

    result = cat.build_queue("reprints", tmp_path / "out")

    rows = cat.conn.execute(
        "SELECT COUNT(*) AS n FROM sheet_contents WHERE deck_or_queue = 'reprints'"
    ).fetchone()
    assert rows["n"] == 4
    assert result.sheets[0].name in {r["sheet_file"] for r in cat.conn.execute(
        "SELECT DISTINCT sheet_file FROM sheet_contents"
    ).fetchall()}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: FAIL — `AttributeError: 'Catalog' object has no attribute 'build_queue'`

- [ ] **Step 3: Write the implementation**

Add these imports near the top of `mtgproxy/catalog.py`, alongside the existing ones:

```python
from mtgproxy.batch import build_sheets, save_sheets
from mtgproxy.geometry import GeometryConfig
```

Add this dataclass near `CardRecord`:

```python
@dataclass(frozen=True)
class BuildResult:
    sheets: list[Path]
    built_cards: int
    leftover_cards: int
```

Add this method to the `Catalog` class (after `history`):

```python
    def build_queue(self, queue_name: str, out_dir: Path) -> BuildResult:
        """Tile complete groups of 4 queued cards into sheet_NN.png files.

        Oldest-added cards fill sheets first. A sheet is a 2x2 grid; leaving it
        partially empty would waste a full sheet of paper and blade time on 1-3
        cards, so any remainder stays queued untouched -- build_queue never
        drains queue_items itself. That happens only when printing.py confirms
        a sheet actually printed (Catalog.record_print), so a halted run can
        resume exactly where it left off without losing or duplicating cards.
        """
        rows = self.conn.execute(
            """
            SELECT queue_items.card_id AS card_id, queue_items.quantity AS qty,
                   cards.image_path AS image_path
            FROM queue_items
            JOIN cards ON cards.id = queue_items.card_id
            WHERE queue_items.queue_name = ?
            ORDER BY queue_items.added_at
            """,
            (queue_name,),
        ).fetchall()

        flat: list[tuple[int, Path]] = []
        for row in rows:
            flat.extend([(row["card_id"], Path(row["image_path"]))] * row["qty"])

        cfg = GeometryConfig()  # bleed_mm defaults to 3.0 -- must stay non-zero so
        # layout.source_has_bleed() can auto-detect bleed vs. face-only art per
        # card when a queue mixes cards from different original decks.
        n = cfg.cards_per_sheet
        full_count = (len(flat) // n) * n
        to_build, leftover = flat[:full_count], flat[full_count:]

        if not to_build:
            return BuildResult(sheets=[], built_cards=0, leftover_cards=len(leftover))

        card_paths = [p for _, p in to_build]
        sheets = build_sheets(card_paths, cfg, sticker=True)
        written = save_sheets(sheets, Path(out_dir), dpi=cfg.dpi)

        for sheet_path, start in zip(written, range(0, len(to_build), n)):
            chunk = to_build[start : start + n]
            for position, (card_id, _) in enumerate(chunk):
                self.conn.execute(
                    "INSERT INTO sheet_contents (deck_or_queue, sheet_file, position, card_id) "
                    "VALUES (?, ?, ?, ?)",
                    (queue_name, sheet_path.name, position, card_id),
                )
        self.conn.commit()
        return BuildResult(sheets=written, built_cards=len(to_build), leftover_cards=len(leftover))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: PASS (20 tests)

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/catalog.py tests/test_catalog.py
git commit -m "feat: add catalog build_queue -- FIFO, skip sub-4 sheets"
```

---

### Task 4: `record_print` — automatic print history + queue draining

**Files:**
- Modify: `mtgproxy/catalog.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: `Catalog`, `SheetNotCatalogued` from Task 1.
- Produces: `Catalog.record_print(self, deck_or_queue: str, sheet_file: str) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_catalog.py`:

```python
from mtgproxy.catalog import SheetNotCatalogued


def test_record_print_raises_when_the_sheet_was_never_catalogued(tmp_path):
    cat = _catalog(tmp_path)

    with pytest.raises(SheetNotCatalogued):
        cat.record_print("sheets-test", "sheet_99.png")


def test_record_print_bumps_times_printed_and_logs_history(tmp_path):
    cat = _catalog(tmp_path)
    src = _card_image(tmp_path)
    cat.catalog_sheet([src], deck_or_queue="sheets-test", sheet_file="sheet_01.png")

    cat.record_print("sheets-test", "sheet_01.png")

    card = cat.resolve(name="Sol Ring", variant_label="sheets-test")
    assert card.times_printed == 1
    assert card.last_printed_at is not None
    history = cat.history(card_id=card.id)
    assert len(history) == 1
    assert history[0]["sheet_file"] == "sheet_01.png"


def test_record_print_counts_the_same_card_twice_if_it_appears_twice_on_a_sheet(tmp_path):
    cat = _catalog(tmp_path)
    src = _card_image(tmp_path)
    cat.catalog_sheet([src, src], deck_or_queue="sheets-test", sheet_file="sheet_01.png")

    cat.record_print("sheets-test", "sheet_01.png")

    card = cat.resolve(name="Sol Ring", variant_label="sheets-test")
    assert card.times_printed == 2


def test_record_print_drains_a_matching_queue(tmp_path):
    cat = _catalog(tmp_path)
    src = _card_image(tmp_path)
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", src)
    cat.add_to_queue("reprints", qty=2, name="Sol Ring", variant_label="chocobo-deck")
    # Simulate build_queue putting ONE copy of it on a sheet.
    card = cat.resolve(name="Sol Ring", variant_label="chocobo-deck")
    cat.conn.execute(
        "INSERT INTO sheet_contents (deck_or_queue, sheet_file, position, card_id) "
        "VALUES ('reprints', 'sheet_01.png', 0, ?)",
        (card.id,),
    )
    cat.conn.commit()

    cat.record_print("reprints", "sheet_01.png")

    remaining = cat.list_queue("reprints")
    assert len(remaining) == 1
    assert remaining[0][1] == 1  # 2 - 1 printed = 1 left


def test_record_print_deletes_the_queue_row_once_fully_printed(tmp_path):
    cat = _catalog(tmp_path)
    src = _card_image(tmp_path)
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", src)
    cat.add_to_queue("reprints", qty=1, name="Sol Ring", variant_label="chocobo-deck")
    card = cat.resolve(name="Sol Ring", variant_label="chocobo-deck")
    cat.conn.execute(
        "INSERT INTO sheet_contents (deck_or_queue, sheet_file, position, card_id) "
        "VALUES ('reprints', 'sheet_01.png', 0, ?)",
        (card.id,),
    )
    cat.conn.commit()

    cat.record_print("reprints", "sheet_01.png")

    assert cat.list_queue("reprints") == []


def test_record_print_on_an_ordinary_deck_does_not_touch_any_queue(tmp_path):
    """deck_or_queue for a normal deck build is a deck folder name, not a
    queue -- there's nothing in queue_items for it, and that must be a no-op,
    not an error."""
    cat = _catalog(tmp_path)
    src = _card_image(tmp_path)
    cat.catalog_sheet([src], deck_or_queue="sheets-chocobo", sheet_file="sheet_01.png")

    cat.record_print("sheets-chocobo", "sheet_01.png")  # must not raise
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: FAIL — `AttributeError: 'Catalog' object has no attribute 'record_print'`

- [ ] **Step 3: Write the implementation**

Add this method to the `Catalog` class (after `build_queue`):

```python
    def record_print(self, deck_or_queue: str, sheet_file: str) -> None:
        """Log a real, successful print. Called from printing.py's existing
        per-sheet success point -- never from anywhere speculative.

        Raises SheetNotCatalogued if this sheet has no sheet_contents rows
        (an old deck printed before the catalog existed, or a hand-built
        sheet). The caller (printing.py) treats that as soft-fail: warn and
        keep going, never halt a live print run over bookkeeping.
        """
        rows = self.conn.execute(
            "SELECT card_id FROM sheet_contents WHERE deck_or_queue = ? AND sheet_file = ?",
            (deck_or_queue, sheet_file),
        ).fetchall()
        if not rows:
            raise SheetNotCatalogued(
                f"no sheet_contents for {deck_or_queue}/{sheet_file} -- "
                "printed outside the catalogued flow"
            )

        now = _now()
        counts: dict[int, int] = {}
        for row in rows:
            card_id = row["card_id"]
            counts[card_id] = counts.get(card_id, 0) + 1
            image_path = self.conn.execute(
                "SELECT image_path FROM cards WHERE id = ?", (card_id,)
            ).fetchone()["image_path"]
            self.conn.execute(
                """
                INSERT INTO print_history
                    (card_id, deck_or_queue, sheet_file, image_snapshot_path, printed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (card_id, deck_or_queue, sheet_file, image_path, now),
            )
            self.conn.execute(
                "UPDATE cards SET times_printed = times_printed + 1, last_printed_at = ? "
                "WHERE id = ?",
                (now, card_id),
            )

        for card_id, count in counts.items():
            self.conn.execute(
                "UPDATE queue_items SET quantity = quantity - ? "
                "WHERE card_id = ? AND queue_name = ?",
                (count, card_id, deck_or_queue),
            )
            self.conn.execute(
                "DELETE FROM queue_items WHERE card_id = ? AND queue_name = ? AND quantity <= 0",
                (card_id, deck_or_queue),
            )
        self.conn.commit()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: PASS (26 tests)

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/catalog.py tests/test_catalog.py
git commit -m "feat: add catalog record_print -- history + queue draining on real prints"
```

---

### Task 5: `catalog.py` CLI (`search`, `add`, `list`, `build`, `history`)

**Files:**
- Modify: `mtgproxy/catalog.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: everything from Tasks 1-4.
- Produces: `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_catalog.py`:

```python
from mtgproxy.catalog import main


def _args(tmp_path, *rest):
    return ["--db", str(tmp_path / "catalog.db"), "--images-dir", str(tmp_path / "images"), *rest]


def test_main_search_reports_no_matches(tmp_path, capsys):
    rc = main(_args(tmp_path, "search", "Sol Ring"))
    assert rc == 1
    assert "no cards match" in capsys.readouterr().out.lower()


def test_main_search_lists_a_match(tmp_path, capsys):
    cat = _catalog(tmp_path)
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", _card_image(tmp_path))
    cat.close()

    rc = main(_args(tmp_path, "search", "sol ring"))

    assert rc == 0
    out = capsys.readouterr().out
    assert "Sol Ring" in out and "chocobo-deck" in out


def test_main_add_then_list_round_trips(tmp_path, capsys):
    cat = _catalog(tmp_path)
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", _card_image(tmp_path))
    cat.close()

    rc = main(_args(
        tmp_path, "add", "Sol Ring", "--variant", "chocobo-deck", "--to", "reprints", "--qty", "3",
    ))
    assert rc == 0

    rc = main(_args(tmp_path, "list", "reprints"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "3x" in out and "Sol Ring" in out


def test_main_add_reports_ambiguous_variant(tmp_path, capsys):
    cat = _catalog(tmp_path)
    src = _card_image(tmp_path)
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", src)
    cat.catalog_card("Sol Ring", "masayoshi", "masayoshi", src)
    cat.close()

    rc = main(_args(tmp_path, "add", "Sol Ring", "--to", "reprints"))

    assert rc == 1
    assert "matches 2 variants" in capsys.readouterr().err


def test_main_build_reports_sheets_and_leftover(tmp_path, capsys):
    cat = _catalog(tmp_path)
    for name in [f"Card {i}" for i in range(5)]:
        src = _card_image(tmp_path, name=name, color="red")
        cat.catalog_card(name, "chocobo-deck", "chocobo-deck", src)
        cat.add_to_queue("reprints", qty=1, name=name, variant_label="chocobo-deck")
    cat.close()

    rc = main(_args(tmp_path, "build", "reprints", "--out", str(tmp_path / "out")))

    assert rc == 0
    out = capsys.readouterr().out
    assert "Built 1 sheet" in out
    assert "1 card(s) left" in out
    assert len(list((tmp_path / "out").glob("*.png"))) == 1


def test_main_build_fails_loudly_when_an_owned_image_is_missing(tmp_path, capsys):
    cat = _catalog(tmp_path)
    for name in [f"Card {i}" for i in range(4)]:
        src = _card_image(tmp_path, name=name, color="red")
        cat.catalog_card(name, "chocobo-deck", "chocobo-deck", src)
        cat.add_to_queue("reprints", qty=1, name=name, variant_label="chocobo-deck")
    card = cat.resolve(name="Card 0", variant_label="chocobo-deck")
    Path(card.image_path).unlink()  # simulate a deleted owned copy
    cat.close()

    rc = main(_args(tmp_path, "build", "reprints", "--out", str(tmp_path / "out")))

    assert rc == 1
    assert "error" in capsys.readouterr().err.lower()


def test_main_history_reports_never_printed(tmp_path, capsys):
    cat = _catalog(tmp_path)
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", _card_image(tmp_path))
    cat.close()

    rc = main(_args(tmp_path, "history", "Sol Ring", "--variant", "chocobo-deck"))

    assert rc == 0
    assert "never been printed" in capsys.readouterr().out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: FAIL — `ImportError: cannot import name 'main' from 'mtgproxy.catalog'`

- [ ] **Step 3: Write the implementation**

Add these imports near the top of `mtgproxy/catalog.py`:

```python
import argparse
import sys
```

Add this at the bottom of `mtgproxy/catalog.py`:

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Look up, queue, and rebuild sheets for previously imported cards."
    )
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Catalog database path.")
    parser.add_argument(
        "--images-dir", default=str(DEFAULT_IMAGES_DIR), help="Catalog's owned image storage."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="Find a card by name.")
    p_search.add_argument("name")

    p_add = sub.add_parser("add", help="Queue a card for a build.")
    p_add.add_argument("name", nargs="?")
    p_add.add_argument("--variant")
    p_add.add_argument("--id", type=int, dest="card_id")
    p_add.add_argument("--to", required=True, dest="queue_name")
    p_add.add_argument("--qty", type=int, default=1)

    p_list = sub.add_parser("list", help="Show what's queued.")
    p_list.add_argument("queue_name")

    p_build = sub.add_parser("build", help="Tile a queue's cards into sheet_NN.png files.")
    p_build.add_argument("queue_name")
    p_build.add_argument("--out", required=True)

    p_history = sub.add_parser("history", help="Show a card's print history.")
    p_history.add_argument("name", nargs="?")
    p_history.add_argument("--variant")
    p_history.add_argument("--id", type=int, dest="card_id")

    args = parser.parse_args(argv)
    cat = Catalog(db_path=Path(args.db), images_dir=Path(args.images_dir))
    try:
        if args.command == "search":
            matches = cat.search(args.name)
            if not matches:
                print(f"no cards match {args.name!r}")
                return 1
            for m in matches:
                print(
                    f"[{m.id}] {m.name} ({m.variant_label}) -- imported {m.first_imported_at}, "
                    f"printed {m.times_printed}x, last {m.last_printed_at or 'never'}"
                )
            return 0

        if args.command == "add":
            try:
                card = cat.add_to_queue(
                    args.queue_name,
                    qty=args.qty,
                    name=args.name,
                    variant_label=args.variant,
                    card_id=args.card_id,
                )
            except (CardNotFound, AmbiguousCard) as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            print(f"added {args.qty}x {card.name} ({card.variant_label}) to {args.queue_name!r}")
            return 0

        if args.command == "list":
            items = cat.list_queue(args.queue_name)
            if not items:
                print(f"{args.queue_name!r} is empty")
                return 0
            for card, qty in items:
                print(f"  {qty}x {card.name} ({card.variant_label})")
            return 0

        if args.command == "build":
            try:
                result = cat.build_queue(args.queue_name, Path(args.out))
            except OSError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            if not result.sheets:
                print(
                    f"{args.queue_name!r} has {result.leftover_cards} card(s) -- "
                    "not enough for a full sheet yet"
                )
                return 0
            print(f"Built {len(result.sheets)} sheet(s) ({result.built_cards} cards).", end=" ")
            if result.leftover_cards:
                print(
                    f"{result.leftover_cards} card(s) left in {args.queue_name!r} -- "
                    "not enough for a full sheet yet."
                )
            else:
                print()
            return 0

        if args.command == "history":
            try:
                card = cat.resolve(name=args.name, variant_label=args.variant, card_id=args.card_id)
            except (CardNotFound, AmbiguousCard) as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            rows = cat.history(card_id=card.id)
            if not rows:
                print(f"{card.name} ({card.variant_label}) has never been printed")
                return 0
            for r in rows:
                print(f"  {r['printed_at']}  {r['deck_or_queue']}/{r['sheet_file']}")
            return 0

        return 1
    finally:
        cat.close()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: PASS (33 tests)

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/catalog.py tests/test_catalog.py
git commit -m "feat: add catalog CLI -- search, add, list, build, history"
```

---

### Task 6: `separate.py` — name One Piece cards from a manifest

**Files:**
- Modify: `mtgproxy/separate.py`
- Test: `tests/test_separate.py`

**Interfaces:**
- Produces: `save_named_cards(cards: list[Image.Image], out_dir: Path, names: list[str]) -> list[Path]`; `separate_path(..., names: list[str] | None = None)` (new keyword param); `main()` gains `--manifest`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_separate.py`:

```python
from mtgproxy.separate import save_named_cards


def test_save_named_cards_uses_the_real_card_name(tmp_path):
    cards = [Image.new("RGB", (10, 14), "red"), Image.new("RGB", (10, 14), "blue")]
    written = save_named_cards(cards, tmp_path / "out", ["Sol Ring", "Lightning Bolt"])

    assert [p.name for p in written] == ["Sol Ring.png", "Lightning Bolt.png"]
    assert all(p.exists() for p in written)


def test_save_named_cards_disambiguates_duplicate_names(tmp_path):
    cards = [Image.new("RGB", (10, 14), c) for c in ("red", "green", "blue")]
    written = save_named_cards(cards, tmp_path / "out", ["Sol Ring", "Sol Ring", "Lightning Bolt"])

    assert [p.name for p in written] == ["Sol Ring.png", "Sol Ring (2).png", "Lightning Bolt.png"]


def test_save_named_cards_rejects_a_count_mismatch(tmp_path):
    cards = [Image.new("RGB", (10, 14), "red")]
    with pytest.raises(ValueError):
        save_named_cards(cards, tmp_path / "out", ["Sol Ring", "Lightning Bolt"])


def test_separate_path_uses_a_manifest_when_given(tmp_path):
    sheet = _grid_sheet(2, 2, card_w=40, card_h=56)
    src = tmp_path / "sheet.png"
    sheet.save(src)
    out = tmp_path / "cards"

    written = separate_path(src, out, cols=2, rows=2, names=["A", "B", "C", "D"])

    assert sorted(p.name for p in written) == ["A.png", "B.png", "C.png", "D.png"]


def test_main_with_manifest_names_output_files(tmp_path, capsys):
    sheet = _grid_sheet(2, 2, card_w=20, card_h=28)
    src = tmp_path / "s.png"
    sheet.save(src)
    manifest = tmp_path / "names.txt"
    manifest.write_text("Sol Ring\nLightning Bolt\nCounterspell\nForce of Will\n", encoding="utf-8")
    out = tmp_path / "cards"

    rc = main([
        "--input", str(src), "--out", str(out),
        "--cols", "2", "--rows", "2", "--manifest", str(manifest),
    ])

    assert rc == 0
    assert sorted(p.name for p in out.glob("*.png")) == [
        "Counterspell.png", "Force of Will.png", "Lightning Bolt.png", "Sol Ring.png",
    ]


def test_main_manifest_not_found_is_an_error(tmp_path, capsys):
    sheet = _grid_sheet(2, 2)
    src = tmp_path / "s.png"
    sheet.save(src)

    rc = main([
        "--input", str(src), "--out", str(tmp_path / "cards"),
        "--manifest", str(tmp_path / "nope.txt"),
    ])

    assert rc == 1
    assert "error" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_separate.py -v`
Expected: FAIL — `ImportError: cannot import name 'save_named_cards' from 'mtgproxy.separate'`

- [ ] **Step 3: Write the implementation**

Add this function to `mtgproxy/separate.py`, right after `save_cards`:

```python
def save_named_cards(cards: list[Image.Image], out_dir: Path, names: list[str]) -> list[Path]:
    """Write cards named after their real card name, in placement order.

    Duplicate placements of the same name (a card printed more than once in
    the deck) are disambiguated with a " (2)", " (3)"... suffix so each
    placement gets its own file. The catalog normalizes that suffix back off
    when it identifies the card -- all those placements are the same card.
    """
    if len(cards) != len(names):
        raise ValueError(
            f"{len(cards)} card(s) but {len(names)} manifest name(s) -- must match exactly"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    seen: dict[str, int] = {}
    written: list[Path] = []
    for card, name in zip(cards, names):
        seen[name] = seen.get(name, 0) + 1
        n = seen[name]
        filename = f"{name}.png" if n == 1 else f"{name} ({n}).png"
        path = out_dir / filename
        to_save = card if card.mode in ("RGB", "RGBA") else card.convert("RGBA")
        to_save.save(path, "PNG")
        written.append(path)
    return written


def _read_manifest_names(path: Path) -> list[str]:
    names = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        names.append(line)
    return names
```

Modify `separate_path`'s signature and body (add the `names` parameter, and dispatch on it at the end):

```python
def separate_path(
    source: Path,
    out_dir: Path,
    *,
    cols: int = 3,
    rows: int = 3,
    gap_px: int = 0,
    margin_px: int = 0,
    auto_margin: bool = True,
    prefix: str = "card",
    names: list[str] | None = None,
) -> list[Path]:
    """Dispatch on file type and write individual cards to ``out_dir``."""
    suffix = source.suffix.lower()
    if suffix in PDF_EXTS:
        cards = extract_cards_from_pdf(source)
    elif suffix in IMAGE_EXTS:
        img = Image.open(source)
        if auto_margin and margin_px == 0:
            cards = split_grid_image_auto(img, cols, rows, gap_px=gap_px)
        else:
            cards = split_grid_image(
                img, cols, rows, margin_px=margin_px, gap_px=gap_px
            )
    else:
        raise ValueError(
            f"unsupported input type {suffix!r}; expected PDF or image "
            f"({', '.join(sorted(IMAGE_EXTS | PDF_EXTS))})"
        )
    if not cards:
        raise ValueError(f"no cards found in {source}")
    if names is not None:
        return save_named_cards(cards, out_dir, names)
    return save_cards(cards, out_dir, prefix=prefix)
```

Add the `--manifest` argument to `main`'s parser (after `--prefix`):

```python
    parser.add_argument(
        "--manifest",
        default=None,
        help="Text file, one card name per line in placement order (top-to-bottom, "
        "left-to-right), used to name output files after real card names instead of "
        "card_NNN.png. Needed for the catalog to know what each card actually is.",
    )
```

Modify `main`'s body to read the manifest and pass `names` through:

```python
    source = Path(args.input)
    if not source.is_file():
        print(f"error: input file not found: {source}", file=sys.stderr)
        return 1

    names = None
    if args.manifest:
        manifest_path = Path(args.manifest)
        if not manifest_path.is_file():
            print(f"error: manifest not found: {manifest_path}", file=sys.stderr)
            return 1
        names = _read_manifest_names(manifest_path)

    try:
        written = separate_path(
            source,
            Path(args.out),
            cols=args.cols,
            rows=args.rows,
            gap_px=args.gap_px,
            margin_px=args.margin_px,
            auto_margin=not args.no_auto_margin,
            prefix=args.prefix,
            names=names,
        )
    except (ValueError, ImportError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_separate.py -v`
Expected: PASS (all tests, including the 6 new ones)

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/separate.py tests/test_separate.py
git commit -m "feat: name separated cards from a manifest instead of card_NNN.png"
```

---

### Task 7: `cli.py` — automatic cataloguing at sheet-build time

**Files:**
- Modify: `mtgproxy/cli.py`
- Modify: `tests/test_cli.py` (existing tests need `--catalog-db`/`--catalog-images-dir` pointed at `tmp_path` so they stop creating `catalog.db` in the repo root)

**Interfaces:**
- Consumes: `mtgproxy.catalog.Catalog`, `Catalog.catalog_sheet`.
- Produces: `cli.main` gains `--catalog-db`/`--catalog-images-dir` args; every `cli.py` run catalogs its cards as a side effect.

- [ ] **Step 1: Write the failing tests**

First, update the *existing* tests in `tests/test_cli.py` so they don't touch the real repo root — replace the whole file:

```python
from PIL import Image
from mtgproxy.cli import main


def _make_images(folder, n):
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        Image.new("RGB", (100, 140), "red").save(folder / f"card_{i}.png")


def _catalog_args(tmp_path):
    return ["--catalog-db", str(tmp_path / "catalog.db"),
            "--catalog-images-dir", str(tmp_path / "catalog-images")]


def test_main_generates_sheets(tmp_path, capsys):
    inp = tmp_path / "cards"
    out = tmp_path / "out"
    _make_images(inp, 6)  # 6 cards -> 2 sheets

    rc = main(["--input", str(inp), "--out", str(out)] + _catalog_args(tmp_path))
    assert rc == 0

    produced = sorted(p.name for p in out.glob("*.png"))
    assert produced == ["sheet_1.png", "sheet_2.png"]

    summary = capsys.readouterr().out
    assert "2 sheet" in summary
    assert "6 card" in summary


def test_main_returns_1_for_missing_input_dir(tmp_path, capsys):
    rc = main(
        ["--input", str(tmp_path / "nope"), "--out", str(tmp_path / "o")] + _catalog_args(tmp_path)
    )
    assert rc == 1
    assert "error" in capsys.readouterr().err.lower()


def test_main_returns_1_for_bad_manifest_quantity(tmp_path, capsys):
    inp = tmp_path / "cards"
    inp.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 140), "red").save(inp / "card.png")
    manifest = tmp_path / "order.txt"
    manifest.write_text("card.png,abc\n", encoding="utf-8")

    rc = main(
        ["--input", str(inp), "--out", str(tmp_path / "o"), "--manifest", str(manifest)]
        + _catalog_args(tmp_path)
    )
    assert rc == 1
    assert "error" in capsys.readouterr().err.lower()


def test_main_returns_1_for_gap_less_than_2x_bleed(tmp_path, capsys):
    inp = tmp_path / "cards"
    inp.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 140), "red").save(inp / "card.png")

    rc = main(
        [
            "--input", str(inp),
            "--out", str(tmp_path / "o"),
            "--bleed", "5",
            "--gap", "8",
        ] + _catalog_args(tmp_path)
    )
    assert rc == 1
    assert "error" in capsys.readouterr().err.lower()


def test_main_returns_1_for_sticker_gap_below_design_space_bleed(tmp_path, capsys):
    inp = tmp_path / "cards"
    inp.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 140), "red").save(inp / "card.png")

    rc = main(
        [
            "--input", str(inp),
            "--out", str(tmp_path / "o"),
            "--sticker",
            "--bleed", "0",
            "--gap", "2",
        ] + _catalog_args(tmp_path)
    )
    assert rc == 1
    assert "error" in capsys.readouterr().err.lower()


def test_main_catalogs_every_card_by_name(tmp_path):
    from mtgproxy.catalog import Catalog

    inp = tmp_path / "cards"
    inp.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 140), "red").save(inp / "Sol Ring.png")
    Image.new("RGB", (100, 140), "blue").save(inp / "Lightning Bolt.png")
    out = tmp_path / "out"

    rc = main(["--input", str(inp), "--out", str(out)] + _catalog_args(tmp_path))
    assert rc == 0

    cat = Catalog(db_path=tmp_path / "catalog.db", images_dir=tmp_path / "catalog-images")
    names = sorted(m.name for m in cat.search("Sol Ring") + cat.search("Lightning Bolt"))
    assert names == ["Lightning Bolt", "Sol Ring"]
    card = cat.resolve(name="Sol Ring")
    assert card.variant_label == "out"  # defaults to the --out folder's name


def test_main_records_sheet_contents_matching_the_written_sheet_files(tmp_path):
    from mtgproxy.catalog import Catalog

    inp = tmp_path / "cards"
    _make_images(inp, 4)  # exactly one sheet
    out = tmp_path / "out"

    rc = main(["--input", str(inp), "--out", str(out)] + _catalog_args(tmp_path))
    assert rc == 0

    cat = Catalog(db_path=tmp_path / "catalog.db", images_dir=tmp_path / "catalog-images")
    rows = cat.conn.execute(
        "SELECT DISTINCT sheet_file FROM sheet_contents WHERE deck_or_queue = 'out'"
    ).fetchall()
    assert [r["sheet_file"] for r in rows] == ["sheet_1.png"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — `error: unrecognized arguments: --catalog-db ...`

- [ ] **Step 3: Write the implementation**

Modify `mtgproxy/cli.py`'s imports (add alongside the existing ones):

```python
from mtgproxy.catalog import DEFAULT_DB_PATH, DEFAULT_IMAGES_DIR, Catalog
```

Add these two arguments to `main`'s parser, after `--sticker`:

```python
    parser.add_argument(
        "--catalog-db", default=str(DEFAULT_DB_PATH), help="Card catalog database path."
    )
    parser.add_argument(
        "--catalog-images-dir",
        default=str(DEFAULT_IMAGES_DIR),
        help="Card catalog's owned image storage.",
    )
```

Modify the body of `main` — right after `written = save_sheets(sheets, Path(args.out), dpi=cfg.dpi)`, add the cataloguing loop:

```python
    written = save_sheets(sheets, Path(args.out), dpi=cfg.dpi)

    cat = Catalog(db_path=Path(args.catalog_db), images_dir=Path(args.catalog_images_dir))
    try:
        deck_name = Path(args.out).name
        n = cfg.cards_per_sheet
        for sheet_path, start in zip(written, range(0, len(card_paths), n)):
            chunk = card_paths[start : start + n]
            cat.catalog_sheet(chunk, deck_or_queue=deck_name, sheet_file=sheet_path.name)
    finally:
        cat.close()

    print(f"Wrote {len(written)} sheet(s) from {len(card_paths)} card(s) to {args.out}")
```

(Remove the old, now-duplicate `print(f"Wrote {len(written)} sheet(s)...")` line that used to come immediately after `save_sheets` — keep only the one shown above, after the cataloguing block.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS (all tests, including the 2 new ones)

Also run the full suite to confirm nothing else broke:

Run: `python -m pytest tests/ -v`
Expected: PASS (all tests except any requiring live hardware, which this plan does not touch)

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/cli.py tests/test_cli.py
git commit -m "feat: catalog every card automatically when cli.py builds sheets"
```

---

### Task 8: `printing.py` — automatic print history, fail soft

**Files:**
- Modify: `mtgproxy/cricut/printing.py`
- Test: `tests/test_cricut.py`

**Interfaces:**
- Consumes: `mtgproxy.catalog.Catalog`, `Catalog.record_print`, `Catalog.catalog_sheet`, `SheetNotCatalogued`.
- Produces: `printing._record_print(cat: Catalog, deck_or_queue: str, sheet_file: str) -> None`; `printing.main` gains `--catalog-db`/`--catalog-images-dir` and calls `_record_print` after each sheet that clears `print_sheet` successfully.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cricut.py`:

```python
def test_record_print_warns_but_does_not_raise_for_an_uncatalogued_sheet(tmp_path, capsys):
    from mtgproxy.cricut import printing
    from mtgproxy.catalog import Catalog

    cat = Catalog(db_path=tmp_path / "catalog.db", images_dir=tmp_path / "images")

    printing._record_print(cat, "sheets-onepiece", "sheet_01.png")  # never catalogued

    assert "catalog" in capsys.readouterr().out.lower()


def test_record_print_logs_history_for_a_catalogued_sheet(tmp_path):
    from mtgproxy.cricut import printing
    from mtgproxy.catalog import Catalog
    from PIL import Image

    cat = Catalog(db_path=tmp_path / "catalog.db", images_dir=tmp_path / "images")
    img = tmp_path / "Sol Ring.png"
    Image.new("RGB", (60, 84), "red").save(img)
    cat.catalog_sheet([img], deck_or_queue="sheets-test", sheet_file="sheet_01.png")

    printing._record_print(cat, "sheets-test", "sheet_01.png")

    card = cat.resolve(name="Sol Ring", variant_label="sheets-test")
    assert card.times_printed == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_cricut.py -v -k record_print`
Expected: FAIL — `AttributeError: module 'mtgproxy.cricut.printing' has no attribute '_record_print'`

- [ ] **Step 3: Write the implementation**

Modify `mtgproxy/cricut/printing.py`'s imports (add alongside the existing ones):

```python
from mtgproxy.catalog import DEFAULT_DB_PATH, DEFAULT_IMAGES_DIR, Catalog, SheetNotCatalogued
```

Add this function after `print_sheet`:

```python
def _record_print(cat: Catalog, deck_or_queue: str, sheet_file: str) -> None:
    """Log a sheet's real, successful print in the catalog.

    Never lets catalog bookkeeping break a live print run: a sheet printed
    outside the catalogued flow (an old deck, a hand-built sheet) just warns
    and moves on, and so does any other catalog error -- the print already
    happened, real paper and ink are already spent, and nothing here should
    be able to turn that into a crashed run.
    """
    try:
        cat.record_print(deck_or_queue, sheet_file)
    except SheetNotCatalogued as e:
        print(f"      catalog: {e}")
    except Exception as e:  # noqa: BLE001 -- deliberately broad, see docstring
        print(f"      catalog: unexpected error recording print history: {e}")
```

Add the two catalog arguments to `main`'s parser, after `--auto-print`:

```python
    parser.add_argument(
        "--catalog-db", default=str(DEFAULT_DB_PATH), help="Card catalog database path."
    )
    parser.add_argument(
        "--catalog-images-dir",
        default=str(DEFAULT_IMAGES_DIR),
        help="Card catalog's owned image storage.",
    )
```

Modify the per-sheet loop near the end of `main` to open the catalog once and record each successful print. Replace:

```python
    for i, sheet in enumerate(todo, start=1):
        try:
            print_sheet(screen, sheet, everything, i, len(todo), auto_print=args.auto_print)
        except (TemplateNotFound, WrongSheet, native.DialogNotFound,
                native.DesignSpaceNotFocused, RuntimeError) as e:
```

with:

```python
    cat = Catalog(db_path=Path(args.catalog_db), images_dir=Path(args.catalog_images_dir))
    for i, sheet in enumerate(todo, start=1):
        try:
            print_sheet(screen, sheet, everything, i, len(todo), auto_print=args.auto_print)
            _record_print(cat, folder.name, sheet.name)
        except (TemplateNotFound, WrongSheet, native.DialogNotFound,
                native.DesignSpaceNotFocused, RuntimeError) as e:
```

(everything else in that `except` block and the rest of `main` is unchanged.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_cricut.py -v -k record_print`
Expected: PASS (2 tests)

Run the full suite to confirm nothing else broke:

Run: `python -m pytest tests/ -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/cricut/printing.py tests/test_cricut.py
git commit -m "feat: log print history and drain queues automatically on a real print"
```

---

## Post-plan smoke test (manual, not automated)

Not a task with its own commit — a sanity pass once all 8 tasks are in, to confirm the whole chain works end to end with real (small, synthetic) data:

```bash
python -m pytest tests/ -v
```

Expected: full suite green. Then, optionally, walk the CLI by hand against a scratch folder:

```bash
python -m mtgproxy.catalog --db ./scratch/catalog.db --images-dir ./scratch/images search "anything"
```

Expected: `no cards match 'anything'` and exit code 1 — confirms the CLI wires up cleanly outside of pytest.
