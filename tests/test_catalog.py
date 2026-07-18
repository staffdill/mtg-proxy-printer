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


# Task 2: Search, resolve, queues, history

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


def test_resolve_by_card_id_returns_the_correct_card(tmp_path):
    cat = _catalog(tmp_path)
    card_id = cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", _card_image(tmp_path))

    found = cat.resolve(card_id=card_id)

    assert found.id == card_id
    assert found.name == "Sol Ring"


def test_resolve_raises_card_not_found_for_an_unknown_card_id(tmp_path):
    cat = _catalog(tmp_path)

    with pytest.raises(CardNotFound):
        cat.resolve(card_id=999999)


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


# Task 3: build_queue -- FIFO flattening, skip sub-4 sheets


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

    built_names = {
        r["name"] for r in cat.conn.execute(
            "SELECT DISTINCT cards.name FROM sheet_contents "
            "JOIN cards ON cards.id = sheet_contents.card_id "
            "WHERE sheet_contents.deck_or_queue = 'reprints'"
        ).fetchall()
    }
    assert built_names == {"Card A", "Card B", "Card C", "Card D"}

    # queue_items is untouched by build_queue -- all 5 are still queued,
    # draining only happens when printing.py confirms an actual print.
    remaining = cat.list_queue("reprints")
    assert len(remaining) == 5


def test_build_queue_does_not_touch_queue_items(tmp_path):
    """Draining the queue happens at PRINT time, not build time -- build_queue
    must leave queue_items alone so a halted/unprinted run can still resume."""
    cat = _catalog(tmp_path)
    _seed_queue(cat, tmp_path, [f"Card {i}" for i in range(4)])

    cat.build_queue("reprints", tmp_path / "out")

    remaining = cat.list_queue("reprints")
    assert len(remaining) == 4


def test_build_queue_does_not_lose_quantity_when_a_card_straddles_the_leftover_boundary(tmp_path):
    """A single queue_items row can have quantity > 1. If build_queue only
    builds PART of that quantity (some copies land in a full sheet, the rest
    are the leftover), it must not touch that row at all -- draining only
    happens at print time, and it must never lose track of how many copies
    are still queued."""
    cat = _catalog(tmp_path)
    src = _card_image(tmp_path, name="Sol Ring", color="red")
    cat.catalog_card("Sol Ring", "chocobo-deck", "chocobo-deck", src)
    cat.add_to_queue("reprints", qty=5, name="Sol Ring", variant_label="chocobo-deck")

    result = cat.build_queue("reprints", tmp_path / "out")

    assert result.built_cards == 4
    assert result.leftover_cards == 1
    remaining = cat.list_queue("reprints")
    assert len(remaining) == 1
    card, qty = remaining[0]
    assert card.name == "Sol Ring"
    assert qty == 5  # untouched -- draining happens at print time, not build time


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


# Task 4: record_print -- automatic print history + queue draining


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


def test_a_queue_built_sheet_drains_correctly_when_printed_with_the_queue_name(tmp_path):
    """The real seam between build_queue and record_print: printing.py must be
    told the QUEUE name (not the --out folder name) so draining actually finds
    the sheet_contents rows build_queue recorded under the queue name."""
    cat = _catalog(tmp_path)
    for name in [f"Card {i}" for i in range(4)]:
        src = _card_image(tmp_path, name=name, color="red")
        cat.catalog_card(name, "chocobo-deck", "chocobo-deck", src)
        cat.add_to_queue("reprints", qty=1, name=name, variant_label="chocobo-deck")

    # A deliberately different folder name than the queue name -- the exact
    # documented workflow (catalog build reprints --out ./sheets-reprints).
    result = cat.build_queue("reprints", tmp_path / "sheets-reprints")
    assert len(result.sheets) == 1

    # printing.py must pass the QUEUE name, not the folder's basename, for
    # this to find the sheet_contents rows build_queue actually wrote.
    cat.record_print("reprints", result.sheets[0].name)

    assert cat.list_queue("reprints") == []
    card = cat.resolve(name="Card 0", variant_label="chocobo-deck")
    assert card.times_printed == 1


def test_catalog_sheet_rebuilding_the_same_sheet_does_not_duplicate_sheet_contents(tmp_path):
    cat = _catalog(tmp_path)
    a = _card_image(tmp_path, name="Sol Ring", color="red")
    b = _card_image(tmp_path, name="Lightning Bolt", color="blue")

    cat.catalog_sheet([a, b], deck_or_queue="sheets-test", sheet_file="sheet_01.png")
    cat.catalog_sheet([a, b], deck_or_queue="sheets-test", sheet_file="sheet_01.png")  # rebuild

    rows = cat.conn.execute(
        "SELECT COUNT(*) AS n FROM sheet_contents WHERE deck_or_queue = 'sheets-test' "
        "AND sheet_file = 'sheet_01.png'"
    ).fetchone()
    assert rows["n"] == 2  # one row per position (2 cards), not 4 from two inserts


# Task 5: CLI -- search, add, list, build, history

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
