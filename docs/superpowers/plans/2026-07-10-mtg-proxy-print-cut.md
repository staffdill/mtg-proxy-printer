# MTG Proxy Print-and-Cut Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python tool that tiles curated MTG card images (with bleed) into 4-up US-Letter print sheets that align to a build-once Cricut Design Space cut template, plus the Design Space coordinate export and the physical run-book.

**Architecture:** One geometry config is the single source of truth for card size, bleed, gaps, DPI, and card positions. The compositing modules derive print sheets from it; a coordinate-export utility derives the Design Space cut-template rectangles from the same config, so prints and cuts inherently agree. Documentation (run-book + template setup) is generated last using the exported coordinates.

**Tech Stack:** Python 3.11+, Pillow (imaging), pytest (tests). Runs on Windows.

## Global Constraints

- Card trim size: **63 mm × 88 mm**. Corner radius: **3 mm** (applied only in Design Space, not by the script).
- Bleed baked into source images: **3 mm** per side (default; configurable).
- Sheet: **US Letter, 8.5 × 11 in (215.9 × 279.4 mm), 300 DPI** → **2550 × 3300 px**.
- Layout: **2 × 2 = 4 cards per sheet**, centered, default inter-card gap **8 mm** (keeps printed bleed boxes from overlapping: gap ≥ 2 × bleed).
- Card order on a sheet: **row-major, top-left first**; a partial final sheet fills from the top-left.
- Printing (documented, not code): **100% / actual size, "fit to page" OFF, borderless OFF, Best quality, matte paper**.
- Package name: `mtgproxy`. Tests in `tests/`. Run tests with `python -m pytest`.
- The script does **not** round corners and does **not** add registration marks — the Cricut Design Space "Print Then Cut" flow does both.

---

## File Structure

- `requirements.txt` — Pillow, pytest.
- `mtgproxy/__init__.py` — package marker.
- `mtgproxy/geometry.py` — `GeometryConfig`, `CardBox`, `sheet_size_px`, `card_boxes` (single source of truth).
- `mtgproxy/layout.py` — `resize_cover`, `composite_sheet` (image → one sheet).
- `mtgproxy/sources.py` — `list_card_images`, `read_manifest`, `resolve_card_list` (folder/manifest → ordered card path list).
- `mtgproxy/batch.py` — `build_sheets`, `save_sheets` (path list → sheet PNGs on disk).
- `mtgproxy/cli.py` — `main(argv)` argparse entry point wiring it together.
- `mtgproxy/template_coords.py` — `format_template_coords` + `__main__` to print Design Space rectangle coordinates.
- `tests/test_geometry.py`, `tests/test_layout.py`, `tests/test_sources.py`, `tests/test_batch.py`, `tests/test_cli.py`, `tests/test_template_coords.py`.
- `docs/RUNBOOK.md` — physical print-and-cut checklist + troubleshooting.
- `docs/DESIGN_SPACE_TEMPLATE.md` — how to build the 4-up cut template, with exact coordinates.

---

### Task 1: Geometry config (single source of truth)

**Files:**
- Create: `requirements.txt`, `mtgproxy/__init__.py`, `mtgproxy/geometry.py`
- Test: `tests/test_geometry.py`

**Interfaces:**
- Produces:
  - `GeometryConfig` frozen dataclass with fields `card_w_mm=63.0, card_h_mm=88.0, corner_radius_mm=3.0, bleed_mm=3.0, gap_mm=8.0, cols=2, rows=2, sheet_w_mm=215.9, sheet_h_mm=279.4, dpi=300`; methods `px_per_mm() -> float`, property `cards_per_sheet -> int`.
  - `CardBox` frozen dataclass: `print_x_px:int, print_y_px:int, print_w_px:int, print_h_px:int, trim_x_mm:float, trim_y_mm:float`.
  - `sheet_size_px(cfg: GeometryConfig) -> tuple[int, int]`.
  - `card_boxes(cfg: GeometryConfig) -> list[CardBox]` (length `cards_per_sheet`, row-major top-left first).

- [ ] **Step 1: Create project files**

`requirements.txt`:
```
pillow>=10.0
pytest>=8.0
```

`mtgproxy/__init__.py`:
```python
```

- [ ] **Step 2: Write the failing test**

`tests/test_geometry.py`:
```python
import pytest
from mtgproxy.geometry import GeometryConfig, sheet_size_px, card_boxes


def test_cards_per_sheet_is_four():
    assert GeometryConfig().cards_per_sheet == 4


def test_sheet_size_px_is_letter_at_300dpi():
    assert sheet_size_px(GeometryConfig()) == (2550, 3300)


def test_card_boxes_count_and_order():
    boxes = card_boxes(GeometryConfig())
    assert len(boxes) == 4
    # row-major: card 0 top-left, card 1 to its right, card 2 below card 0
    assert boxes[1].trim_x_mm > boxes[0].trim_x_mm
    assert boxes[1].trim_y_mm == pytest.approx(boxes[0].trim_y_mm)
    assert boxes[2].trim_y_mm > boxes[0].trim_y_mm
    assert boxes[2].trim_x_mm == pytest.approx(boxes[0].trim_x_mm)


def test_card0_geometry_values():
    box = card_boxes(GeometryConfig())[0]
    # centered content: left=(215.9-134)/2=40.95mm, top=(279.4-184)/2=47.7mm
    assert box.trim_x_mm == pytest.approx(40.95)
    assert box.trim_y_mm == pytest.approx(47.7)
    # print box = trim shifted out by 3mm bleed, size 69x94mm, at 300dpi
    assert (box.print_x_px, box.print_y_px) == (448, 528)
    assert (box.print_w_px, box.print_h_px) == (815, 1110)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_geometry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mtgproxy.geometry'`

- [ ] **Step 4: Write minimal implementation**

`mtgproxy/geometry.py`:
```python
from dataclasses import dataclass

MM_PER_INCH = 25.4


@dataclass(frozen=True)
class GeometryConfig:
    card_w_mm: float = 63.0
    card_h_mm: float = 88.0
    corner_radius_mm: float = 3.0
    bleed_mm: float = 3.0
    gap_mm: float = 8.0
    cols: int = 2
    rows: int = 2
    sheet_w_mm: float = 215.9  # US Letter 8.5 in
    sheet_h_mm: float = 279.4  # US Letter 11 in
    dpi: int = 300

    @property
    def cards_per_sheet(self) -> int:
        return self.cols * self.rows

    def px_per_mm(self) -> float:
        return self.dpi / MM_PER_INCH


@dataclass(frozen=True)
class CardBox:
    print_x_px: int
    print_y_px: int
    print_w_px: int
    print_h_px: int
    trim_x_mm: float
    trim_y_mm: float


def sheet_size_px(cfg: GeometryConfig) -> tuple[int, int]:
    ppm = cfg.px_per_mm()
    return (round(cfg.sheet_w_mm * ppm), round(cfg.sheet_h_mm * ppm))


def card_boxes(cfg: GeometryConfig) -> list[CardBox]:
    ppm = cfg.px_per_mm()
    content_w = cfg.cols * cfg.card_w_mm + (cfg.cols - 1) * cfg.gap_mm
    content_h = cfg.rows * cfg.card_h_mm + (cfg.rows - 1) * cfg.gap_mm
    left = (cfg.sheet_w_mm - content_w) / 2
    top = (cfg.sheet_h_mm - content_h) / 2

    boxes: list[CardBox] = []
    for r in range(cfg.rows):
        for c in range(cfg.cols):
            trim_x = left + c * (cfg.card_w_mm + cfg.gap_mm)
            trim_y = top + r * (cfg.card_h_mm + cfg.gap_mm)
            print_x_mm = trim_x - cfg.bleed_mm
            print_y_mm = trim_y - cfg.bleed_mm
            print_w_mm = cfg.card_w_mm + 2 * cfg.bleed_mm
            print_h_mm = cfg.card_h_mm + 2 * cfg.bleed_mm
            boxes.append(
                CardBox(
                    print_x_px=round(print_x_mm * ppm),
                    print_y_px=round(print_y_mm * ppm),
                    print_w_px=round(print_w_mm * ppm),
                    print_h_px=round(print_h_mm * ppm),
                    trim_x_mm=trim_x,
                    trim_y_mm=trim_y,
                )
            )
    return boxes
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_geometry.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt mtgproxy/__init__.py mtgproxy/geometry.py tests/test_geometry.py
git commit -m "feat: geometry config as single source of truth for card layout"
```

---

### Task 2: Sheet compositing

**Files:**
- Create: `mtgproxy/layout.py`
- Test: `tests/test_layout.py`

**Interfaces:**
- Consumes: `GeometryConfig`, `sheet_size_px`, `card_boxes` from `mtgproxy.geometry`.
- Produces:
  - `resize_cover(img: PIL.Image.Image, w_px: int, h_px: int) -> PIL.Image.Image` (scale to fully cover, center-crop, no distortion).
  - `composite_sheet(images: list[PIL.Image.Image], cfg: GeometryConfig) -> PIL.Image.Image` (white Letter canvas with up to `cards_per_sheet` images placed at their print boxes).

- [ ] **Step 1: Write the failing test**

`tests/test_layout.py`:
```python
from PIL import Image
from mtgproxy.geometry import GeometryConfig, sheet_size_px, card_boxes
from mtgproxy.layout import resize_cover, composite_sheet


def test_resize_cover_exact_size_no_distortion():
    src = Image.new("RGB", (100, 100), "red")  # square source
    out = resize_cover(src, 60, 90)
    assert out.size == (60, 90)


def test_composite_places_cards_and_leaves_white_margin():
    cfg = GeometryConfig()
    imgs = [Image.new("RGB", (100, 140), "red") for _ in range(4)]
    sheet = composite_sheet(imgs, cfg)
    assert sheet.size == sheet_size_px(cfg)

    box0 = card_boxes(cfg)[0]
    # a point inside card 0's print box is red
    inside = (box0.print_x_px + 10, box0.print_y_px + 10)
    assert sheet.getpixel(inside) == (255, 0, 0)
    # top-left corner of the sheet is white margin
    assert sheet.getpixel((5, 5)) == (255, 255, 255)


def test_composite_partial_sheet_ok():
    cfg = GeometryConfig()
    sheet = composite_sheet([Image.new("RGB", (100, 140), "red")], cfg)
    assert sheet.size == sheet_size_px(cfg)
    # only card 0 filled; card 3 region stays white
    box3 = card_boxes(cfg)[3]
    assert sheet.getpixel((box3.print_x_px + 10, box3.print_y_px + 10)) == (255, 255, 255)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_layout.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mtgproxy.layout'`

- [ ] **Step 3: Write minimal implementation**

`mtgproxy/layout.py`:
```python
from PIL import Image

from mtgproxy.geometry import GeometryConfig, card_boxes, sheet_size_px


def resize_cover(img: Image.Image, w_px: int, h_px: int) -> Image.Image:
    src_w, src_h = img.size
    scale = max(w_px / src_w, h_px / src_h)
    scaled = img.resize(
        (max(w_px, round(src_w * scale)), max(h_px, round(src_h * scale))),
        Image.LANCZOS,
    )
    left = (scaled.width - w_px) // 2
    top = (scaled.height - h_px) // 2
    return scaled.crop((left, top, left + w_px, top + h_px))


def composite_sheet(images: list[Image.Image], cfg: GeometryConfig) -> Image.Image:
    canvas = Image.new("RGB", sheet_size_px(cfg), "white")
    for img, box in zip(images, card_boxes(cfg)):
        placed = resize_cover(img.convert("RGB"), box.print_w_px, box.print_h_px)
        canvas.paste(placed, (box.print_x_px, box.print_y_px))
    return canvas
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_layout.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/layout.py tests/test_layout.py
git commit -m "feat: composite curated card images into a 4-up sheet"
```

---

### Task 3: Image sources and card ordering

**Files:**
- Create: `mtgproxy/sources.py`
- Test: `tests/test_sources.py`

**Interfaces:**
- Produces:
  - `list_card_images(folder: pathlib.Path) -> list[pathlib.Path]` — image files (`.png/.jpg/.jpeg`, case-insensitive) sorted by name.
  - `read_manifest(path: pathlib.Path) -> list[tuple[str, int]]` — parse lines `filename,quantity`; ignore blank lines and `#` comments; quantity defaults to 1 if omitted.
  - `resolve_card_list(folder: pathlib.Path, manifest: pathlib.Path | None = None) -> list[pathlib.Path]` — with a manifest, expand each entry into `quantity` repeated paths (`folder/filename`); without one, return `list_card_images(folder)` (each image once).

- [ ] **Step 1: Write the failing test**

`tests/test_sources.py`:
```python
import pytest
from mtgproxy.sources import list_card_images, read_manifest, resolve_card_list


def _touch(folder, name):
    p = folder / name
    p.write_bytes(b"x")
    return p


def test_list_card_images_filters_and_sorts(tmp_path):
    _touch(tmp_path, "b.png")
    _touch(tmp_path, "a.JPG")
    _touch(tmp_path, "notes.txt")
    names = [p.name for p in list_card_images(tmp_path)]
    assert names == ["a.JPG", "b.png"]


def test_read_manifest_parses_quantities_and_comments(tmp_path):
    m = tmp_path / "order.txt"
    m.write_text("# my deck\nsol_ring.png,4\n\nforest.png\n", encoding="utf-8")
    assert read_manifest(m) == [("sol_ring.png", 4), ("forest.png", 1)]


def test_resolve_card_list_expands_manifest_quantities(tmp_path):
    _touch(tmp_path, "sol_ring.png")
    _touch(tmp_path, "forest.png")
    m = tmp_path / "order.txt"
    m.write_text("sol_ring.png,2\nforest.png,1\n", encoding="utf-8")
    paths = resolve_card_list(tmp_path, m)
    assert [p.name for p in paths] == ["sol_ring.png", "sol_ring.png", "forest.png"]


def test_resolve_card_list_without_manifest_lists_folder(tmp_path):
    _touch(tmp_path, "a.png")
    _touch(tmp_path, "b.png")
    paths = resolve_card_list(tmp_path)
    assert [p.name for p in paths] == ["a.png", "b.png"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sources.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mtgproxy.sources'`

- [ ] **Step 3: Write minimal implementation**

`mtgproxy/sources.py`:
```python
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


def list_card_images(folder: Path) -> list[Path]:
    files = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    return sorted(files, key=lambda p: p.name)


def read_manifest(path: Path) -> list[tuple[str, int]]:
    entries: list[tuple[str, int]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "," in line:
            name, qty = line.rsplit(",", 1)
            entries.append((name.strip(), int(qty.strip())))
        else:
            entries.append((line, 1))
    return entries


def resolve_card_list(folder: Path, manifest: Path | None = None) -> list[Path]:
    if manifest is None:
        return list_card_images(folder)
    paths: list[Path] = []
    for name, qty in read_manifest(manifest):
        paths.extend([folder / name] * qty)
    return paths
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sources.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/sources.py tests/test_sources.py
git commit -m "feat: resolve card image list from folder or quantity manifest"
```

---

### Task 4: Batch into sheets and save

**Files:**
- Create: `mtgproxy/batch.py`
- Test: `tests/test_batch.py`

**Interfaces:**
- Consumes: `GeometryConfig` (`cards_per_sheet`), `composite_sheet`.
- Produces:
  - `build_sheets(card_paths: list[pathlib.Path], cfg: GeometryConfig) -> list[PIL.Image.Image]` — chunk paths into `cards_per_sheet`, open each image, composite each chunk.
  - `save_sheets(sheets: list[PIL.Image.Image], out_dir: pathlib.Path, prefix: str = "sheet") -> list[pathlib.Path]` — write `sheet_01.png …`, zero-padded to the sheet count width; creates `out_dir`.

- [ ] **Step 1: Write the failing test**

`tests/test_batch.py`:
```python
from PIL import Image
from mtgproxy.geometry import GeometryConfig, sheet_size_px
from mtgproxy.batch import build_sheets, save_sheets


def _make_images(tmp_path, n):
    paths = []
    for i in range(n):
        p = tmp_path / f"card_{i}.png"
        Image.new("RGB", (100, 140), "red").save(p)
        paths.append(p)
    return paths


def test_build_sheets_chunks_by_four(tmp_path):
    cfg = GeometryConfig()
    paths = _make_images(tmp_path, 5)  # 5 cards -> 2 sheets
    sheets = build_sheets(paths, cfg)
    assert len(sheets) == 2
    assert all(s.size == sheet_size_px(cfg) for s in sheets)


def test_save_sheets_zero_pads_names(tmp_path):
    cfg = GeometryConfig()
    paths = _make_images(tmp_path, 5)
    sheets = build_sheets(paths, cfg)
    out = tmp_path / "out"
    written = save_sheets(sheets, out)
    assert [p.name for p in written] == ["sheet_1.png", "sheet_2.png"]
    assert all(p.exists() for p in written)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_batch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mtgproxy.batch'`

- [ ] **Step 3: Write minimal implementation**

`mtgproxy/batch.py`:
```python
from pathlib import Path

from PIL import Image

from mtgproxy.geometry import GeometryConfig
from mtgproxy.layout import composite_sheet


def build_sheets(card_paths: list[Path], cfg: GeometryConfig) -> list[Image.Image]:
    n = cfg.cards_per_sheet
    sheets: list[Image.Image] = []
    for start in range(0, len(card_paths), n):
        chunk = card_paths[start : start + n]
        images = [Image.open(p) for p in chunk]
        sheets.append(composite_sheet(images, cfg))
    return sheets


def save_sheets(
    sheets: list[Image.Image], out_dir: Path, prefix: str = "sheet"
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    width = len(str(len(sheets)))
    written: list[Path] = []
    for i, sheet in enumerate(sheets, start=1):
        path = out_dir / f"{prefix}_{str(i).zfill(width)}.png"
        sheet.save(path, "PNG", dpi=(sheets[0].info.get("dpi", (300, 300)))[0:2] or (300, 300))
        written.append(path)
    return written
```

Note: the `dpi` save argument embeds 300 DPI metadata so Design Space imports at true physical size. If `sheets[0].info` lacks dpi, it falls back to `(300, 300)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_batch.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/batch.py tests/test_batch.py
git commit -m "feat: batch card list into 4-up sheet PNGs with 300 DPI metadata"
```

---

### Task 5: CLI entry point

**Files:**
- Create: `mtgproxy/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `GeometryConfig`, `resolve_card_list`, `build_sheets`, `save_sheets`.
- Produces:
  - `main(argv: list[str] | None = None) -> int` — argparse CLI: `--input` (required, image folder), `--out` (default `./out`), `--manifest` (optional), `--bleed` (float, default 3.0), `--gap` (float, default 8.0). Builds and saves sheets; prints a summary line `Wrote N sheet(s) from M card(s) to <out>`; returns 0.

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mtgproxy.cli'`

- [ ] **Step 3: Write minimal implementation**

`mtgproxy/cli.py`:
```python
import argparse
from pathlib import Path

from mtgproxy.batch import build_sheets, save_sheets
from mtgproxy.geometry import GeometryConfig
from mtgproxy.sources import resolve_card_list


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Tile MTG card images into 4-up US-Letter print sheets."
    )
    parser.add_argument("--input", required=True, help="Folder of card images (with bleed).")
    parser.add_argument("--out", default="./out", help="Output folder for sheet PNGs.")
    parser.add_argument("--manifest", default=None, help="Optional filename,quantity manifest.")
    parser.add_argument("--bleed", type=float, default=3.0, help="Bleed mm per side.")
    parser.add_argument("--gap", type=float, default=8.0, help="Gap mm between cards.")
    args = parser.parse_args(argv)

    cfg = GeometryConfig(bleed_mm=args.bleed, gap_mm=args.gap)
    manifest = Path(args.manifest) if args.manifest else None
    card_paths = resolve_card_list(Path(args.input), manifest)
    sheets = build_sheets(card_paths, cfg)
    written = save_sheets(sheets, Path(args.out))

    print(f"Wrote {len(written)} sheet(s) from {len(card_paths)} card(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -v`
Expected: PASS (all tasks' tests green)

- [ ] **Step 6: Commit**

```bash
git add mtgproxy/cli.py tests/test_cli.py
git commit -m "feat: CLI to generate print sheets from a card folder"
```

---

### Task 6: Design Space coordinate export

**Files:**
- Create: `mtgproxy/template_coords.py`
- Test: `tests/test_template_coords.py`

**Interfaces:**
- Consumes: `GeometryConfig`, `card_boxes`.
- Produces:
  - `format_template_coords(cfg: GeometryConfig) -> str` — human-readable block giving sheet size, corner radius, and each card's trim rectangle in **mm and inches** (x, y from top-left, plus fixed 63×88 mm / 2.480×3.465 in size), for building the Design Space cut template.
  - `__main__` prints the block.

- [ ] **Step 1: Write the failing test**

`tests/test_template_coords.py`:
```python
from mtgproxy.geometry import GeometryConfig
from mtgproxy.template_coords import format_template_coords


def test_format_includes_size_radius_and_all_cards():
    text = format_template_coords(GeometryConfig())
    assert "63 x 88 mm" in text
    assert "radius 3 mm" in text
    assert "2.480 x 3.465 in" in text  # 63mm/88mm in inches
    # one line per card, numbered 1..4
    for n in range(1, 5):
        assert f"Card {n}:" in text
    # card 1 trim origin in mm
    assert "40.95" in text
    assert "47.70" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_template_coords.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mtgproxy.template_coords'`

- [ ] **Step 3: Write minimal implementation**

`mtgproxy/template_coords.py`:
```python
from mtgproxy.geometry import GeometryConfig, MM_PER_INCH, card_boxes


def format_template_coords(cfg: GeometryConfig) -> str:
    w_in = cfg.card_w_mm / MM_PER_INCH
    h_in = cfg.card_h_mm / MM_PER_INCH
    lines = [
        "Cricut Design Space — 4-up cut template",
        f"Sheet: {cfg.sheet_w_mm:.1f} x {cfg.sheet_h_mm:.1f} mm (US Letter), {cfg.dpi} DPI",
        f"Each cut: rounded rectangle {cfg.card_w_mm:.0f} x {cfg.card_h_mm:.0f} mm "
        f"({w_in:.3f} x {h_in:.3f} in), radius {cfg.corner_radius_mm:.0f} mm",
        "Positions are the top-left corner of each card's trim box, measured from the",
        "top-left of the sheet. Place the imported sheet image at the sheet origin.",
        "",
    ]
    for i, box in enumerate(card_boxes(cfg), start=1):
        x_in = box.trim_x_mm / MM_PER_INCH
        y_in = box.trim_y_mm / MM_PER_INCH
        lines.append(
            f"Card {i}: x={box.trim_x_mm:.2f} mm ({x_in:.3f} in), "
            f"y={box.trim_y_mm:.2f} mm ({y_in:.3f} in)"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_template_coords(GeometryConfig()))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_template_coords.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/template_coords.py tests/test_template_coords.py
git commit -m "feat: export Design Space cut-template coordinates from geometry"
```

---

### Task 7: Run-book and Design Space setup docs

**Files:**
- Create: `docs/RUNBOOK.md`, `docs/DESIGN_SPACE_TEMPLATE.md`

No automated tests (documentation). Generate the coordinate block by running
`python -m mtgproxy.template_coords` and paste its output into `DESIGN_SPACE_TEMPLATE.md`.

- [ ] **Step 1: Generate the coordinate block**

Run: `python -m mtgproxy.template_coords`
Expected: prints the sheet/cut/position block. Copy it for the next step.

- [ ] **Step 2: Write `docs/DESIGN_SPACE_TEMPLATE.md`**

```markdown
# Cricut Design Space — Build the 4-up Cut Template (once)

1. New Project. Set the machine to **Cricut Explore Air 2** and material size **US Letter**.
2. Insert **4 rounded rectangles** (Shapes → Square, then use the corner-radius slider).
   Set each to **63 × 88 mm (2.480 × 3.465 in)**, corner radius **3 mm**.
3. Position each rectangle using the coordinates below (top-left corner of each card,
   measured from the top-left of the sheet). Design Space uses inches — use the inch values.
4. Select all four, **Group**, and **Save** the project as "MTG 4-up template".

<!-- Paste the exact output of `python -m mtgproxy.template_coords` here -->

## Per-sheet cycle
1. Open the saved template.
2. **Upload** the next `sheet_NN.png` as a **Print Then Cut** image; set its size to the
   full sheet (8.5 × 11 in) and align it to the sheet origin (top-left).
3. Send the image **behind** the four cut rectangles (Arrange → Move to Back).
4. **Make It → Print Then Cut.** In the system print dialog: **100% / actual size**,
   **"fit to page" OFF**, **borderless OFF**, **Best quality**, **matte paper**.
5. Load the printed sheet on the mat and cut.
```

- [ ] **Step 3: Write `docs/RUNBOOK.md`**

```markdown
# MTG Proxy Print-and-Cut Run-book

## One-time setup
- Install deps: `pip install -r requirements.txt`
- Cricut: run **Print Then Cut calibration** in Design Space.
- Build the cut template (see DESIGN_SPACE_TEMPLATE.md).
- Load LightGrip (blue) mat; install a clean Fine-Point blade.

## Each batch
1. In the desktop **MPC Autofill** app, choose the art per card; let it download images.
2. Point the script at the downloaded image folder:
   `python -m mtgproxy.cli --input "<mpc-autofill-image-folder>" --out ./out`
   - Optional exact quantities/order: add `--manifest order.txt`
     (lines `filename.png,quantity`).
3. For each `out/sheet_NN.png`: in Design Space open the template, upload the sheet as
   Print Then Cut, send behind the cut grid, Make It → Print Then Cut.
4. Print at **100% / actual size**, matte paper, Best quality; let ink dry flat 2-3 min.
5. Cut. Remove by peeling the **mat away from the card** (flip mat face-down, roll back).
6. Sleeve each proxy with a real card/land behind it (opaque-back sleeves).

## First-run verification (do once, then trust it)
- Print one test sheet; check with calipers:
  - Card size 63 × 88 mm (±0.3 mm)
  - Corner radius ~3 mm
  - Cut sits just inside the art on all sides (no white sliver)
  - No tearing on removal
- If off, adjust template offset / confirm 100% scaling, then re-test.

## Troubleshooting
| Symptom | Fix |
|---|---|
| Cricut can't read registration marks | good black ink; matte paper; even lighting, no glare/shadow; marks not cut off; mat loaded straight |
| White sliver on cut edge | rely on the 3 mm bleed; re-run Print Then Cut calibration; verify 100% scaling |
| Paper curls -> sensor fails | dry flat, gently back-roll, load flat |
| Card tears on removal | LightGrip mat + mat-off-card technique |
| Cut doesn't go all the way through | custom/"more" pressure, fresh blade, multi-cut x2 |
| Colors dull vs screen | inherent to matte inkjet; acceptable sleeved; nudge saturation if wanted |
```

- [ ] **Step 4: Commit**

```bash
git add docs/RUNBOOK.md docs/DESIGN_SPACE_TEMPLATE.md
git commit -m "docs: run-book and Design Space template setup guide"
```

---

## Self-Review

**Spec coverage:**
- Compositing script (Python + Pillow, Windows) → Tasks 1-5. ✓
- Geometry single source of truth (63×88 mm, 3 mm radius, 3 mm bleed, Letter/300 DPI, 4-up, row-major top-left) → Task 1, enforced in Global Constraints. ✓
- Curated image folder input + optional quantities → Task 3 (`resolve_card_list`, manifest). ✓
- Bleed handling (place bleed image, cut at trim) → Task 1 print box vs trim box; Task 2 placement. ✓
- 300 DPI output for true physical size in Design Space → Task 4 save with dpi metadata. ✓
- Design Space 4-up template with exact coordinates → Task 6 export + Task 7 DESIGN_SPACE_TEMPLATE.md. ✓
- Physical run-book (printer/paper/mat/blade, removal, sleeving), calibration/testing, troubleshooting → Task 7 RUNBOOK.md. ✓
- MPC Autofill as the art picker whose folder we intercept → Task 7 run-book step 1-2. ✓

**Open items from the spec** (folder path of MPC Autofill cache, HP model print settings, exact Print Then Cut safe-area) are documented as run-book inputs / verified during the first-run test; they do not block building the script, whose geometry is parameterized (`--bleed`, `--gap`) if adjustment is needed.

**Placeholder scan:** No TBD/TODO in code steps; every code step shows complete code. The one `<!-- Paste … -->` marker in Task 7 is an explicit generate-then-embed step (Step 1 produces the content), not an unresolved placeholder.

**Type consistency:** `GeometryConfig`, `CardBox`, `sheet_size_px`, `card_boxes` names/fields are consistent across Tasks 1, 2, 4, 6. `resolve_card_list`, `build_sheets`, `save_sheets`, `composite_sheet`, `resize_cover` signatures match their call sites in Tasks 4-5. ✓
