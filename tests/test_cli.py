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
