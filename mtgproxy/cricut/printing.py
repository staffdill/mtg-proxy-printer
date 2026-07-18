"""Drive Design Space through Print Then Cut for each sheet, and stop.

Per sheet: pull the sheet out of the library by its own artwork, size it to
5.276 in (Design Space imports it at ~10.98 in, which is outside the Print Then
Cut area), Make It, force Material Size to Letter (it defaults to A4), send it to
the printer — then HAND OVER.

**This never clicks Print, and never presses the Cricut's Go button.** Both spend
paper, ink, and a blade. It stops at the Print Setup dialog with everything set
up, and you look at it and decide.

    python -m mtgproxy.cricut.printing --sheets ./sheets
    python -m mtgproxy.cricut.printing --sheets ./sheets --only 3
    python -m mtgproxy.cricut.printing --start-at 4
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pyautogui
from PIL import Image

from mtgproxy.catalog import DEFAULT_DB_PATH, DEFAULT_IMAGES_DIR, Catalog, SheetNotCatalogued
from mtgproxy.cricut import native
from mtgproxy.cricut.flow import PRINT_FLOW, PRINT_TEMPLATES, SHEET_WIDTH_IN, Step
from mtgproxy.cricut.screen import Screen, TemplateNotFound, match
from mtgproxy.cricut.upload import ensure_panel, list_sheets

#: The library renders each sheet at roughly this width. Measured, not guessed.
THUMBNAIL_W = 72

#: A sheet's own thumbnail matches at 0.82-0.87 (the library re-renders it, so it
#: never reaches the ~1.0 of a flat button crop). Wrong sheets score 0.63-0.69.
#: This sits in the gap.
THUMBNAIL_CONFIDENCE = 0.78

#: ...and the right sheet must also BEAT every other sheet at the tile it landed
#: on, by this much. Measured margin across all 11 sheets was >= 0.161. A picture
#: that is merely "confident" is not enough when being wrong means printing the
#: wrong card onto real paper.
MIN_THUMBNAIL_MARGIN = 0.08


class WrongSheet(RuntimeError):
    """The tile we were about to click is not convincingly this sheet.

    Fatal. Printing the wrong sheet wastes paper and ink and leaves the deck with
    a duplicate and a hole, so guessing is never better than stopping.
    """


#: The Uploads grid is a SCROLLING panel, and it renders newest-first. A 31-sheet
#: deck does not fit in it: sheet_01 ends up ~31 tiles down, far below the fold,
#: and matching only against what happens to be visible would report it as missing
#: when it is merely scrolled out of view. So the grid gets scanned, not glanced at.
#: Both are fractions of the live Design Space window rather than screen pixels, so
#: moving or resizing the window cannot send the scroll into another application.
LIBRARY_HOVER_FRACTION = (0.09, 0.50)
LIBRARY_PANEL_FRACTION = (0.03, 0.12, 0.16, 0.96)

#: One wheel step down. The scan stops when the grid STOPS MOVING, not after a
#: fixed count — the count is only a backstop against scrolling forever.
SCROLL_NOTCHES = -300
MAX_SCROLLS = 60


def _library_region(screen: Screen) -> tuple[int, int, int, int]:
    """The Uploads grid, in screenshot pixels, from the live window rect."""
    left, top, right, bottom = native.require_design_space_foreground()
    w, h = right - left, bottom - top
    fl, ft, fr, fb = LIBRARY_PANEL_FRACTION
    s = screen.scale()
    return (
        round((left + w * fl) * s), round((top + h * ft) * s),
        round((left + w * fr) * s), round((top + h * fb) * s),
    )


def _hover_library() -> None:
    left, top, right, bottom = native.require_design_space_foreground()
    fx, fy = LIBRARY_HOVER_FRACTION
    pyautogui.moveTo(left + round((right - left) * fx), top + round((bottom - top) * fy))


def scroll_library_to_top(screen: Screen) -> None:
    """Rewind the grid so a scan starts from a known place."""
    _hover_library()
    for _ in range(MAX_SCROLLS):
        pyautogui.scroll(600)
    time.sleep(1.0)


def scroll_library_down(screen: Screen) -> bool:
    """One step down. False once the grid stops changing — that is the bottom.

    Comparing the panel's own pixels is what detects the end. A scroll count
    cannot: the library grows every time a deck is uploaded.
    """
    region = _library_region(screen)
    before = screen.grab().crop(region).tobytes()
    _hover_library()
    pyautogui.scroll(SCROLL_NOTCHES)
    time.sleep(0.8)
    return screen.grab().crop(region).tobytes() != before


def sheet_thumbnail(sheet: Path, width: int = THUMBNAIL_W) -> Image.Image:
    """The sheet as the library draws it: flattened onto white, scaled down.

    Sticker sheets are RGBA and their transparency has to be composited against
    white, or the match is against black. Sheets generated without --sticker are
    already opaque, so handle both rather than assuming.
    """
    src = Image.open(sheet)
    flat = Image.new("RGB", src.size, (255, 255, 255))
    if src.mode in ("RGBA", "LA") or "transparency" in src.info:
        rgba = src.convert("RGBA")
        flat.paste(rgba, (0, 0), rgba)
    else:
        flat.paste(src.convert("RGB"), (0, 0))
    return flat.resize((width, round(width * src.height / src.width)), Image.LANCZOS)


def identify_tile(
    screen: Screen, sheet: Path, siblings: list[Path]
) -> tuple[tuple[int, int] | None, str | None]:
    """Is this sheet on screen RIGHT NOW, beyond doubt? (centre, None) if so.

    Two checks, because the whole library is a grid of near-identical 4-up card
    sheets. First the sheet's own artwork must match somewhere with enough
    confidence. Then, at the tile it landed on, it must out-score EVERY other
    sheet by a clear margin. The second check is the one that matters: it is what
    turns "this looks like sheet 7" into "nothing else looks more like this tile
    than sheet 7 does".

    Anything short of both checks returns (None, why) and is the caller's cue to
    keep scrolling, NOT a click. That distinction is the whole point: while
    scanning past sheet_01 looking for sheet_02, sheet_02's artwork really does
    match sheet_01's tile above the confidence gate — it just loses the margin
    check. Refusing to click it is mandatory; refusing to carry on looking would
    abort a run over a tile we were only passing by.
    """
    shot = screen.grab()
    needle = sheet_thumbnail(sheet)
    confidence, centre = match(shot, needle)
    if confidence < THUMBNAIL_CONFIDENCE:
        return None, None  # simply not in view

    cx, cy = centre
    pad = 6
    tile = shot.crop(
        (
            cx - needle.width // 2 - pad,
            cy - needle.height // 2 - pad,
            cx + needle.width // 2 + pad,
            cy + needle.height // 2 + pad,
        )
    )
    scores = []
    for other in siblings:
        t = sheet_thumbnail(other)
        if t.width > tile.width or t.height > tile.height:
            continue
        scores.append((match(tile, t)[0], other))
    scores.sort(reverse=True)

    best_score, best_sheet = scores[0]
    if best_sheet != sheet:
        return None, (
            f"the tile at {centre} looks more like {best_sheet.name} "
            f"({best_score:.3f}) than {sheet.name}"
        )
    runner_up = scores[1][0] if len(scores) > 1 else 0.0
    margin = best_score - runner_up
    if margin < MIN_THUMBNAIL_MARGIN:
        return None, (
            f"the tile at {centre} is ambiguous: {sheet.name} scores {best_score:.3f} "
            f"but {scores[1][1].name} scores {runner_up:.3f} (margin {margin:.3f} < "
            f"{MIN_THUMBNAIL_MARGIN})"
        )

    print(f"      matched {sheet.name} at {centre} "
          f"(confidence {confidence:.3f}, margin over next-best {margin:+.3f})")
    return centre, None


def locate_sheet(screen: Screen, sheet: Path, siblings: list[Path]) -> tuple[int, int]:
    """Find this sheet's tile, scrolling the Uploads grid until it shows up.

    Checks the current view first — consecutive sheets are usually neighbours in
    the grid, so the common case costs no scrolling at all. Only on a miss does it
    rewind to the top and walk down. Reaching the bottom without ever seeing the
    sheet is fatal: it means the sheet is genuinely not in the library, and the
    only thing left to click would be some other deck's card.
    """
    hit, why = identify_tile(screen, sheet, siblings)
    if hit:
        return hit

    print(f"      not in view — scanning the library for {sheet.name}")
    scroll_library_to_top(screen)
    for _ in range(MAX_SCROLLS):
        hit, reason = identify_tile(screen, sheet, siblings)
        if hit:
            return hit
        why = reason or why  # keep the most informative thing we saw
        if not scroll_library_down(screen):
            break  # the grid stopped moving: that was the bottom

    screen._dump(f"thumb_{sheet.stem}")
    raise WrongSheet(
        f"{sheet.name} is not in the library — scanned the whole Uploads grid, top "
        f"to bottom, and never identified it beyond doubt. Upload it first."
        + (f" (closest call: {why})" if why else "")
    )


def place_sheet(screen: Screen, step: Step, sheet: Path, siblings: list[Path]) -> None:
    """Click the sheet's tile. One click puts it straight on the canvas."""
    x, y = locate_sheet(screen, sheet, siblings)
    pyautogui.moveTo(x, y, duration=0.2)
    pyautogui.click()
    time.sleep(step.settle)
    # Make goes green only when the canvas actually holds something.
    screen.require("21_make_enabled.png", timeout=step.timeout)


def set_width(screen: Screen, step: Step) -> None:
    """Force the sheet to its true width. Design Space ignores the PNG's DPI and
    imports it at about 10.98 in — outside the Print Then Cut area — so this is
    not a nicety, it is what makes the cards come out 63 x 88 mm."""
    ax, ay = screen.require(step.template, timeout=step.timeout)
    dx, dy = step.click_offset
    pyautogui.click(ax + dx, ay + dy)
    time.sleep(0.4)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.3)
    pyautogui.typewrite(f"{SHEET_WIDTH_IN:.3f}", interval=0.05)
    time.sleep(0.3)
    pyautogui.press("tab")
    time.sleep(step.settle)
    pyautogui.press("escape")  # close the popover so it does not cover Make
    time.sleep(0.5)


def select_letter(screen: Screen, step: Step) -> None:
    """Set Material Size to Letter. It defaults to A4 (8.3 x 11.7 in), which lays
    the registration marks out for the wrong page."""
    ax, ay = screen.require(step.template, timeout=step.timeout)
    dx, dy = step.click_offset
    pyautogui.click(ax + dx, ay + dy)  # open the dropdown
    time.sleep(1.2)
    screen.click(step.template_alt, timeout=step.timeout, settle=step.settle)


#: The Add Bleed toggle sits this far right of its own label, in a box this size.
BLEED_TOGGLE_DX = 292
BLEED_TOGGLE_BOX = (34, 22)


def _bleed_is_on(screen: Screen, label_xy: tuple[int, int]) -> bool:
    """Is the Add Bleed toggle green?

    Searched for ONLY in the small box beside its own label, never across the whole
    screen. A full-screen search for the green toggle false-matches the mint
    highlight on a selected layer in the Layers panel at 0.98 — and a false "it is
    already on" would print the whole run with no bleed and a white sliver down
    every cut edge.
    """
    ax, ay = label_xy
    w, h = BLEED_TOGGLE_BOX
    cx = ax + BLEED_TOGGLE_DX
    region = screen.grab().crop((cx - w, ay - h, cx + w, ay + h))
    template = screen.load("53_bleed_on.png")
    if template.width > region.width or template.height > region.height:
        return False
    confidence, _ = match(region, template)
    return confidence >= screen.confidence


def ensure_bleed(screen: Screen, timeout: float) -> None:
    """Add Bleed must be ON. Without it the blade cuts exactly on the printed edge
    and any registration drift shows white paper. It defaults to on — but a silent
    assumption is not a guarantee, so check it, click it if it is off, and insist."""
    ax, ay = screen.require("51_add_bleed.png", timeout=timeout)
    if not _bleed_is_on(screen, (ax, ay)):
        pyautogui.click(ax + BLEED_TOGGLE_DX, ay)
        time.sleep(1.2)
    if not _bleed_is_on(screen, (ax, ay)):
        screen._dump("bleed_off")
        raise TemplateNotFound(
            "Add Bleed is still off after clicking it — refusing to print, every "
            "card would come out with a white edge"
        )


#: How long the human gets to print, cut, and come back before the script gives up.
HANDOVER_TIMEOUT = 900.0

#: The "Connect your machine" modal's close X, relative to its title's centre.
CONNECT_CLOSE_OFFSET = (406, -19)


def _dismiss_post_print_modals(screen: Screen) -> None:
    """Clear the two modals Design Space only raises after a sheet REALLY prints.

    Neither can be seen by a dry run or a gated run, because neither exists until
    ink hits paper — which is why they were both missed until the first live
    auto-print:

    1. "Verify Print Quality" — asks you to check the sensor marks. It covers the
       Cancel button.
    2. "Connect your machine" — Design Space auto-advances to Set Base Material and
       goes looking for the Cricut. It also covers Cancel, Escape does not close
       it, and clicking its X raises a further "are you sure?" confirmation. We are
       not cutting here, so the machine being absent is expected and fine.
    """
    if screen.find("61_verify_done.png", timeout=20.0):
        screen.click("61_verify_done.png", timeout=5.0, settle=2.0)

    hit = screen.find("62_connect_machine.png", timeout=8.0)
    if hit:
        tx, ty = hit[1]
        dx, dy = CONNECT_CLOSE_OFFSET
        pyautogui.click(tx + dx, ty + dy)  # its close X
        time.sleep(1.5)
        if screen.find("63_confirm_yes.png", timeout=8.0):
            screen.click("63_confirm_yes.png", timeout=5.0, settle=2.5)


def _on_canvas(screen: Screen, timeout: float = 2.0) -> bool:
    """Are we back on the Canvas tab? The Make button only exists there — greyed
    with an empty canvas, green with something on it."""
    return bool(
        screen.find("20_make_disabled.png", timeout=timeout)
        or screen.find("21_make_enabled.png", timeout=timeout)
    )


def _back_to_canvas(screen: Screen, attempts: int = 4) -> None:
    """Cancel out of the Make flow until the Canvas is actually showing.

    One Cancel is not enough: the Make screen's Cancel drops you onto the Prepare
    screen, which needs its own. Rather than hardcode "click Cancel twice" and be
    wrong the day Cricut adds a step, click until the Canvas is genuinely there.
    """
    # Take focus back first. This runs at the end of a long unattended sheet, which
    # is exactly when a human wanders over and clicks something else — and then the
    # screenshots are of THEIR window, not Design Space, and nothing matches.
    native.focus_design_space()

    for _ in range(attempts):
        if _on_canvas(screen):
            return
        # Two different Cancels, and they are visually INVERTED: the Make screen's is
        # solid green with white text, the Prepare screen's is white with green text.
        # In grayscale they correlate at only 0.67, so one template cannot match both.
        hit = screen.find("60_make_cancel.png", timeout=6.0) or screen.find(
            "64_prepare_cancel.png", timeout=6.0
        )
        if hit is None:
            break
        # Click where find() just saw it. Re-searching (screen.click) would race the
        # UI: Design Space can move on between the two lookups, and then the click
        # raises even though the Cancel it was told about was real.
        screen.click_at(*hit[1], settle=4.0)

        # Cancel does not cancel. It raises an orange "Are you sure you want to
        # cancel the cut?" banner, and until that is answered we are still on the
        # Prepare screen — so the next pass finds Cancel again, clicks it again, and
        # the loop burns its attempts without ever leaving.
        confirm = screen.find("65_cancel_cut_yes.png", timeout=4.0)
        if confirm:
            screen.click_at(*confirm[1], settle=4.0)
    if not _on_canvas(screen, timeout=6.0):
        screen._dump("stuck_after_print")
        raise TemplateNotFound(
            "could not get back to the Canvas after printing — Design Space is stuck "
            "on some screen the flow does not know about (see debug/)"
        )


def gate(screen: Screen, step: Step, sheet: Path, index: int, total: int,
         auto_print: bool = False) -> None:
    """Stop and hand the mouse over. Everything past here spends physical material.

    Waits on the SCREEN rather than on stdin: the script has no terminal to read
    while it is driving the pointer, and tying the handover to a keypress would
    mean it could not run unattended between sheets.
    """
    # Design Space enumerates printers slowly and shows "No printers found" first;
    # Print goes green only once one is actually selected.
    screen.require(step.template, timeout=step.timeout)
    ensure_bleed(screen, timeout=step.timeout)

    if auto_print:
        # Only ever reached because a human passed --auto-print. This spends paper
        # and ink with nobody watching, so it is never the default and never
        # inferred.
        print("      --auto-print: clicking Print")
        screen.click(step.template, timeout=step.timeout, settle=3.0)
        deadline = time.time() + HANDOVER_TIMEOUT
        while screen.find(step.template, timeout=1.0) is not None:
            if time.time() >= deadline:
                raise TemplateNotFound("the Print Setup dialog never closed after Print")
            time.sleep(1.0)
        print("      printed — backing out without cutting")
        _dismiss_post_print_modals(screen)
        # Design Space now wants us to cut. We do not: the cut happens later, from
        # the saved project.
        _back_to_canvas(screen)
        return

    print(
        f"\n  >>> {sheet.name} ({index}/{total}) is at the Print Setup dialog.\n"
        f"  >>> Letter, Add Bleed ON, printer ready.\n"
        f"  >>> OVER TO YOU:\n"
        f"  >>>   1. check the preview, then click Print\n"
        f"  >>>   2. let the ink dry flat 2-3 min\n"
        f"  >>>   3. run the Cricut (Set Base Material, load the mat, press Go)\n"
        f"  >>>   4. bring Design Space back to the Canvas tab\n"
        f"  >>> I'll pick up automatically when the canvas comes back.\n"
    )

    # The dialog closing is the human acting on it — printing or cancelling.
    deadline = time.time() + HANDOVER_TIMEOUT
    while screen.find(step.template, timeout=1.0) is not None:
        if time.time() >= deadline:
            raise TemplateNotFound(
                f"still sitting at the Print Setup dialog after {HANDOVER_TIMEOUT:.0f}s"
            )
        time.sleep(1.0)
    print("      print dialog closed — waiting for you to finish the cut...")

    # Then wait for the Canvas tab to reappear, however long the cut takes.
    while time.time() < deadline:
        if screen.find("20_make_disabled.png", timeout=1.0) is not None:
            return
        if screen.find("21_make_enabled.png", timeout=1.0) is not None:
            return
        time.sleep(2.0)
    raise TemplateNotFound(
        f"Design Space never came back to the Canvas tab within {HANDOVER_TIMEOUT:.0f}s"
    )


def reset_after_print(screen: Screen, step: Step) -> None:
    """Get back to a known-empty canvas, from wherever Design Space happens to be.

    Do not assume we are on the Canvas. A previous run can leave Design Space parked
    on the Make or Prepare screen, where there is no Make button at all — so a reset
    that only looks for one waits out its whole timeout for something that cannot
    appear. Back out to the Canvas first, then clear it.
    """
    _back_to_canvas(screen)

    hit = screen.find(step.template, timeout=5.0)  # 20_make_disabled => already empty
    if hit:
        return
    # Make is live, so something is still on the canvas. Clear it — with the same
    # foreground guard as everywhere else, because this is Ctrl+A + Delete.
    left, top, right, bottom = native.require_design_space_foreground()
    pyautogui.press("escape")
    time.sleep(0.4)
    pyautogui.click(left + round((right - left) * 0.80), top + round((bottom - top) * 0.80))
    time.sleep(0.4)
    native.require_design_space_foreground()
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.4)
    pyautogui.press("delete")
    time.sleep(step.settle)
    screen.require(step.template, timeout=step.timeout)


def print_sheet(screen: Screen, sheet: Path, siblings: list[Path], index: int, total: int,
                auto_print: bool = False) -> None:
    print(f"\n[{index}/{total}] {sheet.name}")
    for step in PRINT_FLOW:
        print(f"    {step.name}")
        if step.action == "click":
            screen.click(step.template, timeout=step.timeout, settle=step.settle)
        elif step.action == "ensure_panel":
            ensure_panel(screen, step)
        elif step.action == "place_sheet":
            place_sheet(screen, step, sheet, siblings)
        elif step.action == "set_width":
            set_width(screen, step)
        elif step.action == "select_letter":
            select_letter(screen, step)
        elif step.action == "gate":
            gate(screen, step, sheet, index, total, auto_print=auto_print)
        elif step.action == "reset_after_print":
            reset_after_print(screen, step)
        else:
            raise RuntimeError(f"unknown action {step.action!r} in step {step.name!r}")


def _record_print(cat: Catalog, deck_or_queue: str, sheet_file: str) -> None:
    """Log a sheet's real, successful print in the catalog.

    Never lets catalog bookkeeping break a live print run: a sheet printed
    outside the catalogued flow (an old deck, a hand-built sheet) just warns
    and moves on, and so does any other catalog error -- the print already
    happened, real paper and ink are already spent, and nothing here should
    be able to turn that into a crashed run.
    """
    try:
        cat.record_print(deck_or_queue, sheet_file)
    except SheetNotCatalogued as e:
        print(f"      catalog: {e}")
    except Exception as e:  # noqa: BLE001 -- deliberately broad, see docstring
        print(f"      catalog: unexpected error recording print history: {e}")


def build_project(screen: Screen, sheets: list[Path], everything: list[Path]) -> None:
    """Place every sheet onto ONE canvas, each sized to 5.276in, and stop.

    Design Space has Auto Save on, so the project saves itself; name it once by
    hand. This is the artifact you open on the other machine to CUT from: Make It
    turns each Print Then Cut layer into its own mat (only one sheet fits inside
    the 6.75 x 9.25in Print Then Cut area, so they cannot share), and each mat
    offers "I've Already Printed" -> cut.

    Nothing here prints, and nothing here clears the canvas: the whole point is
    that the sheets accumulate.
    """
    place = next(s for s in PRINT_FLOW if s.action == "place_sheet")
    size_btn = next(s for s in PRINT_FLOW if s.action == "click" and s.template == "30_size_btn.png")
    width = next(s for s in PRINT_FLOW if s.action == "set_width")
    panel = next(s for s in PRINT_FLOW if s.action == "ensure_panel")

    for i, sheet in enumerate(sheets, start=1):
        print(f"\n[{i}/{len(sheets)}] adding {sheet.name}")
        ensure_panel(screen, panel)
        place_sheet(screen, place, sheet, everything)
        screen.click(size_btn.template, timeout=size_btn.timeout, settle=size_btn.settle)
        set_width(screen, width)
    print(f"\n{len(sheets)} sheet(s) on the canvas. Auto Save has saved the project.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Drive Design Space to the Print Setup dialog for each sheet, "
        "then stop so a human clicks Print."
    )
    parser.add_argument("--sheets", default="./sheets", help="Folder of sheet PNGs.")
    parser.add_argument("--start-at", type=int, default=1, help="Resume from sheet N.")
    parser.add_argument("--only", type=int, default=None, help="Do just sheet N.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Locate every template and report confidence. Clicks nothing."
    )
    parser.add_argument(
        "--build-project", action="store_true",
        help="Place and size every sheet onto ONE canvas and stop. Does not print. "
             "This is the project you open elsewhere to cut from.",
    )
    parser.add_argument(
        "--auto-print", action="store_true",
        help="Click Print automatically instead of handing over. Spends paper and ink "
             "unattended — make sure the tray holds enough matte stock for every sheet.",
    )
    parser.add_argument(
        "--catalog-db", default=str(DEFAULT_DB_PATH), help="Card catalog database path."
    )
    parser.add_argument(
        "--catalog-images-dir",
        default=str(DEFAULT_IMAGES_DIR),
        help="Card catalog's owned image storage.",
    )
    args = parser.parse_args(argv)

    pyautogui.FAILSAFE = True
    screen = Screen()
    folder = Path(args.sheets)
    everything = list_sheets(folder)  # every sheet — the pool we disambiguate against

    if args.dry_run:
        print("Dry run — locating each print-flow template. Nothing will be clicked.\n")
        for name in PRINT_TEMPLATES:
            try:
                hit = screen.find(name, timeout=1.0)
            except TemplateNotFound as e:
                print(f"  BROKEN    {name:<24} {e}")
                continue
            print(f"  {'FOUND    ' if hit else 'not seen '} {name:<24}"
                  + (f" confidence={hit[0]:.3f} at {hit[1]}" if hit else ""))
        return 0

    if not everything:
        print(f"error: no sheets in {folder}", file=sys.stderr)
        return 1
    for name in PRINT_TEMPLATES:
        try:
            screen.load(name)
        except TemplateNotFound as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

    if args.build_project:
        todo = list_sheets(folder, start_at=args.start_at)
        print(f"Building one project from {len(todo)} sheet(s). Nothing will print.")
        print("Starting in 5s. Move the mouse to a screen corner to abort.")
        time.sleep(5)
        try:
            native.focus_design_space()
            build_project(screen, todo, everything)
        except (TemplateNotFound, WrongSheet, native.DesignSpaceNotFocused, RuntimeError) as e:
            print(f"\nerror: {e}", file=sys.stderr)
            return 1
        return 0

    if args.only is not None:
        todo = [p for p in everything if int(p.stem.split("_")[1]) == args.only]
        if not todo:
            print(f"error: no sheet {args.only} in {folder}", file=sys.stderr)
            return 1
    else:
        todo = list_sheets(folder, start_at=args.start_at)

    print(f"Printing {len(todo)} sheet(s). The script stops at the Print Setup dialog")
    print("every time — it never clicks Print and never presses Go on the Cricut.")
    print("Starting in 5s. Move the mouse to a screen corner to abort.")
    time.sleep(5)

    # Take responsibility for focus rather than hoping: this types into whatever
    # window is in front.
    try:
        native.focus_design_space()
    except native.DesignSpaceNotFocused as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    # The flow clears the canvas at the END of each sheet, so sheet 2 onward starts
    # clean. Sheet 1 has no predecessor, and whatever was left on the canvas would
    # get the first sheet stacked on top of it. Clear it here rather than assume.
    reset = next(s for s in PRINT_FLOW if s.action == "reset_after_print")
    try:
        reset_after_print(screen, reset)
    except (TemplateNotFound, native.DesignSpaceNotFocused) as e:
        print(f"error: could not get to an empty canvas: {e}", file=sys.stderr)
        return 1

    cat = Catalog(db_path=Path(args.catalog_db), images_dir=Path(args.catalog_images_dir))
    for i, sheet in enumerate(todo, start=1):
        try:
            print_sheet(screen, sheet, everything, i, len(todo), auto_print=args.auto_print)
            _record_print(cat, folder.name, sheet.name)
        except (TemplateNotFound, WrongSheet, native.DialogNotFound,
                native.DesignSpaceNotFocused, RuntimeError) as e:
            n = int(sheet.stem.split("_")[1])
            print(f"\nerror on {sheet.name}: {e}", file=sys.stderr)
            if args.auto_print:
                # Never claim nothing printed when it might have. A failure AFTER the
                # Print click leaves a sheet in the tray, and telling someone to
                # resume at N would print it a second time.
                print(
                    f"Halted on {sheet.name}. It may ALREADY HAVE PRINTED — check the "
                    f"printer before resuming, and start at {n + 1} if it did.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Halted. Nothing was printed. Resume with --start-at {n}",
                    file=sys.stderr,
                )
            return 1

    print(f"\nDone — {len(todo)} sheet(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
