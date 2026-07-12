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
    Step("clear the canvas", "clear_canvas", settle=1.0),
)

#: Every template file the flow needs. Deduplicated: the Continue button is the
#: same control on the preview and convert screens.
TEMPLATES: tuple[str, ...] = tuple(
    dict.fromkeys(s.template for s in UPLOAD_FLOW if s.template)
) + ("00_upload_tab.png",)
