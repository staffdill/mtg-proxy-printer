from pathlib import Path

import pytest
from PIL import Image

from mtgproxy.separate import (
    detect_content_margin,
    extract_cards_from_pdf,
    main,
    save_cards,
    save_named_cards,
    separate_path,
    split_grid_image,
    split_grid_image_auto,
)


def _grid_sheet(cols: int, rows: int, card_w: int = 60, card_h: int = 84, gap: int = 0, margin: int = 0) -> Image.Image:
    """Build a synthetic multi-card sheet; each cell is a unique solid color."""
    w = 2 * margin + cols * card_w + (cols - 1) * gap
    h = 2 * margin + rows * card_h + (rows - 1) * gap
    sheet = Image.new("RGB", (w, h), "white")
    n = 0
    for r in range(rows):
        for c in range(cols):
            n += 1
            color = ((n * 40) % 256, (n * 70) % 256, (n * 110) % 256)
            x = margin + c * (card_w + gap)
            y = margin + r * (card_h + gap)
            sheet.paste(Image.new("RGB", (card_w, card_h), color), (x, y))
    return sheet


def test_split_grid_image_equal_cells():
    sheet = _grid_sheet(3, 2, card_w=50, card_h=70)
    cards = split_grid_image(sheet, 3, 2)
    assert len(cards) == 6
    assert all(c.size == (50, 70) for c in cards)
    # top-left and top-middle differ (unique colors)
    assert cards[0].getpixel((25, 35)) != cards[1].getpixel((25, 35))


def test_split_grid_image_with_margin_and_gap():
    sheet = _grid_sheet(2, 2, card_w=40, card_h=60, gap=4, margin=10)
    cards = split_grid_image(sheet, 2, 2, margin_px=10, gap_px=4)
    assert len(cards) == 4
    assert all(c.size == (40, 60) for c in cards)


def test_split_grid_rejects_bad_grid():
    sheet = Image.new("RGB", (100, 100), "red")
    with pytest.raises(ValueError):
        split_grid_image(sheet, 0, 2)


def test_detect_content_margin_trims_white():
    sheet = Image.new("RGB", (200, 200), "white")
    sheet.paste(Image.new("RGB", (80, 100), "blue"), (20, 30))
    left, top, right, bottom = detect_content_margin(sheet)
    assert left == 20 and top == 30
    assert right == 100 and bottom == 130


def test_split_grid_image_auto_ignores_page_margin():
    # Content is a 2x2 block inset in a larger white page
    inner = _grid_sheet(2, 2, card_w=40, card_h=50)
    page = Image.new("RGB", (200, 200), "white")
    page.paste(inner, (30, 40))
    cards = split_grid_image_auto(page, 2, 2)
    assert len(cards) == 4
    assert all(c.size == (40, 50) for c in cards)


def test_save_cards_zero_pads(tmp_path):
    cards = [Image.new("RGB", (10, 14), "red") for _ in range(12)]
    written = save_cards(cards, tmp_path / "out", prefix="card")
    assert [p.name for p in written] == [f"card_{i:03d}.png" for i in range(1, 13)]
    assert all(p.exists() for p in written)


def test_separate_path_from_sheet_image(tmp_path):
    sheet = _grid_sheet(3, 3, card_w=30, card_h=42)
    src = tmp_path / "sheet.png"
    sheet.save(src)
    out = tmp_path / "cards"
    written = separate_path(src, out, cols=3, rows=3)
    assert len(written) == 9
    assert all(Image.open(p).size == (30, 42) for p in written)


def test_extract_cards_from_pdf_preserves_duplicates(tmp_path):
    fitz = pytest.importorskip("fitz")

    # Two placements of the same image (deck quantity 2) + one other
    a = Image.new("RGB", (60, 84), (200, 0, 0))
    b = Image.new("RGB", (60, 84), (0, 200, 0))
    a_path = tmp_path / "a.png"
    b_path = tmp_path / "b.png"
    a.save(a_path)
    b.save(b_path)

    doc = fitz.open()
    page = doc.new_page(width=200, height=100)
    # place a, a, b left-to-right
    page.insert_image(fitz.Rect(0, 0, 60, 84), filename=str(a_path))
    page.insert_image(fitz.Rect(70, 0, 130, 84), filename=str(a_path))
    page.insert_image(fitz.Rect(140, 0, 200, 84), filename=str(b_path))
    pdf_path = tmp_path / "deck.pdf"
    doc.save(pdf_path)
    doc.close()

    cards = extract_cards_from_pdf(pdf_path)
    assert len(cards) == 3
    assert all(c.size == (60, 84) for c in cards)
    # first two are the red card, third is green
    assert cards[0].getpixel((30, 42)) == (200, 0, 0)
    assert cards[1].getpixel((30, 42)) == (200, 0, 0)
    assert cards[2].getpixel((30, 42)) == (0, 200, 0)


def test_separate_path_from_pdf(tmp_path):
    fitz = pytest.importorskip("fitz")

    card = Image.new("RGB", (40, 56), "purple")
    card_path = tmp_path / "c.png"
    card.save(card_path)
    doc = fitz.open()
    page = doc.new_page(width=100, height=70)
    page.insert_image(fitz.Rect(5, 5, 45, 61), filename=str(card_path))
    page.insert_image(fitz.Rect(50, 5, 90, 61), filename=str(card_path))
    pdf_path = tmp_path / "two.pdf"
    doc.save(pdf_path)
    doc.close()

    written = separate_path(pdf_path, tmp_path / "out")
    assert len(written) == 2


def test_main_missing_input(tmp_path, capsys):
    rc = main(["--input", str(tmp_path / "nope.pdf"), "--out", str(tmp_path / "o")])
    assert rc == 1
    assert "error" in capsys.readouterr().err.lower()


def test_main_sheet_image_ok(tmp_path, capsys):
    sheet = _grid_sheet(2, 2, card_w=20, card_h=28)
    src = tmp_path / "s.png"
    sheet.save(src)
    out = tmp_path / "cards"
    rc = main(["--input", str(src), "--out", str(out), "--cols", "2", "--rows", "2"])
    assert rc == 0
    assert len(list(out.glob("*.png"))) == 4
    assert "4 card" in capsys.readouterr().out


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
