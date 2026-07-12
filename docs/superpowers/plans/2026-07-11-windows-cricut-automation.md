# Windows Cricut Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the sticker-mode bleed bug, then port the Cricut Design Space automation from macOS to Windows 11 and extend it to drive a full Print Then Cut run that halts at the print dialog for a human to click Print.

**Architecture:** Two components. `mtgproxy` (pure, testable) generates transparent 4-up sheets whose alpha boundary Design Space traces into cut lines. `mtgproxy.cricut` (UI automation) drives Design Space per sheet, split on a hard boundary: **Design Space's own Chromium UI is located by pixel template matching** (it exposes no UI Automation tree — this was verified, not assumed), while **native Windows dialogs are driven through UI Automation** (they expose real control handles). Never cross that line.

**Tech Stack:** Python 3.13, Pillow, OpenCV (template matching), pyautogui (screenshots + clicks), pywinauto (UI Automation), pytest.

## Global Constraints

- **Target machine:** Windows 11, single 5120×1440 display at 96 DPI (100% scaling). The DPI scale factor computes to 1.0 here but must be **computed, never hardcoded**.
- **Design Space:** 9.76.91, Electron/Chromium. It auto-updates; templates are a maintenance surface.
- **Design Space exposes no UIA tree.** Probing returns 3 descendants, two opaque `Chrome Legacy Window` panes. Do not attempt UIA on in-app buttons.
- **The script never clicks Print, and never presses the Cricut's Go button.** Both consume physical materials. This is not a default to be overridden.
- **A template miss halts the entire run.** Never advance a step or a sheet on a bad match. A half-recognized UI is exactly when blind clicking is most dangerous.
- **Card geometry:** trim 63 × 88 mm, corner radius 3 mm, 300 DPI (11.811 px/mm). Tolerance ±0.3 mm.
- **Sheet size:** 4 cards, 2×2, 8 mm gap → 134 × 184 mm = **5.276 × 7.244 in**. Design Space ignores PNG DPI, so width is set numerically.
- **Card images:** `C:\Users\Staff\Downloads\card_images_2026-07-11` (84 images, ~3 mm bleed) → 21 sheets.

---

### Task 1: Normalize line endings

The working tree was copied in without `.git`, converting every file LF→CRLF. All 20 tracked files show as modified while being byte-identical in content. Fix this first so every later diff is honest.

**Files:**
- Create: `.gitattributes`

- [ ] **Step 1: Create `.gitattributes`**

```
# Normalize text files to LF in the repository, native in the working tree.
* text=auto

# Binary assets must never be line-ending converted.
*.png binary
*.jpg binary
*.jpeg binary
```

- [ ] **Step 2: Renormalize the index**

```bash
git add --renormalize .
git status --short
```
Expected: the previously "modified" files now appear staged with no content change.

- [ ] **Step 3: Verify no real content changed**

```bash
git diff --cached --ignore-all-space --stat
```
Expected: empty output (all differences are line-ending only).

- [ ] **Step 4: Commit**

```bash
git add .gitattributes
git commit -m "chore: normalize line endings with .gitattributes"
```

---

### Task 2: Fix the sticker-mode bleed scaling bug

`layout.rounded_card()` calls `resize_cover(img, trim_w, trim_h)`, squeezing the whole 69 × 94 mm bleed image into the 63 × 88 mm trim box. Measured on a real source: art renders at 11.053 px/mm against a sheet of 11.811 px/mm — **the card face is 6.4% too small**, with the bleed ring left showing as a fake border.

The fix: render at the *bleed box* (the scale the art was authored at), crop the bleed ring away, then round the corners.

**Files:**
- Modify: `mtgproxy/layout.py:36-47` (`rounded_card`)
- Test: `tests/test_layout.py`

**Interfaces:**
- Consumes: `GeometryConfig` (`card_w_mm`, `card_h_mm`, `bleed_mm`, `corner_radius_mm`, `px_per_mm()`), `resize_cover` — all unchanged.
- Produces: `rounded_card(img, cfg) -> Image` — same signature, corrected behavior. `composite_sticker_sheet` calls it and needs no change.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_layout.py`:

```python
def test_rounded_card_crops_bleed_instead_of_shrinking_the_face():
    # A source authored the way MPC authors them: a bleed ring around the card
    # face. Card face RED, bleed ring BLUE, rendered at exactly 10 px/mm.
    # bleed_mm=6 (not the 3mm default) so the ring is thick enough that a
    # sampled point cannot land ambiguously on the boundary.
    cfg = GeometryConfig(bleed_mm=6.0, gap_mm=12.0)
    src = Image.new("RGB", (750, 1000), "blue")  # 75 x 100 mm at 10 px/mm
    src.paste(Image.new("RGB", (630, 880), "red"), (60, 60))  # the 63x88mm face

    out = rounded_card(src, cfg)

    ppm = cfg.px_per_mm()
    assert out.size == (round(cfg.card_w_mm * ppm), round(cfg.card_h_mm * ppm))

    # 2mm inside each edge midpoint must be the card FACE (red), not bleed (blue).
    # The bug renders the bleed ring inside the trim box, so these come out blue.
    inset = round(2 * ppm)
    w, h = out.size
    for point in [
        (inset, h // 2),          # left edge
        (w - inset - 1, h // 2),  # right edge
        (w // 2, inset),          # top edge
        (w // 2, h - inset - 1),  # bottom edge
    ]:
        r, g, b, a = out.getpixel(point)
        assert a == 255, f"{point} should be opaque"
        assert r > 200 and b < 55, f"{point} is bleed, not card face: {(r, g, b)}"


def test_rounded_card_with_zero_bleed_is_a_plain_trim_resize():
    # The "no bleed" folder: source art IS the card face, nothing to crop.
    cfg = GeometryConfig(bleed_mm=0.0, gap_mm=8.0)
    src = Image.new("RGB", (630, 880), "red")
    out = rounded_card(src, cfg)

    ppm = cfg.px_per_mm()
    assert out.size == (round(cfg.card_w_mm * ppm), round(cfg.card_h_mm * ppm))
    px = out.getpixel((out.width // 2, out.height // 2))
    assert px[3] == 255 and px[:3] == (255, 0, 0)
```

Add `rounded_card` to the imports at the top of `tests/test_layout.py`:

```python
from mtgproxy.layout import (
    resize_cover,
    composite_sheet,
    composite_sticker_sheet,
    rounded_card,
)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_layout.py::test_rounded_card_crops_bleed_instead_of_shrinking_the_face -v`
Expected: FAIL — `AssertionError: (23, 519) is bleed, not card face: (0, 0, 255)`

- [ ] **Step 3: Implement the fix**

Replace `rounded_card` in `mtgproxy/layout.py` entirely:

```python
def rounded_card(img: Image.Image, cfg: GeometryConfig) -> Image.Image:
    """A single card sized to trim (63x88mm) with rounded corners cut out as
    transparency — an RGBA 'sticker' Design Space can auto-cut around.

    Source art carries bleed (MPC images extend ~3mm past the trim edge), so it
    is rendered at the bleed box — the scale it was authored at — and the bleed
    ring is then cropped away. Scaling the bleed image straight into the trim
    box instead shrinks the card face by ~6% and leaves the bleed ring showing
    as a fake border.
    """
    ppm = cfg.px_per_mm()
    w = round(cfg.card_w_mm * ppm)
    h = round(cfg.card_h_mm * ppm)
    bleed_w = round((cfg.card_w_mm + 2 * cfg.bleed_mm) * ppm)
    bleed_h = round((cfg.card_h_mm + 2 * cfg.bleed_mm) * ppm)
    radius = round(cfg.corner_radius_mm * ppm)

    full = resize_cover(img.convert("RGB"), bleed_w, bleed_h)
    left = (bleed_w - w) // 2
    top = (bleed_h - h) // 2
    card = full.crop((left, top, left + w, top + h)).convert("RGBA")

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    card.putalpha(mask)
    return card
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest tests/ -v`
Expected: all PASS, including the pre-existing `test_sticker_sheet_transparent_with_rounded_cards`.

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/layout.py tests/test_layout.py
git commit -m "fix: sticker mode shrank card faces 6.4% by squeezing bleed into the trim box"
```

---

### Task 3: Add the sticker gap floor and drop the dead cut-template code

Design Space smears ~1/16 in (1.5875 mm) of bleed outward past every cut line. Adjacent cards therefore need ≥ ~3.2 mm of separation or their bleeds collide. `GeometryConfig.__post_init__` enforces `gap ≥ 2·bleed`, which is *not* binding when `--bleed 0` — exactly the case where the floor matters.

`template_coords.py` exists only to emit coordinates for the manual cut template we are no longer building. Delete it rather than leave a trap.

**Files:**
- Modify: `mtgproxy/geometry.py` (add constant + validator)
- Modify: `mtgproxy/cli.py` (call the validator in sticker mode)
- Delete: `mtgproxy/template_coords.py`, `tests/test_template_coords.py`
- Delete: `docs/DESIGN_SPACE_TEMPLATE.md`
- Test: `tests/test_geometry.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `geometry.DESIGN_SPACE_BLEED_MM: float`, `geometry.validate_sticker_gap(cfg) -> None` (raises `ValueError`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_geometry.py`:

```python
from mtgproxy.geometry import DESIGN_SPACE_BLEED_MM, validate_sticker_gap
import pytest


def test_validate_sticker_gap_rejects_gap_below_design_space_bleed():
    # bleed=0 slips past __post_init__'s gap >= 2*bleed check, but Design Space
    # still smears ~1.6mm outward from each cut line, so touching cards bleed
    # into each other.
    cfg = GeometryConfig(bleed_mm=0.0, gap_mm=2.0)
    with pytest.raises(ValueError, match="gap"):
        validate_sticker_gap(cfg)


def test_validate_sticker_gap_accepts_the_default_gap():
    validate_sticker_gap(GeometryConfig())  # 8mm gap, comfortably clear


def test_design_space_bleed_is_one_sixteenth_inch():
    assert abs(DESIGN_SPACE_BLEED_MM - 25.4 / 16) < 1e-9
```

Append to `tests/test_cli.py`:

```python
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
        ]
    )
    assert rc == 1
    assert "error" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_geometry.py tests/test_cli.py -v`
Expected: FAIL with `ImportError: cannot import name 'DESIGN_SPACE_BLEED_MM'`

- [ ] **Step 3: Add the constant and validator to `mtgproxy/geometry.py`**

Below `MM_PER_INCH = 25.4`:

```python
# Design Space smears roughly 1/16in of bleed outward past every cut line when
# its bleed option is on. Adjacent cards need at least twice that between them
# or their bleeds collide.
DESIGN_SPACE_BLEED_MM = MM_PER_INCH / 16
```

At the end of the file:

```python
def validate_sticker_gap(cfg: GeometryConfig) -> None:
    """Sticker sheets cut on the printed edge, so Design Space adds its own
    bleed outward from each cut line. Raise if the gap is too small to absorb
    it. GeometryConfig's own gap >= 2*bleed check does not cover this: with
    --bleed 0 it permits any gap at all."""
    floor = 2 * DESIGN_SPACE_BLEED_MM
    if cfg.gap_mm < floor:
        raise ValueError(
            f"gap_mm ({cfg.gap_mm}) must be >= {floor:.3f} in sticker mode so "
            f"Design Space's own bleed does not run between adjacent cards"
        )
```

- [ ] **Step 4: Call it from `mtgproxy/cli.py`**

Update the import block:

```python
from mtgproxy.geometry import (
    MM_PER_INCH,
    GeometryConfig,
    content_size_mm,
    trim_content_size_mm,
    validate_sticker_gap,
)
```

In the `try` block, after `cfg = GeometryConfig(...)`:

```python
    try:
        cfg = GeometryConfig(bleed_mm=args.bleed, gap_mm=args.gap)
        if args.sticker:
            validate_sticker_gap(cfg)
        card_paths = resolve_card_list(input_dir, manifest)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
```

- [ ] **Step 5: Delete the dead cut-template code**

```bash
git rm mtgproxy/template_coords.py tests/test_template_coords.py docs/DESIGN_SPACE_TEMPLATE.md
```

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest tests/ -v`
Expected: all PASS. No test references `template_coords`.

- [ ] **Step 7: Commit**

```bash
git add mtgproxy/geometry.py mtgproxy/cli.py tests/test_geometry.py tests/test_cli.py
git commit -m "feat: enforce sticker gap floor; drop the manual cut-template code"
```

---

### Task 4: Generate the real sheets and inspect them

Validate Task 2 against real art before any UI work. This is free and catches geometry errors before a single sheet of paper is used.

**Files:**
- Modify: `.gitignore` (ignore generated output)

- [ ] **Step 1: Ignore generated artifacts**

Append to `.gitignore`:

```
sheets/
debug/
```

- [ ] **Step 2: Generate the sheets**

```bash
python -m mtgproxy.cli --input "C:/Users/Staff/Downloads/card_images_2026-07-11" --out ./sheets --sticker
```
Expected: `Wrote 21 sheet(s) from 84 card(s) to ./sheets`, plus a line reporting the import size as `5.276 x 7.244 in`.

- [ ] **Step 3: Verify sheet dimensions**

```bash
python -c "from PIL import Image; im = Image.open('sheets/sheet_01.png'); print(im.size, im.mode); print('mm:', im.width/ (300/25.4), im.height/(300/25.4))"
```
Expected: `(1583, 2173) RGBA` and `mm: 134.0... 184.0...`

- [ ] **Step 4: Inspect `sheets/sheet_01.png` by eye**

Open it. Confirm: four card faces, no blue/grey bleed ring showing as a fake border, corners rounded, background transparent (checkerboard in a viewer), card art fills each card edge to edge.

**This is a human gate.** If the cards look inset inside a border, Task 2's fix did not take — stop and fix it. Do not proceed to UI work with bad sheets.

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore generated sheets/ and debug/ output"
```

---

### Task 5: Reconnaissance — record what the Windows UI actually is

Everything downstream (`native.py`, `flow.py`) must be written against observed reality, not guesses. Design Space's dialog titles, control identifiers, and button appearances are unknown until we look. **Do this before writing the automation, not after it breaks.**

**Files:**
- Create: `mtgproxy/cricut/__init__.py`
- Create: `mtgproxy/cricut/probe.py`
- Create: `mtgproxy/cricut/templates/` (directory for the captured button images)
- Create: `docs/superpowers/notes/cricut-ui-recon.md`
- Modify: `requirements.txt`
- Delete: `image-upload-workflow/` (macOS templates and script — all unusable)

**Interfaces:**
- Produces: `probe.snap(name) -> Path` (saves a full screenshot), `probe.dump_dialogs() -> str` (dumps UIA identifiers of every top-level dialog).

- [ ] **Step 1: Add the dependencies**

Replace `requirements.txt`:

```
pillow>=10.0
pytest>=8.0
numpy>=1.26
opencv-python-headless>=4.9
pyautogui>=0.9.54
pywinauto>=0.6.8
```

Run: `python -m pip install -r requirements.txt`

- [ ] **Step 2: Create the package and the probe tool**

`mtgproxy/cricut/__init__.py`:

```python
"""Driving Cricut Design Space on Windows.

Design Space is Electron/Chromium and exposes no UI Automation tree — probing
its window returns only opaque "Chrome Legacy Window" panes — so its own
buttons can only be found by matching pixels (screen.py). The native Windows
dialogs it opens DO expose real control handles, and are driven through UI
Automation (native.py). That split is the whole design; do not cross it.
"""
```

`mtgproxy/cricut/probe.py`:

```python
"""Reconnaissance helpers. Not used at run time — this is how we learn what the
Windows Design Space UI actually looks like, so flow.py and native.py can be
written against fact rather than guesswork.

Usage:
    python -m mtgproxy.cricut.probe snap <name>   # full screenshot after 5s
    python -m mtgproxy.cricut.probe dialogs       # UIA identifiers of open dialogs
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pyautogui

SNAP_DIR = Path(__file__).resolve().parents[2] / "debug" / "recon"


def snap(name: str, delay: float = 5.0) -> Path:
    """Save a full-screen screenshot. The delay is to let you bring Design Space
    to the state you want captured."""
    print(f"Capturing '{name}' in {delay:.0f}s — switch to Design Space now...")
    time.sleep(delay)
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAP_DIR / f"{name}.png"
    pyautogui.screenshot().save(path)
    print(f"Saved {path}  ({pyautogui.screenshot().size[0]}x{pyautogui.screenshot().size[1]})")
    return path


def dump_dialogs(delay: float = 5.0) -> str:
    """Print the UIA control identifiers of every visible top-level dialog.
    Run this with the file-open dialog (and later the print dialog) on screen to
    learn the exact titles, class names, and control names native.py must use."""
    from pywinauto import Desktop

    print(f"Dumping dialogs in {delay:.0f}s — bring the dialog up now...")
    time.sleep(delay)

    out: list[str] = []
    for win in Desktop(backend="uia").windows():
        try:
            if not win.is_visible():
                continue
            title = win.window_text()
            cls = win.class_name()
        except Exception:
            continue
        if cls not in ("#32770", "Chrome_WidgetWin_1") and not title:
            continue
        out.append(f"\n=== title={title!r}  class={cls!r} ===")
        try:
            for ctrl in win.descendants():
                try:
                    out.append(
                        f"    {ctrl.friendly_class_name():<18} "
                        f"text={ctrl.window_text()!r:<40} "
                        f"auto_id={getattr(ctrl.element_info, 'automation_id', '')!r}"
                    )
                except Exception:
                    continue
        except Exception as e:
            out.append(f"    <could not enumerate: {e}>")

    text = "\n".join(out)
    print(text)
    return text


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 1
    if argv[0] == "snap":
        if len(argv) < 2:
            print("error: snap needs a name", file=sys.stderr)
            return 1
        snap(argv[1])
        return 0
    if argv[0] == "dialogs":
        dump_dialogs()
        return 0
    print(f"unknown command: {argv[0]}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Remove the macOS automation**

Every screenshot in `image-upload-workflow/ui_templates/` is of the macOS UI and cannot match on Windows; `upload_to_cricut.py` is superseded by `mtgproxy/cricut/`.

```bash
git rm -r image-upload-workflow/
```

- [ ] **Step 4: Walk the Design Space flow and capture each screen**

With Design Space open and a blank canvas, run `python -m mtgproxy.cricut.probe snap <name>` at each of these states, advancing the UI by hand between captures:

| name | state to capture |
|---|---|
| `01_canvas` | blank canvas, left rail visible |
| `02_upload_panel` | after clicking Upload, the "Upload Image" button visible |
| `03_browse` | the Upload Image panel with its Browse button |
| `04_preview` | image preview with Continue |
| `05_bg_remover` | Background Remover screen with Apply & Continue |
| `06_convert` | "Convert Upload To" screen — **note that Multiple Layers, not Flat Graphic, is preselected** |
| `07_details` | Image Details screen with Upload |
| `08_library` | library grid with the new image |
| `09_canvas_placed` | image on canvas, size fields visible in the toolbar |
| `10_make_it` | Make It / mat preview |
| `11_bleed` | the print preview showing the **bleed toggle**, captured in its OFF state |
| `12_send` | the Send to Printer button |

- [ ] **Step 5: Dump the native dialogs**

With the **file-open dialog** on screen: `python -m mtgproxy.cricut.dump_dialogs` — actually run `python -m mtgproxy.cricut.probe dialogs`.
Then repeat with the **print dialog** on screen.

Record for each: the exact window `title`, `class`, the name of the filename Edit control, and the name of the confirm Button.

- [ ] **Step 6: Crop the button templates**

From the screenshots in `debug/recon/`, crop each button into `mtgproxy/cricut/templates/` using these exact filenames — `flow.py` in Task 7 references them by name:

```
01_upload_image_btn.png     06_continue_btn.png        11_bleed_toggle_off.png
02_browse_btn.png           07_upload_btn.png          11_bleed_toggle_on.png
04_continue_btn.png         08_library_first_image.png 12_send_to_printer_btn.png
05_apply_continue_btn.png   09_add_to_canvas_btn.png
06a_flat_graphic_option.png 10_make_it_btn.png
                            13_width_field.png
```

Crop tightly to the button, including a few pixels of surrounding background for context. Avoid including any text that changes between sheets (e.g. a filename).

Use Pillow to crop precisely:

```python
from PIL import Image
Image.open("debug/recon/02_upload_panel.png").crop((left, top, right, bottom)).save(
    "mtgproxy/cricut/templates/01_upload_image_btn.png"
)
```

- [ ] **Step 7: Record the findings**

Write `docs/superpowers/notes/cricut-ui-recon.md` capturing: the file-dialog title/class/control names, the print-dialog title/class, whether the print dialog is a native `#32770` **or** an in-app Chromium print preview (this changes Task 6 — if it is in-app, the gate detects it by template instead of UIA), and any screen whose button proved hard to crop distinctly.

- [ ] **Step 8: Commit**

```bash
git add mtgproxy/cricut/ requirements.txt docs/superpowers/notes/cricut-ui-recon.md
git commit -m "feat: cricut package skeleton, UI recon probe, captured Windows templates"
```

---

### Task 6: `screen.py` — locate and click Design Space's Chromium UI

**Files:**
- Create: `mtgproxy/cricut/screen.py`
- Test: `tests/test_screen.py`

**Interfaces:**
- Produces:
  - `class TemplateNotFound(RuntimeError)`
  - `match(screen: Image, template: Image) -> tuple[float, tuple[int, int]]` — best confidence and its centre, in screenshot pixels
  - `class Screen(template_dir: Path, confidence: float = 0.8, debug_dir: Path, grab: Callable[[], Image])`
    - `.scale() -> float`
    - `.find(name: str, timeout: float = 10.0) -> tuple[float, tuple[int, int]] | None` — logical screen coords
    - `.require(name: str, timeout: float = 10.0) -> tuple[int, int]` — raises `TemplateNotFound` and dumps a debug screenshot
    - `.click(name: str, timeout: float = 10.0, settle: float = 1.0) -> None`
- Consumed by: `flow.py` (Task 7), `run.py` (Task 8)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_screen.py`:

```python
from pathlib import Path

import pytest
from PIL import Image

from mtgproxy.cricut.screen import Screen, TemplateNotFound, match


def _screen_with_button(button_xy=(200, 150)) -> tuple[Image.Image, Image.Image]:
    """An 800x600 grey 'screen' with a 60x30 red 'button' pasted into it, plus
    the button image on its own to use as the template."""
    screen = Image.new("RGB", (800, 600), (128, 128, 128))
    button = Image.new("RGB", (60, 30), (220, 30, 30))
    screen.paste(button, button_xy)
    return screen, button


def test_match_finds_the_button_centre():
    screen, button = _screen_with_button((200, 150))
    confidence, (cx, cy) = match(screen, button)
    assert confidence > 0.9
    assert (cx, cy) == (230, 165)  # 200+60//2, 150+30//2


def test_find_returns_none_when_the_button_is_absent(tmp_path):
    screen = Image.new("RGB", (800, 600), (128, 128, 128))  # no button
    _, button = _screen_with_button()
    (tmp_path / "btn.png").parent.mkdir(parents=True, exist_ok=True)
    button.save(tmp_path / "btn.png")

    s = Screen(template_dir=tmp_path, debug_dir=tmp_path / "debug", grab=lambda: screen)
    assert s.find("btn.png", timeout=0.1) is None


def test_require_raises_and_dumps_a_debug_screenshot(tmp_path):
    screen = Image.new("RGB", (800, 600), (128, 128, 128))  # no button
    _, button = _screen_with_button()
    button.save(tmp_path / "btn.png")
    debug = tmp_path / "debug"

    s = Screen(template_dir=tmp_path, debug_dir=debug, grab=lambda: screen)
    with pytest.raises(TemplateNotFound, match="btn.png"):
        s.require("btn.png", timeout=0.1)

    dumps = list(debug.glob("*btn*.png"))
    assert dumps, "a debug screenshot naming the failed template must be written"


def test_require_raises_when_the_template_file_is_missing(tmp_path):
    s = Screen(template_dir=tmp_path, debug_dir=tmp_path / "debug", grab=lambda: Image.new("RGB", (10, 10)))
    with pytest.raises(TemplateNotFound, match="missing"):
        s.require("nope.png", timeout=0.1)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_screen.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mtgproxy.cricut.screen'`

- [ ] **Step 3: Implement `mtgproxy/cricut/screen.py`**

```python
"""Locating and clicking Design Space's own UI by matching pixels.

Design Space is Electron/Chromium and exposes no UI Automation tree, so this is
the only way in. Native Windows dialogs are NOT handled here — see native.py,
which has real control handles and needs none of this guesswork.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import pyautogui
from PIL import Image

DEFAULT_CONFIDENCE = 0.8
TEMPLATE_DIR = Path(__file__).parent / "templates"
DEBUG_DIR = Path(__file__).resolve().parents[2] / "debug"


class TemplateNotFound(RuntimeError):
    """A template could not be located on screen, or its file is missing.

    Always fatal: a half-recognized UI is exactly when blind clicking is most
    dangerous, because the next click lands somewhere unintended and there is a
    blade attached.
    """


def match(screen: Image.Image, template: Image.Image) -> tuple[float, tuple[int, int]]:
    """Best match of template within screen. Returns (confidence, centre_xy) in
    screenshot pixels. Grayscale, so theme/colour shifts do not break matching."""
    s = cv2.cvtColor(np.array(screen.convert("RGB")), cv2.COLOR_RGB2GRAY)
    t = cv2.cvtColor(np.array(template.convert("RGB")), cv2.COLOR_RGB2GRAY)
    result = cv2.matchTemplate(s, t, cv2.TM_CCOEFF_NORMED)
    _, confidence, _, (x, y) = cv2.minMaxLoc(result)
    return float(confidence), (x + t.shape[1] // 2, y + t.shape[0] // 2)


@dataclass
class Screen:
    template_dir: Path = TEMPLATE_DIR
    confidence: float = DEFAULT_CONFIDENCE
    debug_dir: Path = DEBUG_DIR
    grab: Callable[[], Image.Image] = field(default=lambda: pyautogui.screenshot())

    def scale(self) -> float:
        """Screenshot pixels per logical screen point. 1.0 at 100% DPI, but
        computed rather than assumed so a display change does not silently send
        every click to the wrong place."""
        shot_w, _ = self.grab().size
        screen_w, _ = pyautogui.size()
        return shot_w / screen_w

    def load(self, name: str) -> Image.Image:
        path = self.template_dir / name
        if not path.is_file():
            raise TemplateNotFound(f"template file missing: {path}")
        return Image.open(path)

    def find(self, name: str, timeout: float = 10.0) -> tuple[float, tuple[int, int]] | None:
        """Poll for the template. Returns (confidence, logical_xy) or None."""
        template = self.load(name)
        scale = self.scale()
        deadline = time.time() + timeout
        best = 0.0
        while True:
            confidence, (x, y) = match(self.grab(), template)
            best = max(best, confidence)
            if confidence >= self.confidence:
                return confidence, (round(x / scale), round(y / scale))
            if time.time() >= deadline:
                return None
            time.sleep(0.3)

    def require(self, name: str, timeout: float = 10.0) -> tuple[int, int]:
        """find(), but a miss is fatal and leaves evidence behind."""
        hit = self.find(name, timeout=timeout)
        if hit is None:
            self._dump(name)
            raise TemplateNotFound(
                f"could not find {name} on screen within {timeout}s "
                f"(debug screenshot written to {self.debug_dir})"
            )
        return hit[1]

    def click(self, name: str, timeout: float = 10.0, settle: float = 1.0) -> None:
        x, y = self.require(name, timeout=timeout)
        pyautogui.moveTo(x, y, duration=0.2)
        pyautogui.click()
        time.sleep(settle)

    def _dump(self, name: str) -> None:
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%H%M%S")
        self.grab().save(self.debug_dir / f"miss_{Path(name).stem}_{stamp}.png")
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_screen.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/cricut/screen.py tests/test_screen.py
git commit -m "feat: template matching for Design Space's Chromium UI"
```

---

### Task 7: `native.py` — drive the Windows dialogs through UI Automation

**Write this against the identifiers recorded in Task 5's recon notes.** The names below are the expected Windows 11 common-dialog names; if recon found different ones, use what recon found — that is the entire reason recon came first.

**Files:**
- Create: `mtgproxy/cricut/native.py`
- Test: `tests/test_native.py`

**Interfaces:**
- Produces:
  - `class DialogNotFound(RuntimeError)`
  - `wait_for_dialog(title_re: str, timeout: float = 30.0, class_name: str = "#32770") -> WindowSpecification`
  - `choose_file(path: Path, timeout: float = 30.0) -> None`
  - `wait_for_print_dialog(timeout: float = 120.0) -> None`
- Consumed by: `run.py` (Task 8)

- [ ] **Step 1: Write the failing tests**

Only the failure path is testable without a live dialog — but it is the path that matters, because a hang here would strand a run.

Create `tests/test_native.py`:

```python
from pathlib import Path

import pytest

from mtgproxy.cricut.native import DialogNotFound, choose_file, wait_for_dialog


def test_wait_for_dialog_raises_rather_than_hanging_when_absent():
    with pytest.raises(DialogNotFound, match="NoSuchDialogAnywhere"):
        wait_for_dialog("NoSuchDialogAnywhere", timeout=0.5)


def test_choose_file_raises_when_no_open_dialog_is_up(tmp_path):
    target = tmp_path / "sheet_01.png"
    target.write_bytes(b"not really a png")
    with pytest.raises(DialogNotFound):
        choose_file(target, timeout=0.5)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_native.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mtgproxy.cricut.native'`

- [ ] **Step 3: Implement `mtgproxy/cricut/native.py`**

```python
"""Driving the native Windows dialogs Design Space opens — the file picker and
the print dialog — through UI Automation.

These are real Win32 windows with real control handles, so we address controls
directly instead of matching pixels. This is what replaces the macOS version's
AppleScript "Go to Folder" dance: no typing races, no warm-up keystrokes, no
double-Enter, no reading the field back to see what actually landed in it.

Anything Design Space itself draws belongs in screen.py, not here.
"""
from __future__ import annotations

import time
from pathlib import Path

from pywinauto import Desktop

FILE_DIALOG_CLASS = "#32770"


class DialogNotFound(RuntimeError):
    """A native dialog did not appear in time. Fatal — never fall through to
    clicking blind."""


def wait_for_dialog(title_re: str, timeout: float = 30.0, class_name: str = FILE_DIALOG_CLASS):
    """Poll for a visible top-level dialog whose title matches title_re."""
    deadline = time.time() + timeout
    while True:
        try:
            dlg = Desktop(backend="uia").window(class_name=class_name, title_re=title_re)
            if dlg.exists(timeout=0.2) and dlg.is_visible():
                return dlg
        except Exception:
            pass
        if time.time() >= deadline:
            raise DialogNotFound(
                f"no dialog matching title~={title_re!r} class={class_name!r} within {timeout}s"
            )
        time.sleep(0.3)


def choose_file(path: Path, timeout: float = 30.0) -> None:
    """Put an absolute path into the open dialog's File name box and confirm.

    Setting the edit text directly (rather than typing it) is why this cannot
    drop keystrokes the way the macOS version could.
    """
    dlg = wait_for_dialog(r".*(Open|Select|Choose).*", timeout=timeout)
    edit = dlg.child_window(title="File name:", control_type="Edit")
    edit.wait("exists enabled visible ready", timeout=10)
    edit.set_edit_text(str(Path(path).resolve()))
    time.sleep(0.2)
    try:
        dlg.child_window(title="Open", control_type="Button").click_input()
    except Exception:
        edit.type_keys("{ENTER}")
    dlg.wait_not("visible", timeout=timeout)


def wait_for_print_dialog(timeout: float = 120.0) -> None:
    """Block until the print dialog appears. This is the gate: the script stops
    here and a human clicks Print. We never click it — that spends paper and ink.
    """
    wait_for_dialog(r".*Print.*", timeout=timeout)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_native.py -v`
Expected: PASS (both raise `DialogNotFound` promptly rather than hanging).

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/cricut/native.py tests/test_native.py
git commit -m "feat: drive Windows file and print dialogs via UI Automation"
```

---

### Task 8: `flow.py` — the per-sheet sequence, as data

Expressing the sequence as data (rather than a wall of imperative clicks) is what makes a Cricut UI update a one-line edit plus a re-screenshot, and what makes `--dry-run` possible at all.

**Files:**
- Create: `mtgproxy/cricut/flow.py`
- Test: `tests/test_flow.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Step(name: str, action: str, template: str | None = None, template_alt: str | None = None, timeout: float = 10.0, settle: float = 1.0)`
  - `SHEET_FLOW: tuple[Step, ...]`
  - `TEMPLATES: tuple[str, ...]` — every template file the flow needs
  - `SHEET_WIDTH_IN: float`
  - `ACTIONS: frozenset[str]` — the action names `run.py` must dispatch on
- Consumed by: `run.py` (Task 9)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_flow.py`:

```python
from mtgproxy.cricut import flow
from mtgproxy.cricut.screen import TEMPLATE_DIR


def test_every_referenced_template_file_exists():
    # Turns "you forgot to screenshot a button" into a test failure instead of a
    # mid-run halt at sheet 7.
    missing = [t for t in flow.TEMPLATES if not (TEMPLATE_DIR / t).is_file()]
    assert not missing, f"missing template files: {missing}"


def test_every_step_uses_a_known_action():
    unknown = [s.name for s in flow.SHEET_FLOW if s.action not in flow.ACTIONS]
    assert not unknown, f"steps with unknown actions: {unknown}"


def test_click_steps_all_carry_a_template():
    naked = [s.name for s in flow.SHEET_FLOW if s.action == "click" and not s.template]
    assert not naked, f"click steps with no template: {naked}"


def test_the_flow_gates_before_it_resets_and_never_prints():
    actions = [s.action for s in flow.SHEET_FLOW]
    assert "gate" in actions, "the flow must stop at the print dialog"
    assert actions.index("gate") < actions.index("reset"), "gate before reset"
    assert "print" not in actions, "the script must never click Print"


def test_sheet_width_matches_the_generated_sheet():
    # 2 cards x 63mm + one 8mm gap = 134mm
    assert abs(flow.SHEET_WIDTH_IN - 134.0 / 25.4) < 0.001
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_flow.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mtgproxy.cricut.flow'`

- [ ] **Step 3: Implement `mtgproxy/cricut/flow.py`**

```python
"""The per-sheet journey through Design Space, expressed as data.

Design Space auto-updates, and every one of these steps is a pixel match against
a Chromium UI that Cricut can restyle at will. Keeping the sequence as a list of
Steps means a UI change is a one-line edit and a fresh screenshot, not a
debugging session — and it is what lets --dry-run report on every step without
clicking anything.
"""
from __future__ import annotations

from dataclasses import dataclass

from mtgproxy.geometry import MM_PER_INCH, GeometryConfig

#: The sheet is 2 cards wide plus one gap: 2*63 + 8 = 134mm. Design Space ignores
#: the PNG's DPI, so the image must be resized to this by hand once on canvas.
_CFG = GeometryConfig()
SHEET_WIDTH_IN = (
    _CFG.cols * _CFG.card_w_mm + (_CFG.cols - 1) * _CFG.gap_mm
) / MM_PER_INCH

ACTIONS = frozenset(
    {
        "ensure_panel",   # deselect, and reopen the Upload rail only if it is hidden
        "click",          # locate template, click it
        "choose_file",    # hand off to native.py's file dialog
        "set_width",      # click the W field, type SHEET_WIDTH_IN, commit
        "ensure_toggle",  # click `template` if present, then REQUIRE `template_alt`
        "gate",           # wait for the print dialog, then wait for the human
        "reset",          # return the canvas to empty
    }
)


@dataclass(frozen=True)
class Step:
    name: str
    action: str
    template: str | None = None
    template_alt: str | None = None
    timeout: float = 10.0
    settle: float = 1.0


SHEET_FLOW: tuple[Step, ...] = (
    # A completed upload leaves the new layer selected on canvas, which swaps the
    # left panel for an object-properties toolbar and hides the Upload button.
    # Deselect first; only click the rail tab if the button is genuinely hidden,
    # because the tab template matches its active styling too and clicking an
    # already-open tab toggles it shut.
    Step("ensure upload panel", "ensure_panel", "01_upload_image_btn.png", settle=0.5),
    Step("Upload Image", "click", "01_upload_image_btn.png"),
    Step("Browse", "click", "02_browse_btn.png"),
    # Native Windows dialog from here — no pixel matching.
    Step("pick the sheet file", "choose_file", timeout=30.0),
    # Large sheets are slow to render a first preview.
    Step("Continue (preview)", "click", "04_continue_btn.png", timeout=45.0),
    # Apply & Continue stays greyed (and so will not match) until the full-res
    # preview finishes rendering. Nothing to remove — our sheets are already RGBA.
    Step("Apply & Continue (bg remover)", "click", "05_apply_continue_btn.png", timeout=60.0),
    # "Convert Upload To" defaults to Multiple Layers, NOT Flat Graphic. Selecting
    # it explicitly is mandatory or every sheet converts wrong for Print Then Cut.
    Step("Flat Graphic", "click", "06a_flat_graphic_option.png", timeout=15.0),
    Step("Continue (convert)", "click", "06_continue_btn.png"),
    Step("Upload", "click", "07_upload_btn.png", timeout=30.0),
    # An uploaded image lands in the LIBRARY, not on the canvas.
    Step("select the new image", "click", "08_library_first_image.png", timeout=30.0),
    Step("Add to Canvas", "click", "09_add_to_canvas_btn.png"),
    # The size fields only exist once the image is on the canvas.
    Step("set width", "set_width", "13_width_field.png"),
    Step("Make It", "click", "10_make_it_btn.png", timeout=20.0),
    # Without bleed, the blade cuts exactly on the printed edge and any drift
    # shows white paper. Click the toggle if it reads OFF, then REQUIRE that it
    # now reads ON — never assume a silent skip meant it was already on.
    Step(
        "ensure bleed is ON",
        "ensure_toggle",
        template="11_bleed_toggle_off.png",
        template_alt="11_bleed_toggle_on.png",
        timeout=30.0,
    ),
    Step("Send to Printer", "click", "12_send_to_printer_btn.png", timeout=20.0),
    # The script stops here. A human clicks Print, cuts, reloads paper.
    Step("print gate", "gate", timeout=120.0),
    Step("clear the canvas", "reset"),
)

TEMPLATES: tuple[str, ...] = tuple(
    dict.fromkeys(
        t
        for step in SHEET_FLOW
        for t in (step.template, step.template_alt)
        if t is not None
    )
)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_flow.py -v`
Expected: all PASS. If `test_every_referenced_template_file_exists` fails, Task 5's cropping is incomplete — go finish it.

- [ ] **Step 5: Commit**

```bash
git add mtgproxy/cricut/flow.py tests/test_flow.py
git commit -m "feat: per-sheet Design Space flow as data"
```

---

### Task 9: `run.py` — preflight, dry run, the gate, and the reset

**Files:**
- Create: `mtgproxy/cricut/run.py`
- Test: `tests/test_run.py`

**Interfaces:**
- Produces: `main(argv: list[str] | None = None) -> int`, `preflight(sheets: list[Path], screen: Screen) -> None`, `dry_run(screen: Screen) -> int`, `run_sheet(screen, sheet, gate) -> None`
- CLI: `python -m mtgproxy.cricut.run --sheets ./sheets [--dry-run] [--start-at N]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_run.py`:

```python
from pathlib import Path

import pytest
from PIL import Image

from mtgproxy.cricut.run import list_sheets, preflight
from mtgproxy.cricut.screen import Screen, TemplateNotFound


def _sheets(tmp_path, n):
    d = tmp_path / "sheets"
    d.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        Image.new("RGBA", (10, 10)).save(d / f"sheet_{i:02d}.png")
    return d


def test_list_sheets_is_ordered_numerically(tmp_path):
    d = _sheets(tmp_path, 12)
    names = [p.name for p in list_sheets(d)]
    assert names[0] == "sheet_01.png"
    assert names[-1] == "sheet_12.png"


def test_list_sheets_honours_start_at(tmp_path):
    d = _sheets(tmp_path, 5)
    names = [p.name for p in list_sheets(d, start_at=4)]
    assert names == ["sheet_04.png", "sheet_05.png"]


def test_preflight_rejects_an_empty_sheets_folder(tmp_path):
    empty = tmp_path / "sheets"
    empty.mkdir()
    with pytest.raises(ValueError, match="no sheets"):
        preflight(list_sheets(empty), Screen(template_dir=tmp_path, grab=lambda: Image.new("RGB", (8, 8))))


def test_preflight_rejects_missing_templates(tmp_path):
    d = _sheets(tmp_path, 1)
    empty_templates = tmp_path / "no_templates"
    empty_templates.mkdir()
    screen = Screen(template_dir=empty_templates, grab=lambda: Image.new("RGB", (8, 8)))
    with pytest.raises(TemplateNotFound):
        preflight(list_sheets(d), screen)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_run.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mtgproxy.cricut.run'`

- [ ] **Step 3: Implement `mtgproxy/cricut/run.py`**

```python
"""Run every sheet through Design Space, stopping at the print dialog.

The script drives upload, placement, sizing, Make It and Print Then Cut. It does
NOT click Print, and does NOT press the Cricut's Go button: both spend physical
material, and both stay with the human. The riskiest surface in this system is
one we deliberately do not automate.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import pyautogui

from mtgproxy.cricut import native
from mtgproxy.cricut.flow import SHEET_FLOW, SHEET_WIDTH_IN, TEMPLATES, Step
from mtgproxy.cricut.screen import Screen, TemplateNotFound

_SHEET_RE = re.compile(r"sheet_(\d+)\.png$", re.IGNORECASE)


def list_sheets(folder: Path, start_at: int = 1) -> list[Path]:
    """Sheets in numeric order — not lexicographic, which would put sheet_10
    before sheet_2 the moment a deck needs ten or more sheets."""
    found: list[tuple[int, Path]] = []
    for p in sorted(folder.glob("*.png")):
        m = _SHEET_RE.search(p.name)
        if m:
            found.append((int(m.group(1)), p))
    return [p for n, p in sorted(found) if n >= start_at]


def preflight(sheets: list[Path], screen: Screen) -> None:
    """Fail before touching anything, rather than halfway through sheet 7."""
    if not sheets:
        raise ValueError("no sheets to run — generate them with `mtgproxy.cli --sticker` first")
    for name in TEMPLATES:
        screen.load(name)  # raises TemplateNotFound if a template file is missing


def dry_run(screen: Screen) -> int:
    """Walk the flow and report whether each template can be SEEN, clicking
    nothing. Step through Design Space by hand while this runs: this is how we
    find out the templates are good before anything can misfire."""
    print("Dry run — locating each template. Nothing will be clicked.\n")
    misses = 0
    for step in SHEET_FLOW:
        for template in (step.template, step.template_alt):
            if template is None:
                continue
            hit = screen.find(template, timeout=1.0)
            if hit:
                print(f"  FOUND    {template:<28} confidence={hit[0]:.3f}  at {hit[1]}")
            else:
                print(f"  not seen {template:<28} ({step.name})")
                misses += 1
    print(f"\n{len(TEMPLATES) - misses}/{len(TEMPLATES)} templates visible on this screen.")
    return 0


def _set_width(screen: Screen, step: Step) -> None:
    """Design Space ignores the PNG's DPI, so the sheet imports at some arbitrary
    size. Set the width numerically; aspect lock carries the height."""
    x, y = screen.require(step.template, timeout=step.timeout)
    pyautogui.click(x, y)
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.typewrite(f"{SHEET_WIDTH_IN:.3f}")
    pyautogui.press("tab")
    time.sleep(step.settle)


def _ensure_toggle(screen: Screen, step: Step) -> None:
    """Click the toggle if it reads OFF, then REQUIRE that it now reads ON.

    A silent skip must never be mistaken for "it was already on": if the OFF
    template stops matching because Cricut restyled it, we would print every
    sheet with no bleed and get a white sliver on every card.
    """
    if screen.find(step.template, timeout=step.timeout):
        screen.click(step.template, timeout=step.timeout, settle=step.settle)
    screen.require(step.template_alt, timeout=step.timeout)


def _ensure_panel(screen: Screen, step: Step) -> None:
    """A finished upload leaves the layer selected, which hides the left panel
    behind an object-properties toolbar. Deselect; only click the rail tab if the
    Upload button is genuinely not visible — the tab template matches its active
    styling too, so clicking an already-open tab would toggle it shut."""
    pyautogui.press("escape")
    time.sleep(step.settle)
    if screen.find(step.template, timeout=1.0) is None:
        screen.click("00_upload_tab.png", timeout=5.0, settle=0.5)


def _reset(screen: Screen, step: Step) -> None:
    """Return the canvas to empty. Without this, sheet N+1 stacks on top of sheet
    N and every subsequent sheet is wrong. Invariant: exactly one image on the
    canvas at a time."""
    pyautogui.press("escape")
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.3)
    pyautogui.press("delete")
    time.sleep(step.settle)


def _gate(sheet: Path, index: int, total: int) -> None:
    native.wait_for_print_dialog(timeout=120.0)
    print(
        f"\n  >>> Sheet {index}/{total} ({sheet.name}) is at the print dialog."
        f"\n  >>> Print it, cut it, reload paper — then press Enter here to continue."
    )
    input()


def run_sheet(screen: Screen, sheet: Path, index: int, total: int) -> None:
    print(f"\n[{index}/{total}] {sheet.name}")
    for step in SHEET_FLOW:
        print(f"  - {step.name}")
        if step.action == "click":
            screen.click(step.template, timeout=step.timeout, settle=step.settle)
        elif step.action == "ensure_panel":
            _ensure_panel(screen, step)
        elif step.action == "choose_file":
            native.choose_file(sheet, timeout=step.timeout)
        elif step.action == "set_width":
            _set_width(screen, step)
        elif step.action == "ensure_toggle":
            _ensure_toggle(screen, step)
        elif step.action == "gate":
            _gate(sheet, index, total)
        elif step.action == "reset":
            _reset(screen, step)
        else:
            raise RuntimeError(f"unknown action {step.action!r} in step {step.name!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Drive Cricut Design Space through Print Then Cut for each sheet, "
        "stopping at the print dialog so a human clicks Print."
    )
    parser.add_argument("--sheets", default="./sheets", help="Folder of sheet PNGs.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Locate every template and report confidence. Clicks nothing.",
    )
    parser.add_argument(
        "--start-at", type=int, default=1, help="Resume from sheet N (1-based)."
    )
    args = parser.parse_args(argv)

    pyautogui.FAILSAFE = True  # slam the mouse into a screen corner to abort
    screen = Screen()

    if args.dry_run:
        return dry_run(screen)

    sheets = list_sheets(Path(args.sheets), start_at=args.start_at)
    try:
        preflight(sheets, screen)
    except (ValueError, TemplateNotFound) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print("Bring Cricut Design Space to the foreground, on a blank canvas.")
    print("Starting in 5 seconds. Move the mouse to a screen corner to abort.")
    time.sleep(5)

    total = len(sheets)
    for i, sheet in enumerate(sheets, start=args.start_at):
        try:
            run_sheet(screen, sheet, i, total + args.start_at - 1)
        except (TemplateNotFound, native.DialogNotFound) as e:
            print(f"\nerror on {sheet.name}: {e}", file=sys.stderr)
            print(
                f"Halted. Fix the template or the UI, then resume with "
                f"--start-at {i}",
                file=sys.stderr,
            )
            return 1

    print(f"\nDone — {total} sheet(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add the `00_upload_tab.png` template**

`_ensure_panel` references it. Crop it from `debug/recon/01_canvas.png` (the Upload tab on the left rail) into `mtgproxy/cricut/templates/00_upload_tab.png`, and add it to `flow.py`'s first step so the existence test covers it:

```python
    Step("ensure upload panel", "ensure_panel", "01_upload_image_btn.png",
         template_alt="00_upload_tab.png", settle=0.5),
```

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add mtgproxy/cricut/run.py mtgproxy/cricut/flow.py mtgproxy/cricut/templates/00_upload_tab.png tests/test_run.py
git commit -m "feat: run sheets through Design Space with a preflight, dry run, and printer gate"
```

---

### Task 10: Bring-up — prove it without wasting paper

Each step is attempted only once the previous one is clean. **These are human gates, not automated checks.**

- [ ] **Step 1: Dry run**

With Design Space open, run:
```bash
python -m mtgproxy.cricut.run --dry-run
```
Step through the UI by hand as it goes. Every template that *should* be visible on the current screen must report `FOUND` with confidence ≥ 0.8. Re-crop any template that reports low confidence or matches the wrong thing.

Do not proceed until the dry run is clean.

- [ ] **Step 2: One sheet, live, to the gate — but do not print**

```bash
python -m mtgproxy.cricut.run --sheets ./sheets --start-at 1
```
Let it run one sheet. At the gate, **before printing**, confirm in Design Space:
- the canvas image measures **5.276 in** wide,
- the **bleed toggle is ON**,
- the print preview shows **4 cards plus registration marks**,
- the cut preview outlines all four cards with rounded corners.

Then cancel the print dialog and abort the script (Ctrl+C).

- [ ] **Step 3: One sheet, printed and cut**

Re-run and this time actually print it, cut it, and measure with calipers:
- card size **63 × 88 mm ± 0.3 mm**
- corner radius **~3 mm**
- the cut sits in ink — **no white sliver** on any edge
- no tearing on removal (peel the mat away from the card, not the card off the mat)

**This is the real go/no-go.** If the size or registration drifts, run Design Space's **Print Then Cut calibration** routine — that is a machine procedure, not a code bug. Do not go hunting through Python for a hardware problem.

- [ ] **Step 4: The full run**

```bash
python -m mtgproxy.cricut.run --sheets ./sheets
```
21 sheets. If it halts, it tells you the `--start-at N` to resume from.

---

### Task 11: Update the run-book

**Files:**
- Modify: `docs/RUNBOOK.md`

- [ ] **Step 1: Rewrite `docs/RUNBOOK.md`**

```markdown
# MTG Proxy Print-and-Cut Run-book (Windows)

## One-time setup
- `pip install -r requirements.txt`
- Cricut: run **Print Then Cut calibration** in Design Space.
- Load a LightGrip (blue) mat; install a clean Fine-Point blade.
- No cut template is needed. Sheets are transparent PNGs and Design Space
  generates the cut lines from the transparency itself.

## Each batch
1. In **MPC Autofill**, choose the art per card; let it download the images.
2. Generate the sheets:
   `python -m mtgproxy.cli --input "<mpc-autofill-folder>" --out ./sheets --sticker`
   - Optional exact quantities/order: `--manifest order.txt` (lines `filename.png,quantity`).
   - Source images with no bleed: add `--bleed 0`.
3. Open Design Space on a blank canvas, then:
   `python -m mtgproxy.cricut.run --sheets ./sheets`
4. Per sheet the script drives upload → canvas → size → Make It → Print Then Cut,
   then **stops at the print dialog**. Confirm the bleed toggle is ON, click
   **Print** yourself, let the ink dry flat 2-3 min, then cut.
5. Press Enter in the terminal to move to the next sheet.
6. Remove each card by peeling the **mat away from the card** (flip the mat
   face-down and roll it back). Never lift the card off the mat.
7. Sleeve each proxy with a real card or basic land behind it.

If the script halts, it prints the `--start-at N` needed to resume.
Move the mouse to a screen corner at any time to abort it.

## First-run verification (do once, then trust it)
Print one sheet and check with calipers:
- Card size 63 x 88 mm (+/- 0.3 mm)
- Corner radius ~3 mm
- The cut sits in ink, with no white sliver
- No tearing on removal

If the size or registration is off, re-run Design Space's **Print Then Cut
calibration**. That is a machine procedure, not a code bug.

## Troubleshooting
| Symptom | Fix |
|---|---|
| Script halts on a template it cannot see | Design Space auto-updated its UI. Look at the screenshot in `debug/`, re-crop that template, resume with `--start-at N`. |
| Cricut cannot read registration marks | good black ink; matte paper; even lighting, no glare; marks not cut off; mat loaded straight |
| White sliver on a cut edge | the bleed toggle was OFF on the Make It screen; re-run Print Then Cut calibration |
| Cards come out slightly too small | regenerate the sheets — this was a real bug (bleed squeezed into the trim box); confirm the canvas image is 5.276 in wide |
| Paper curls -> sensor fails | dry flat, gently back-roll, load flat |
| Card tears on removal | LightGrip mat + mat-away-from-card technique |
| Cut does not go all the way through | custom/"more" pressure, fresh blade, multi-cut x2 |
```

- [ ] **Step 2: Commit**

```bash
git add docs/RUNBOOK.md
git commit -m "docs: run-book for the Windows print-and-cut workflow"
```

---

## Self-Review

**Spec coverage.** Every spec section maps to a task: the bleed bug → Task 2; the sticker gap floor and `template_coords` removal → Task 3; `screen.py`/`native.py`/`flow.py`/`run.py` → Tasks 6–9; the gate, reset, failure handling and `--start-at` → Task 9; unit tests → Tasks 2, 3, 6, 7, 8, 9; the dry run and staged bring-up → Tasks 9 and 10; the run-book → Task 11. Task 5 (recon) was added beyond the spec because `native.py` and `flow.py` cannot be written honestly against an unobserved UI — the spec's open question of whether the print dialog is native or in-app is resolved there, and Task 7 says what to do with each answer.

**Type consistency.** `Screen.find` returns `tuple[float, tuple[int,int]] | None` and `Screen.require` returns `tuple[int,int]`; `run.py` uses `hit[0]` for confidence and `hit[1]` for the point in `dry_run`, and unpacks `x, y` from `require` in `_set_width`. `Step` fields (`name`, `action`, `template`, `template_alt`, `timeout`, `settle`) are used consistently across `flow.py` and `run.py`. `TEMPLATES` collects both `template` and `template_alt`, so the `00_upload_tab.png` added in Task 9 Step 4 is covered by Task 8's existence test.

**Known soft spot.** The template filenames in Task 8 are a contract that Task 5's cropping must fulfil. If recon finds the real UI differs (for instance, the print dialog turns out to be an in-app Chromium preview rather than a native `#32770`), `flow.py`'s step list and `native.wait_for_print_dialog` are the two places to change — which is exactly the flexibility the data-driven design was for.
