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
