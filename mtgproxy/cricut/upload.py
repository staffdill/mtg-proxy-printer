"""Upload every sheet into the Cricut Design Space library.

Drives Design Space's upload flow once per sheet and clears the canvas between
them. It does not print, does not size anything, and never presses the Cricut's
Go button.

Note that size is deliberately not set here: Design Space stores an uploaded image
at its native pixels, so the canvas size does not persist to the library. Each
sheet still has to be resized to 5.276 in when it is later placed to print.

    python -m mtgproxy.cricut.upload --sheets ./sheets
    python -m mtgproxy.cricut.upload --dry-run          # locate templates, click nothing
    python -m mtgproxy.cricut.upload --start-at 4       # resume after a failure
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import pyautogui

from mtgproxy.cricut import native
from mtgproxy.cricut.flow import TEMPLATES, UPLOAD_FLOW, Step
from mtgproxy.cricut.screen import Screen, TemplateNotFound

_SHEET_RE = re.compile(r"sheet_(\d+)\.png$", re.IGNORECASE)

#: A point on the canvas that is always empty — right of the placed sheet, above
#: the zoom controls. Clicking here gives the canvas keyboard focus so Ctrl+A
#: selects the artwork rather than whatever panel last had focus.
EMPTY_CANVAS_XY = (1650, 1150)


def list_sheets(folder: Path, start_at: int = 1) -> list[Path]:
    """Sheets in numeric order — not lexicographic, which would run sheet_10
    before sheet_2 the moment a deck needs ten or more sheets."""
    numbered = []
    for path in folder.glob("*.png"):
        m = _SHEET_RE.search(path.name)
        if m:
            numbered.append((int(m.group(1)), path))
    return [p for n, p in sorted(numbered) if n >= start_at]


def preflight(sheets: list[Path], screen: Screen) -> None:
    """Fail before touching anything, rather than halfway through sheet 7."""
    if not sheets:
        raise ValueError(
            "no sheets found — generate them first with "
            "`python -m mtgproxy.cli --input <folder> --out ./sheets --sticker`"
        )
    for name in TEMPLATES:
        screen.load(name)  # raises TemplateNotFound if the file is missing


def ensure_panel(screen: Screen, step: Step) -> None:
    """Make the Upload Image button reachable.

    After an upload, Design Space leaves the new layer selected (which swaps the
    left panel for an object-properties toolbar) and switches the rail to Images.
    Both hide the button. Deselect first, then click the Upload rail tab only if
    the button is genuinely not visible — clicking a tab that is already open
    toggles it shut.
    """
    pyautogui.press("escape")
    time.sleep(step.settle)
    if screen.find(step.template, timeout=1.0) is None:
        screen.click("00_upload_tab.png", timeout=10.0, settle=1.2)


def clear_canvas(screen: Screen, step: Step) -> None:
    """Return the canvas to empty so the next sheet does not stack on this one."""
    pyautogui.press("escape")
    time.sleep(0.4)
    pyautogui.click(*EMPTY_CANVAS_XY)  # give the canvas keyboard focus
    time.sleep(0.4)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.4)
    pyautogui.press("delete")
    time.sleep(step.settle)


def upload_sheet(screen: Screen, sheet: Path, index: int, total: int) -> None:
    print(f"\n[{index}/{total}] {sheet.name}")
    for step in UPLOAD_FLOW:
        print(f"    {step.name}")
        if step.action == "click":
            screen.click(step.template, timeout=step.timeout, settle=step.settle)
        elif step.action == "ensure_panel":
            ensure_panel(screen, step)
        elif step.action == "choose_file":
            native.choose_file(sheet, timeout=step.timeout)
        elif step.action == "clear_canvas":
            clear_canvas(screen, step)
        else:
            raise RuntimeError(f"unknown action {step.action!r} in step {step.name!r}")


def dry_run(screen: Screen) -> int:
    """Report whether each template can be SEEN, clicking nothing. Step through
    Design Space by hand while this runs: this is how we find out the templates
    are good before anything can misfire."""
    print("Dry run — locating each template. Nothing will be clicked.\n")
    seen = 0
    for name in TEMPLATES:
        hit = screen.find(name, timeout=1.0)
        if hit:
            print(f"  FOUND     {name:<28} confidence={hit[0]:.3f}  at {hit[1]}")
            seen += 1
        else:
            print(f"  not seen  {name:<28}")
    print(f"\n{seen}/{len(TEMPLATES)} templates visible on the current screen.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Upload proxy sheets into the Cricut Design Space library."
    )
    parser.add_argument("--sheets", default="./sheets", help="Folder of sheet PNGs.")
    parser.add_argument("--start-at", type=int, default=1, help="Resume from sheet N.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Locate every template and report confidence. Clicks nothing.",
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

    last = args.start_at + len(sheets) - 1
    print(f"Uploading sheets {args.start_at}..{last} ({len(sheets)} total).")
    print("Bring Design Space to the front, on the Canvas tab, canvas empty.")
    print("Starting in 5s. Move the mouse to a screen corner to abort.")
    time.sleep(5)

    for offset, sheet in enumerate(sheets):
        index = args.start_at + offset
        try:
            upload_sheet(screen, sheet, index, last)
        except (TemplateNotFound, native.DialogNotFound) as e:
            print(f"\nerror on {sheet.name}: {e}", file=sys.stderr)
            print(f"Halted. Fix the cause, then resume with --start-at {index}", file=sys.stderr)
            return 1

    print(f"\nDone — {len(sheets)} sheet(s) uploaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
