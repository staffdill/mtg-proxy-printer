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
