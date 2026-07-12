"""The per-sheet journey through Design Space's upload flow, expressed as data.

Design Space auto-updates, and every one of these steps is a pixel match against
a Chromium UI that Cricut can restyle at will. Keeping the sequence as a list of
Steps means a UI change is a one-line edit and a fresh screenshot rather than a
debugging session — and it is what lets --dry-run report on every step without
clicking anything.

Verified against Design Space 9.76.91 on Windows 11 by driving the real UI; see
docs/superpowers/notes/cricut-ui-recon.md.
"""
from __future__ import annotations

from dataclasses import dataclass

from mtgproxy.geometry import MM_PER_INCH, GeometryConfig

#: The sheet geometry the compositor produced. The print flow has to tell Design
#: Space the same number, so it is derived here rather than typed in twice.
_CFG = GeometryConfig()

#: Every action name run.py must dispatch on.
ACTIONS = frozenset(
    {
        "ensure_panel",  # deselect, and reopen the Upload rail only if it is hidden
        "click",         # locate the template, click it
        "choose_file",   # hand off to native.py — this one is a Windows dialog
        "clear_canvas",  # return the canvas to empty for the next sheet
    }
)


@dataclass(frozen=True)
class Step:
    name: str
    action: str
    template: str | None = None
    template_alt: str | None = None
    #: Click this many pixels from the template's centre. For inputs whose own
    #: contents change (the width box holds a different number every time), the
    #: template anchors on the adjacent static label and the offset reaches the
    #: field itself.
    click_offset: tuple[int, int] = (0, 0)
    timeout: float = 10.0
    settle: float = 1.0


UPLOAD_FLOW: tuple[Step, ...] = (
    # A finished upload leaves the new layer selected on the canvas and switches
    # the left rail to Images, both of which hide the Upload Image button. So the
    # panel has to be re-established before every sheet, not just the first.
    Step("ensure the upload panel is open", "ensure_panel", "01_upload_image_btn.png", settle=0.6),
    Step("Upload Image", "click", "01_upload_image_btn.png", settle=1.5),
    Step("Browse", "click", "02_browse_btn.png", settle=1.5),
    # Native Windows dialog from here — see native.py. No pixel matching.
    Step("pick the sheet file", "choose_file", timeout=30.0),
    # A first preview of a 1582x2174 sheet takes a while to render.
    Step("Continue (preview)", "click", "04_continue_btn.png", timeout=60.0, settle=2.0),
    # Nothing to remove — our sheets are already RGBA with the background
    # transparent. The button stays greyed (and so will not match) until the
    # full-res preview finishes rendering, which is slow.
    Step("Apply & Continue (background remover)", "click", "05_apply_continue_btn.png",
         timeout=90.0, settle=2.0),
    # "Convert Upload To" preselects Multiple Layers, NOT Flat Graphic. Selecting
    # it explicitly is mandatory: Multiple Layers converts the sheet wrong for
    # Print Then Cut. (Same trap as macOS — it survived the port.)
    Step("Flat Graphic", "click", "06a_flat_graphic.png", timeout=30.0, settle=1.2),
    Step("Continue (convert)", "click", "04_continue_btn.png", timeout=20.0, settle=2.0),
    Step("Upload", "click", "07_upload_btn.png", timeout=30.0, settle=4.0),
    # Design Space drops the uploaded image straight onto the canvas (it does not
    # sit in the library waiting to be added — that is the macOS behaviour). Left
    # there, sheet N+1 would stack on top of sheet N and every later sheet would
    # be wrong. Invariant: the canvas is empty before the next sheet starts.
    # 20_make_disabled is the POST-condition, not a thing to click: with an empty
    # canvas Design Space greys the Make button out. If it is still live, something
    # survived the delete and the next sheet would stack on top of it.
    Step("clear the canvas", "clear_canvas", "20_make_disabled.png", timeout=15.0, settle=1.5),
)

#: Every template file the flow needs, including ones an action reaches for that
#: are not the step's own `template` (the Upload rail tab). Deduplicated: Continue
#: is the same control on the preview and convert screens.
TEMPLATES: tuple[str, ...] = tuple(
    dict.fromkeys(
        [s.template for s in UPLOAD_FLOW if s.template] + ["00_upload_tab.png"]
    )
)


# --- Printing ---------------------------------------------------------------
#
# Per sheet: pull it out of the library, size it, Make It, force Letter, send to
# the printer — then STOP. The human clicks Print and runs the Cricut. Nothing
# past the Print Setup dialog is automated, because everything past it spends
# paper, ink, and a blade.

PRINT_ACTIONS = frozenset(
    {
        "ensure_panel",       # the library grid must be showing
        "place_sheet",        # find THIS sheet's own artwork in the library, click it
        "click",
        "set_width",          # the sheet imports at ~10.98in; force it to 5.276in
        "select_letter",      # Material Size defaults to A4 and must be Letter
        "ensure_bleed",       # Add Bleed must be ON or the cut shows white edges
        "gate",               # hand over to the human; never click Print
        "reset_after_print",  # back to an empty canvas for the next sheet
    }
)

#: The sheet is 2 cards wide plus one gap: 2*63 + 8 = 134mm. Design Space ignores
#: the PNG's DPI and imports it at about 10.98in, so this has to be set by hand.
SHEET_WIDTH_IN = (
    _CFG.cols * _CFG.card_w_mm + (_CFG.cols - 1) * _CFG.gap_mm
) / MM_PER_INCH

PRINT_FLOW: tuple[Step, ...] = (
    Step("open the library", "ensure_panel", "01_upload_image_btn.png", settle=0.8),
    # Identified by its own artwork, then re-checked against every other sheet at
    # the tile it landed on. A mis-pick here prints the wrong card onto real paper.
    Step("find this sheet in the library", "place_sheet", timeout=20.0, settle=3.5),
    Step("open the Size popover", "click", "30_size_btn.png", timeout=20.0, settle=1.2),
    # The width box holds a different number each time, so it cannot be a template.
    # Anchor on the static "W" label beside it and reach across.
    Step("set the width", "set_width", "31_width_label.png",
         click_offset=(38, 0), timeout=15.0, settle=1.5),
    Step("Make", "click", "21_make_enabled.png", timeout=20.0, settle=6.0),
    # Design Space defaults Material Size to A4 (8.3 x 11.7in). Our paper is Letter.
    # Left alone, the registration marks are laid out for the wrong page.
    Step("set Material Size to Letter", "select_letter", "40_material_size.png",
         template_alt="41_letter_option.png", click_offset=(0, 36),
         timeout=25.0, settle=2.5),
    Step("Continue", "click", "04_continue_btn.png", timeout=25.0, settle=6.0),
    Step("Send to Printer", "click", "50_send_to_printer.png", timeout=30.0, settle=3.0),
    # Print Setup. Wait for the Print button to go green — Design Space enumerates
    # printers slowly and shows "No printers found" first — and assert Add Bleed is
    # on. Then stop and let the human look at it.
    Step("hand over at the print dialog", "gate", "52_print_ready.png",
         template_alt="53_bleed_on.png", timeout=180.0),
    Step("back to an empty canvas", "reset_after_print", "20_make_disabled.png",
         template_alt="21_make_enabled.png", timeout=600.0, settle=1.5),
)

PRINT_TEMPLATES: tuple[str, ...] = tuple(
    dict.fromkeys(
        [t for s in PRINT_FLOW for t in (s.template, s.template_alt) if t]
        + ["00_upload_tab.png", "51_add_bleed.png",
           "60_make_cancel.png", "61_verify_done.png",
           "62_connect_machine.png", "63_confirm_yes.png"]
    )
)
