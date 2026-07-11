from PIL import Image
from mtgproxy.cli import main


def _make_images(folder, n):
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        Image.new("RGB", (100, 140), "red").save(folder / f"card_{i}.png")


def test_main_generates_sheets(tmp_path, capsys):
    inp = tmp_path / "cards"
    out = tmp_path / "out"
    _make_images(inp, 6)  # 6 cards -> 2 sheets

    rc = main(["--input", str(inp), "--out", str(out)])
    assert rc == 0

    produced = sorted(p.name for p in out.glob("*.png"))
    assert produced == ["sheet_1.png", "sheet_2.png"]

    summary = capsys.readouterr().out
    assert "2 sheet" in summary
    assert "6 card" in summary


def test_main_returns_1_for_missing_input_dir(tmp_path, capsys):
    rc = main(["--input", str(tmp_path / "nope"), "--out", str(tmp_path / "o")])
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
    )
    assert rc == 1
    assert "error" in capsys.readouterr().err.lower()
