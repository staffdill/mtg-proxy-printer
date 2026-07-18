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
