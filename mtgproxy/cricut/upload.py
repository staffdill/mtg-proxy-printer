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
from PIL import Image

from mtgproxy.cricut import native
from mtgproxy.cricut.flow import TEMPLATES, UPLOAD_FLOW, Step
from mtgproxy.cricut.screen import Screen, TemplateNotFound, match

_SHEET_RE = re.compile(r"sheet_(\d+)\.png", re.IGNORECASE)

#: Where inside the Design Space window to click to give the canvas keyboard
#: focus, as a fraction of the window's own size. Low and to the right: past the
#: sheet (which sits top-left on the canvas) but clear of the zoom controls along
#: the bottom edge. Derived from the live window rect rather than hardcoded to
#: screen pixels, so moving or resizing the window cannot send the click into a
#: different application.
CANVAS_FOCUS_FRACTION = (0.80, 0.80)


def list_sheets(folder: Path, start_at: int = 1) -> list[Path]:
    """Sheets in numeric order — not lexicographic, which would run sheet_10
    before sheet_2 the moment a deck needs ten or more sheets."""
    numbered = []
    for path in folder.glob("*.png"):
        m = _SHEET_RE.fullmatch(path.name)
        if m:
            numbered.append((int(m.group(1)), path))
    return [p for n, p in sorted(numbered) if n >= start_at]


def preflight(sheets: list[Path], screen: Screen) -> None:
    """Fail before touching anything, rather than halfway through sheet 7.

    Every template is loaded AND matched against a blank image here. That second
    part is not busywork: a featureless crop cannot be matched by normalized
    correlation at all, and this is the only place that catches it before the
    run starts clicking.
    """
    if not sheets:
        raise ValueError(
            "no sheets found — generate them first with "
            "`python -m mtgproxy.cli --input <folder> --out ./sheets --sticker`"
        )
    probe = Image.new("RGB", (64, 64), (255, 255, 255))
    for name in TEMPLATES:
        template = screen.load(name)  # raises TemplateNotFound if the file is missing
        canvas = Image.new("RGB", (template.width + 8, template.height + 8), (255, 255, 255))
        canvas.paste(probe.resize(canvas.size))
        match(canvas, template)  # raises TemplateNotFound if the crop is featureless


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
        screen.click("00_upload_tab.png", timeout=step.timeout, settle=1.2)


#: After the canvas reports empty, wait this long and check again. Design Space
#: places an uploaded image on the canvas ASYNCHRONOUSLY, so "empty" is not proof
#: of anything until it has had a chance to arrive late.
LATE_ARRIVAL_GRACE = 3.0

#: How many times to delete before giving up on the canvas settling.
CLEAR_ATTEMPTS = 3


def _delete_everything(screen: Screen, step: Step) -> None:
    """Ctrl+A, Delete — with the foreground guard, because it is destructive.

    Ctrl+A followed by Delete lands wherever the keyboard focus is, so this
    refuses to send it unless Design Space is genuinely the foreground window,
    and it derives the focusing click from that window's own rect instead of a
    hardcoded screen coordinate.
    """
    left, top, right, bottom = native.require_design_space_foreground()
    fx, fy = CANVAS_FOCUS_FRACTION
    x = left + round((right - left) * fx)
    y = top + round((bottom - top) * fy)

    pyautogui.press("escape")
    time.sleep(0.4)
    pyautogui.click(x, y)  # give the canvas keyboard focus
    time.sleep(0.4)

    native.require_design_space_foreground()  # the click must not have raised anything else
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.4)
    pyautogui.press("delete")
    time.sleep(step.settle)


def clear_canvas(screen: Screen, step: Step) -> None:
    """Return the canvas to empty so the next sheet does not stack on this one.

    The subtle part is WHEN. Design Space drops the uploaded image onto the canvas
    asynchronously, and it can take longer to arrive than the Upload step waits. A
    clear that fires too early finds a canvas that is empty *because the image has
    not landed yet*, deletes nothing, sees Make greyed out and declares success —
    and then the image arrives, and the next sheet stacks on top of it. Every sheet
    after that is wrong, and the run only notices when something else trips over
    the mess (observed: uploads 1-15 left sheet_11 and sheet_15 behind, and the
    Browse click then stopped opening its dialog).

    So this is a TRANSITION, not a check: wait for the image to actually be there
    (Make goes green), delete it, confirm it is gone (Make greys out) — and then
    confirm it is STILL gone after a grace period, in case it landed late.
    """
    # Before anything else, and before waiting on any template: if Design Space is
    # not the foreground window then the Ctrl+A + Delete this is building up to
    # would land in whatever IS focused. Refuse immediately rather than spend the
    # wait first and discover it at the end.
    native.require_design_space_foreground()

    for _ in range(CLEAR_ATTEMPTS):
        # The image must exist before it can be deleted.
        screen.require(step.template_alt, timeout=step.timeout)  # 21_make_enabled
        _delete_everything(screen, step)
        screen.require(step.template, timeout=step.timeout)      # 20_make_disabled => empty

        time.sleep(LATE_ARRIVAL_GRACE)
        if screen.find(step.template_alt, timeout=1.0) is None:
            return  # still empty: nothing arrived late, the canvas is genuinely clear

    screen._dump("canvas_would_not_clear")
    raise TemplateNotFound(
        f"the canvas kept refilling after {CLEAR_ATTEMPTS} deletes — Design Space is "
        f"still dropping images onto it, and the next sheet would stack on top"
    )


#: How many times to re-click a control whose screen never advanced.
CLICK_ATTEMPTS = 3


def click_step(screen: Screen, step: Step) -> None:
    """Click, and — where the step says how — prove the screen actually moved.

    Design Space drops clicks while it is rendering, and says nothing. Without a
    witness the flow cannot tell a swallowed click from a successful one: it walks
    on to the next step, looks for a screen it never reached, and blames that.
    """
    for attempt in range(1, CLICK_ATTEMPTS + 1):
        screen.click(step.template, timeout=step.timeout, settle=step.settle)
        if step.advances_past is None:
            return  # no witness declared: nothing to verify against
        if screen.find(step.advances_past, timeout=2.0) is None:
            return  # the witness is gone: the screen advanced
        print(f"      still on the same screen (attempt {attempt}/{CLICK_ATTEMPTS}) — "
              f"Design Space was busy and swallowed the click; clicking again")

    screen._dump(f"stuck_{Path(step.template).stem}")
    raise TemplateNotFound(
        f"{step.name!r}: clicked {CLICK_ATTEMPTS} times and {step.advances_past} never "
        f"went away — Design Space is not leaving this screen"
    )


def upload_sheet(screen: Screen, sheet: Path, index: int, total: int) -> None:
    print(f"\n[{index}/{total}] {sheet.name}")
    for step in UPLOAD_FLOW:
        print(f"    {step.name}")
        if step.action == "click":
            click_step(screen, step)
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
    broken = 0
    for name in TEMPLATES:
        try:
            hit = screen.find(name, timeout=1.0)
        except TemplateNotFound as e:
            # The template file itself is bad (missing, or a featureless crop).
            # Report it in the table rather than dying with a traceback — telling
            # you which templates are usable is this tool's entire job.
            print(f"  BROKEN    {name:<28} {e}")
            broken += 1
            continue
        if hit:
            print(f"  FOUND     {name:<28} confidence={hit[0]:.3f}  at {hit[1]}")
            seen += 1
        else:
            print(f"  not seen  {name:<28}")
    print(f"\n{seen}/{len(TEMPLATES)} templates visible on the current screen.")
    if broken:
        print(f"{broken} template(s) are BROKEN and must be re-cropped before running.")
        return 1
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
    print("Starting in 5s. Move the mouse to a screen corner to abort.")
    time.sleep(5)

    try:
        native.focus_design_space()
    except native.DesignSpaceNotFocused as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    for offset, sheet in enumerate(sheets):
        index = args.start_at + offset
        try:
            upload_sheet(screen, sheet, index, last)
        except (TemplateNotFound, native.DialogNotFound,
                native.DesignSpaceNotFocused, RuntimeError) as e:
            print(f"\nerror on {sheet.name}: {e}", file=sys.stderr)
            print(f"Halted. Fix the cause, then resume with --start-at {index}", file=sys.stderr)
            return 1

    print(f"\nDone — {len(sheets)} sheet(s) uploaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
