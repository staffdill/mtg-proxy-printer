from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from mtgproxy.cricut import flow
from mtgproxy.cricut.native import DialogNotFound, choose_file, wait_for_dialog
from mtgproxy.cricut.screen import TEMPLATE_DIR, Screen, TemplateNotFound, match
from mtgproxy.cricut.upload import list_sheets, preflight


def _screen_with_button(xy=(200, 150)):
    """An 800x600 grey 'screen' with a 60x30 button pasted in, plus the button on
    its own to use as a template.

    The button carries internal contrast on purpose: normalized correlation cannot
    match a featureless template, so a solid-colour one would exercise nothing a
    real button does.
    """
    screen = Image.new("RGB", (800, 600), (128, 128, 128))
    button = Image.new("RGB", (60, 30), (220, 30, 30))
    ImageDraw.Draw(button).rectangle([12, 8, 47, 21], fill=(255, 255, 255))  # "label"
    screen.paste(button, xy)
    return screen, button


def _sheets(tmp_path, n):
    d = tmp_path / "sheets"
    d.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        Image.new("RGBA", (8, 8)).save(d / f"sheet_{i:02d}.png")
    return d


# --- screen.py -------------------------------------------------------------


def test_match_finds_the_button_centre():
    screen, button = _screen_with_button((200, 150))
    confidence, centre = match(screen, button)
    assert confidence > 0.9
    assert centre == (230, 165)  # 200 + 60//2, 150 + 30//2


def test_find_returns_none_when_the_button_is_absent(tmp_path):
    _, button = _screen_with_button()
    button.save(tmp_path / "btn.png")
    blank = Image.new("RGB", (800, 600), (128, 128, 128))

    s = Screen(template_dir=tmp_path, debug_dir=tmp_path / "dbg", grab=lambda: blank)
    assert s.find("btn.png", timeout=0.1) is None


def test_require_raises_and_dumps_a_screenshot_of_what_was_there(tmp_path):
    _, button = _screen_with_button()
    button.save(tmp_path / "btn.png")
    blank = Image.new("RGB", (800, 600), (128, 128, 128))
    debug = tmp_path / "dbg"

    s = Screen(template_dir=tmp_path, debug_dir=debug, grab=lambda: blank)
    with pytest.raises(TemplateNotFound, match="btn.png"):
        s.require("btn.png", timeout=0.1)

    assert list(debug.glob("miss_btn_*.png")), "a debug screenshot must be left behind"


def test_require_raises_when_the_template_file_is_missing(tmp_path):
    s = Screen(template_dir=tmp_path, debug_dir=tmp_path / "dbg",
               grab=lambda: Image.new("RGB", (8, 8)))
    with pytest.raises(TemplateNotFound, match="missing"):
        s.require("nope.png", timeout=0.1)


def test_match_refuses_a_featureless_template():
    # A flat crop has no variance, so normalized correlation is undefined and
    # OpenCV returns a confident match at an arbitrary place. Clicking there is
    # the worst thing this program could do, so it must refuse instead.
    screen = Image.new("RGB", (800, 600), (128, 128, 128))
    blank_template = Image.new("RGB", (40, 20), (200, 200, 200))
    with pytest.raises(TemplateNotFound, match="featureless"):
        match(screen, blank_template)


# --- flow.py ---------------------------------------------------------------


def test_every_referenced_template_file_exists():
    # Turns "you forgot to screenshot a button" into a test failure rather than a
    # mid-run halt on sheet 7.
    missing = [t for t in flow.TEMPLATES if not (TEMPLATE_DIR / t).is_file()]
    assert not missing, f"missing template files: {missing}"


def test_every_step_uses_a_known_action():
    unknown = [s.name for s in flow.UPLOAD_FLOW if s.action not in flow.ACTIONS]
    assert not unknown, f"steps with unknown actions: {unknown}"


def test_click_steps_all_carry_a_template():
    naked = [s.name for s in flow.UPLOAD_FLOW if s.action == "click" and not s.template]
    assert not naked, f"click steps with no template: {naked}"


def test_flat_graphic_is_selected_before_continuing_past_the_convert_screen():
    # Design Space preselects Multiple Layers, which converts the sheet wrong for
    # Print Then Cut. If this ordering ever breaks, every sheet is silently ruined.
    names = [s.name for s in flow.UPLOAD_FLOW]
    assert names.index("Flat Graphic") < names.index("Continue (convert)")


def test_the_canvas_is_cleared_after_the_upload():
    # Without this, sheet N+1 stacks on sheet N and every later sheet is wrong.
    actions = [s.action for s in flow.UPLOAD_FLOW]
    assert actions[-1] == "clear_canvas"


# --- upload.py -------------------------------------------------------------


def test_list_sheets_orders_numerically_not_lexicographically(tmp_path):
    d = _sheets(tmp_path, 12)
    names = [p.name for p in list_sheets(d)]
    assert names[0] == "sheet_01.png"
    assert names[-1] == "sheet_12.png"


def test_list_sheets_honours_start_at(tmp_path):
    d = _sheets(tmp_path, 5)
    assert [p.name for p in list_sheets(d, start_at=4)] == ["sheet_04.png", "sheet_05.png"]


def test_preflight_rejects_an_empty_sheets_folder(tmp_path):
    empty = tmp_path / "sheets"
    empty.mkdir()
    screen = Screen(template_dir=TEMPLATE_DIR, grab=lambda: Image.new("RGB", (8, 8)))
    with pytest.raises(ValueError, match="no sheets"):
        preflight(list_sheets(empty), screen)


def test_preflight_rejects_missing_templates(tmp_path):
    d = _sheets(tmp_path, 1)
    no_templates = tmp_path / "empty"
    no_templates.mkdir()
    screen = Screen(template_dir=no_templates, grab=lambda: Image.new("RGB", (8, 8)))
    with pytest.raises(TemplateNotFound):
        preflight(list_sheets(d), screen)


# --- native.py -------------------------------------------------------------


def test_wait_for_dialog_raises_rather_than_hanging_when_absent():
    with pytest.raises(DialogNotFound, match="NoSuchDialogAnywhere"):
        wait_for_dialog("NoSuchDialogAnywhere", timeout=0.5)


def test_choose_file_raises_when_no_open_dialog_is_up(tmp_path):
    target = tmp_path / "sheet_01.png"
    Image.new("RGBA", (8, 8)).save(target)
    with pytest.raises(DialogNotFound):
        choose_file(target, timeout=0.5)


# --- safety: the destructive path ------------------------------------------


def test_clear_canvas_refuses_to_send_keystrokes_when_design_space_is_not_focused(monkeypatch):
    # Ctrl+A + Delete goes wherever the keyboard focus is. If Design Space is not
    # the foreground window, those keys would select and destroy the contents of
    # whatever IS focused. It must refuse rather than fire blind.
    from mtgproxy.cricut import native, upload

    monkeypatch.setattr(native, "_window_text", lambda hwnd: "Notepad - untitled")

    pressed = []
    monkeypatch.setattr(upload.pyautogui, "press", lambda *a, **k: pressed.append(a))
    monkeypatch.setattr(upload.pyautogui, "hotkey", lambda *a, **k: pressed.append(a))
    monkeypatch.setattr(upload.pyautogui, "click", lambda *a, **k: pressed.append(a))

    step = flow.Step("clear", "clear_canvas", "20_make_disabled.png")
    screen = Screen(grab=lambda: Image.new("RGB", (64, 64)))

    with pytest.raises(native.DesignSpaceNotFocused, match="Notepad"):
        upload.clear_canvas(screen, step)

    assert pressed == [], "not a single key may be sent when the wrong window is focused"


def test_preflight_rejects_a_featureless_template(tmp_path, monkeypatch):
    # A flat crop cannot be matched by normalized correlation, and OpenCV answers
    # with a confident match at an arbitrary place. preflight is the only thing
    # that catches this before the run starts clicking.
    from mtgproxy.cricut import upload

    bad = tmp_path / "templates"
    bad.mkdir()
    for name in flow.TEMPLATES:
        Image.new("RGB", (40, 20), (210, 210, 210)).save(bad / name)  # featureless

    sheets = _sheets(tmp_path, 1)
    screen = Screen(template_dir=bad, grab=lambda: Image.new("RGB", (64, 64)))
    with pytest.raises(TemplateNotFound, match="featureless"):
        upload.preflight(list_sheets(sheets), screen)


def test_templates_includes_the_rail_tab_and_the_canvas_empty_check():
    # Both are loaded at runtime by actions rather than being a step's own
    # template, so they are exactly the ones a naive TEMPLATES would miss --
    # and preflight would then not validate them.
    assert "00_upload_tab.png" in flow.TEMPLATES
    assert "20_make_disabled.png" in flow.TEMPLATES


def test_templates_do_not_collide_with_each_other():
    """No template may confidently match a DIFFERENT template's button.

    Design Space's buttons are all the same green pill, and a whole-pill crop of
    "Browse" was measured matching the "Upload" pill on another screen at 0.96 --
    close enough to a true match to be clicked in its place. Cropping to the label
    text opened the gap. This guards it: re-crop a template too loosely and this
    fails, instead of the run clicking the wrong button on a slow render.
    """
    from mtgproxy.cricut.screen import DEFAULT_CONFIDENCE

    loaded = {n: Image.open(TEMPLATE_DIR / n).convert("RGB") for n in flow.TEMPLATES}
    collisions = []
    for haystack_name, haystack in loaded.items():
        # Paste the template into a white field so any other template fits inside it.
        pad = 40
        field = Image.new(
            "RGB", (haystack.width + 2 * pad, haystack.height + 2 * pad), (255, 255, 255)
        )
        field.paste(haystack, (pad, pad))
        for needle_name, needle in loaded.items():
            if needle_name == haystack_name:
                continue
            if needle.width > field.width or needle.height > field.height:
                continue
            confidence, _ = match(field, needle)
            if confidence >= DEFAULT_CONFIDENCE:
                collisions.append(f"{needle_name} matches {haystack_name} at {confidence:.3f}")
    assert not collisions, "templates collide:\n  " + "\n  ".join(collisions)


# --- printing: picking the right sheet out of the library -------------------


def _distinct_sheets(tmp_path, n=4):
    """Sheets that actually look different, like the real ones do."""
    d = tmp_path / "sheets"
    d.mkdir(parents=True, exist_ok=True)
    palette = [(220, 40, 40), (40, 160, 220), (40, 200, 90), (230, 190, 40)]
    for i in range(1, n + 1):
        im = Image.new("RGB", (158, 217), (255, 255, 255))
        dr = ImageDraw.Draw(im)
        dr.rectangle([10, 10, 148, 207], fill=palette[(i - 1) % len(palette)])
        dr.text((20, 100), f"S{i}" * 6, fill=(0, 0, 0))
        dr.ellipse([30 + 12 * i, 30, 90 + 12 * i, 120], fill=(0, 0, 0))
        im.save(d / f"sheet_{i:02d}.png")
    return d


def test_locate_sheet_picks_the_right_tile_out_of_a_grid(tmp_path):
    from mtgproxy.cricut import printing

    d = _distinct_sheets(tmp_path, 4)
    sheets = list_sheets(d)

    # A fake library: the four sheets laid out in a grid on white.
    lib = Image.new("RGB", (400, 400), (255, 255, 255))
    spots = {}
    for i, s in enumerate(sheets):
        t = printing.sheet_thumbnail(s)
        x, y = 30 + (i % 2) * 180, 30 + (i // 2) * 180
        lib.paste(t, (x, y))
        spots[s] = (x + t.width // 2, y + t.height // 2)

    screen = Screen(grab=lambda: lib, template_dir=TEMPLATE_DIR)
    for s in sheets:
        assert printing.locate_sheet(screen, s, sheets) == spots[s], f"{s.name} landed wrong"


def test_clear_canvas_waits_for_the_upload_to_land_before_deleting(monkeypatch):
    """Design Space places the uploaded image on the canvas ASYNCHRONOUSLY.

    A clear that fires while the canvas is still empty deletes nothing, sees Make
    greyed out, and declares success — and then the image lands and the next sheet
    stacks on top of it. That is not hypothetical: it left sheet_11 and sheet_15
    stranded on the canvas across a real 31-sheet run.
    """
    from mtgproxy.cricut import upload

    state = {"landed": False, "deleted": False, "asked": []}

    class _Canvas:
        confidence = 0.9

        def require(self, name, timeout=10.0):
            state["asked"].append(name)
            if name == "21_make_enabled.png":
                state["landed"] = True  # the image arrives while we are waiting for it
                if state["deleted"]:
                    raise TemplateNotFound("canvas is empty")
                return (0, 0)
            if name == "20_make_disabled.png":
                if not state["deleted"]:
                    raise TemplateNotFound("canvas is not empty")
                return (0, 0)
            raise AssertionError(f"unexpected template {name}")

        def find(self, name, timeout=10.0):
            if name == "21_make_enabled.png" and not state["deleted"]:
                return (1.0, (0, 0))
            return None

        def _dump(self, name):
            pass

    def fake_delete(screen, step):
        assert state["landed"], "deleted before the image had even landed on the canvas"
        state["deleted"] = True

    monkeypatch.setattr(upload, "_delete_everything", fake_delete)
    monkeypatch.setattr(upload.time, "sleep", lambda _s: None)
    # clear_canvas guards on the REAL foreground window. Without this the test passes
    # or fails depending on which window the developer happens to have focused.
    monkeypatch.setattr(
        upload.native, "require_design_space_foreground", lambda: (0, 0, 100, 100)
    )

    step = next(s for s in flow.UPLOAD_FLOW if s.action == "clear_canvas")
    upload.clear_canvas(_Canvas(), step)

    assert state["deleted"], "the canvas was never actually cleared"
    assert state["asked"][0] == "21_make_enabled.png", (
        "clear_canvas must confirm the image LANDED before deleting; checking only "
        "that the canvas is empty passes trivially when the upload is still in flight"
    )


def test_click_step_reclicks_when_design_space_swallowed_the_click():
    """A click dropped mid-render is silent. Without a witness the flow walks on and
    dies at the NEXT step, looking for a screen it never reached (observed: sheet 27
    sat on Convert Upload To while waiting 30s for the Upload button)."""
    from mtgproxy.cricut import upload

    clicks = []
    state = {"screen": "convert"}

    class _S:
        def click(self, name, timeout=10.0, settle=1.0):
            clicks.append(name)
            if len(clicks) >= 2:          # the first click is swallowed
                state["screen"] = "next"

        def find(self, name, timeout=10.0):
            on_convert = state["screen"] == "convert"
            return (1.0, (0, 0)) if (name == "06a_flat_graphic.png" and on_convert) else None

        def _dump(self, name):
            pass

    step = next(s for s in flow.UPLOAD_FLOW if s.name == "Continue (convert)")
    assert step.advances_past == "06a_flat_graphic.png"

    upload.click_step(_S(), step)
    assert clicks == ["04_continue_btn.png"] * 2, "must click again when the screen did not move"


def test_click_step_gives_up_rather_than_clicking_forever():
    from mtgproxy.cricut import upload

    clicks = []

    class _S:
        def click(self, name, timeout=10.0, settle=1.0):
            clicks.append(name)

        def find(self, name, timeout=10.0):
            return (1.0, (0, 0))  # the witness never goes away

        def _dump(self, name):
            pass

    step = next(s for s in flow.UPLOAD_FLOW if s.name == "Continue (convert)")
    with pytest.raises(TemplateNotFound):
        upload.click_step(_S(), step)
    assert len(clicks) == upload.CLICK_ATTEMPTS


def _no_real_scrolling(monkeypatch, printing, on_top=None, on_down=None):
    """Never let a test drive the physical mouse.

    locate_sheet scrolls the real Uploads grid when a sheet is not in view, and a
    test that reaches that path would move the live pointer and scroll whatever
    Design Space happens to be showing — on the machine running the tests.
    """
    monkeypatch.setattr(printing, "scroll_library_to_top", on_top or (lambda s: None))
    monkeypatch.setattr(printing, "scroll_library_down", on_down or (lambda s: False))


def test_locate_sheet_refuses_when_the_sheet_is_not_in_the_library(tmp_path, monkeypatch):
    from mtgproxy.cricut import printing

    _no_real_scrolling(monkeypatch, printing)
    d = _distinct_sheets(tmp_path, 4)
    sheets = list_sheets(d)
    # A library holding everything EXCEPT sheet_03.
    lib = Image.new("RGB", (400, 400), (255, 255, 255))
    for i, s in enumerate(s for s in sheets if s.stem != "sheet_03"):
        t = printing.sheet_thumbnail(s)
        lib.paste(t, (30 + (i % 2) * 180, 30 + (i // 2) * 180))

    screen = Screen(grab=lambda: lib, debug_dir=tmp_path / "dbg")
    missing = next(s for s in sheets if s.stem == "sheet_03")
    with pytest.raises(printing.WrongSheet):
        printing.locate_sheet(screen, missing, sheets)


def test_locate_sheet_scrolls_to_reach_a_sheet_below_the_fold(tmp_path, monkeypatch):
    """The library is taller than its panel. A sheet that is merely scrolled out of
    view must be FOUND, not reported missing — with 31 sheets uploaded, that is
    every sheet but the newest few."""
    from mtgproxy.cricut import printing

    d = _distinct_sheets(tmp_path, 4)
    sheets = list_sheets(d)

    # One tall column: at most one tile fits in the viewport at a time.
    tile_pitch, view_h = 180, 200
    tall = Image.new("RGB", (400, tile_pitch * len(sheets) + 60), (255, 255, 255))
    spots = {}
    for i, s in enumerate(sheets):
        t = printing.sheet_thumbnail(s)
        x, y = 30, 30 + i * tile_pitch
        tall.paste(t, (x, y))
        spots[s] = (x + t.width // 2, y + t.height // 2)

    state = {"offset": 0}

    def grab():
        return tall.crop((0, state["offset"], 400, state["offset"] + view_h))

    def down(_screen):
        if state["offset"] + view_h >= tall.height:
            return False  # the grid stopped moving: the bottom
        state["offset"] += 50
        return True

    _no_real_scrolling(
        monkeypatch, printing,
        on_top=lambda _s: state.update(offset=0),
        on_down=down,
    )
    screen = Screen(grab=grab, debug_dir=tmp_path / "dbg")

    for s in sheets:
        state["offset"] = 0
        x, y = printing.locate_sheet(screen, s, sheets)
        # Coords come back relative to the viewport, so add back what we scrolled.
        assert (x, y + state["offset"]) == spots[s], f"{s.name} landed wrong"


class _FakeScreen:
    """Models the real post-print sequence Design Space puts you through.

    It matters that this is not "everything is findable": the Make screen's Cancel
    only reaches the Prepare screen, so the Canvas must NOT appear until Cancel has
    been clicked twice. A fake that says "you're already on the canvas" would let a
    broken backout pass.
    """

    def __init__(self, cancels_needed=2):
        self.clicks = []
        self.cancels_needed = cancels_needed

    def require(self, name, timeout=10.0):
        return (0, 0)

    def find(self, name, timeout=1.0):
        # The Print Setup dialog is treated as already closed, so gate()'s wait
        # loop exits at once.
        if "52_print_ready" in name:
            return None
        # The Canvas only shows up once we have cancelled our way back to it.
        if "make_disabled" in name or "make_enabled" in name:
            cancelled = self.clicks.count("60_make_cancel.png")
            return (1.0, (0, 0)) if cancelled >= self.cancels_needed else None
        return (1.0, (0, 0))

    def click(self, name, timeout=10.0, settle=1.0):
        self.clicks.append(name)

    def click_at(self, x, y, settle=1.0):
        # _back_to_canvas clicks the Cancel it just located, rather than searching
        # for it a second time (which races the UI).
        self.clicks.append("60_make_cancel.png")


def test_back_to_canvas_answers_the_are_you_sure_you_want_to_cancel_the_cut_banner(monkeypatch):
    """Cancel does not cancel.

    On the Prepare screen it raises an orange "Are you sure you want to cancel the
    cut?" banner, and until that is answered Yes, Design Space has not moved. A
    backout that only knows about Cancel re-clicks it every pass and burns through
    its attempts without ever reaching the Canvas — which is exactly how a real run
    got stuck.
    """
    from mtgproxy.cricut import printing

    state = {"asked": False, "left": False}
    clicks = []

    class _S:
        def find(self, name, timeout=1.0):
            if "make_disabled" in name or "make_enabled" in name:
                return (1.0, (0, 0)) if state["left"] else None
            if "64_prepare_cancel" in name:
                return None if state["left"] else (1.0, (10, 10))
            if "60_make_cancel" in name:
                return None
            if "65_cancel_cut_yes" in name:
                return (1.0, (20, 20)) if state["asked"] else None
            return None

        def click_at(self, x, y, settle=1.0):
            clicks.append((x, y))
            if (x, y) == (10, 10):        # Cancel -> only raises the banner
                state["asked"] = True
            elif (x, y) == (20, 20):      # Yes -> actually leaves
                state["left"] = True

        def _dump(self, name):
            pass

    monkeypatch.setattr(printing.native, "focus_design_space", lambda: (0, 0, 100, 100))
    printing._back_to_canvas(_S())

    assert (20, 20) in clicks, "never answered the confirmation — Cancel alone does nothing"
    assert state["left"]


def test_the_gate_never_clicks_print_unless_auto_print_was_asked_for(monkeypatch):
    # Printing is irreversible: it spends paper and ink. It must never happen
    # because of a default, an inference, or a timing accident -- only because a
    # human passed --auto-print.
    from mtgproxy.cricut import printing

    monkeypatch.setattr(printing, "ensure_bleed", lambda screen, timeout: None)
    monkeypatch.setattr(printing.native, "focus_design_space", lambda: (0, 0, 100, 100))
    gate_step = next(s for s in flow.PRINT_FLOW if s.action == "gate")
    assert gate_step.template == "52_print_ready.png"

    # cancels_needed=0: the human has already printed, cut, and come back to the
    # Canvas, which is what the non-auto gate waits for.
    screen = _FakeScreen(cancels_needed=0)
    printing.gate(screen, gate_step, Path("sheets/sheet_03.png"), 1, 1, auto_print=False)
    assert screen.clicks == [], f"the gate clicked {screen.clicks} without --auto-print"


def test_the_gate_does_print_when_auto_print_is_asked_for(monkeypatch):
    from mtgproxy.cricut import printing

    monkeypatch.setattr(printing, "ensure_bleed", lambda screen, timeout: None)
    monkeypatch.setattr(printing.native, "focus_design_space", lambda: (0, 0, 100, 100))
    gate_step = next(s for s in flow.PRINT_FLOW if s.action == "gate")
    screen = _FakeScreen()
    printing.gate(screen, gate_step, Path("sheets/sheet_03.png"), 1, 1, auto_print=True)
    # Prints, dismisses the "Verify Print Quality" modal Design Space raises once a
    # sheet has really gone to the printer, then backs out WITHOUT cutting -- the
    # cut happens later, from the saved project, so it never reaches the Go button.
    # 52 = Print. 61 = "Verify Print Quality". 63 = the "are you sure?" behind the
    # "Connect your machine" modal's X. 60 = Cancel, clicked until the Canvas is
    # actually back (the Make screen's Cancel only reaches the Prepare screen).
    assert screen.clicks[0] == "52_print_ready.png"
    assert "52_print_ready.png" not in screen.clicks[1:], "Print must be clicked exactly once"
    assert "61_verify_done.png" in screen.clicks
    # Cancelled until the Canvas actually came back -- twice here, because the Make
    # screen's Cancel only reaches the Prepare screen.
    assert screen.clicks.count("60_make_cancel.png") == 2


def test_the_flow_never_presses_go_on_the_cricut():
    actions = [s.action for s in flow.PRINT_FLOW]
    assert not any(a in ("go", "cut", "send_to_machine") for a in actions)
    src = (Path(__file__).parent.parent / "mtgproxy" / "cricut" / "printing.py").read_text(
        encoding="utf-8"
    )
    assert "press_go" not in src and "go_btn" not in src


def test_print_flow_sets_width_and_letter_before_it_reaches_the_gate():
    # Skip either and the sheet prints at the wrong size, or with the registration
    # marks laid out for A4. Both waste the sheet.
    names = [s.action for s in flow.PRINT_FLOW]
    assert names.index("set_width") < names.index("gate")
    assert names.index("select_letter") < names.index("gate")


def test_every_print_template_exists():
    missing = [t for t in flow.PRINT_TEMPLATES if not (TEMPLATE_DIR / t).is_file()]
    assert not missing, f"missing print templates: {missing}"


def test_bleed_check_ignores_the_green_layer_highlight_elsewhere_on_screen():
    """The bleed toggle must only ever be looked for beside its own label.

    Searching the whole screen for the green toggle false-matches the mint
    highlight on a selected layer in the Layers panel at 0.98. A false "bleed is
    already on" prints the entire run with a white sliver down every cut edge, so
    this is the difference between a good deck and a ruined one.
    """
    from mtgproxy.cricut import printing

    tog = Image.open(TEMPLATE_DIR / "53_bleed_on.png").convert("RGB")

    # A screen where the toggle is OFF beside the label, but a green blob the same
    # size sits somewhere else entirely (the Layers panel).
    shot = Image.new("RGB", (1400, 700), (245, 245, 245))
    label_xy = (600, 300)
    off = Image.new("RGB", tog.size, (200, 200, 200))
    ImageDraw.Draw(off).ellipse([2, 2, tog.height - 4, tog.height - 4], fill=(255, 255, 255))
    shot.paste(off, (label_xy[0] + printing.BLEED_TOGGLE_DX - tog.width // 2,
                     label_xy[1] - tog.height // 2))
    shot.paste(tog, (100, 80))  # the decoy, far from the label

    screen = Screen(grab=lambda: shot, template_dir=TEMPLATE_DIR)
    assert not printing._bleed_is_on(screen, label_xy), (
        "a green blob elsewhere on screen must not be read as 'bleed is on'"
    )

    # And when the toggle really IS on beside the label, it must say so.
    shot2 = shot.copy()
    shot2.paste(tog, (label_xy[0] + printing.BLEED_TOGGLE_DX - tog.width // 2,
                      label_xy[1] - tog.height // 2))
    screen2 = Screen(grab=lambda: shot2, template_dir=TEMPLATE_DIR)
    assert printing._bleed_is_on(screen2, label_xy)


def test_the_two_cancel_buttons_are_not_interchangeable():
    """Design Space has TWO Cancel buttons and they are visually inverted.

    The Make screen's is solid green with white text; the Prepare screen's is white
    with green text. Matched in grayscale they correlate at only ~0.67, so a single
    template silently fails to find one of them -- which is exactly how the print
    run got stranded on the Prepare screen after every sheet.
    """
    make = Image.open(TEMPLATE_DIR / "60_make_cancel.png").convert("RGB")
    prep = Image.open(TEMPLATE_DIR / "64_prepare_cancel.png").convert("RGB")
    from mtgproxy.cricut.screen import DEFAULT_CONFIDENCE

    field = Image.new("RGB", (prep.width + 40, prep.height + 40), (255, 255, 255))
    field.paste(prep, (20, 20))
    confidence, _ = match(field, make)
    assert confidence < DEFAULT_CONFIDENCE, (
        "if these two ever become interchangeable, drop 64_prepare_cancel -- but "
        f"today the Make Cancel matches the Prepare Cancel at only {confidence:.3f}"
    )


def test_reset_backs_out_of_the_make_flow_before_looking_for_the_canvas(monkeypatch):
    """A previous run can leave Design Space parked on the Prepare screen.

    There is no Make button there at all, so a reset that only looks for one waits
    out its entire timeout for something that cannot appear -- which is exactly how
    the print run stalled on startup instead of clearing the canvas.
    """
    from mtgproxy.cricut import printing

    # cancels_needed=2: we start on the Make screen, two Cancels from the Canvas.
    screen = _FakeScreen(cancels_needed=2)
    monkeypatch.setattr(printing.native, "require_design_space_foreground",
                        lambda: (0, 0, 100, 100))
    monkeypatch.setattr(printing.native, "focus_design_space", lambda: (0, 0, 100, 100))
    step = flow.Step("reset", "reset_after_print", "20_make_disabled.png", timeout=1.0)

    printing.reset_after_print(screen, step)

    assert screen.clicks.count("60_make_cancel.png") == 2, (
        "reset must cancel its way back to the Canvas before hunting for the Make button"
    )


# --- printing: catalog integration ------------------------------------------


def test_record_print_warns_but_does_not_raise_for_an_uncatalogued_sheet(tmp_path, capsys):
    from mtgproxy.cricut import printing
    from mtgproxy.catalog import Catalog

    cat = Catalog(db_path=tmp_path / "catalog.db", images_dir=tmp_path / "images")

    printing._record_print(cat, "sheets-onepiece", "sheet_01.png")  # never catalogued

    assert "catalog" in capsys.readouterr().out.lower()


def test_record_print_logs_history_for_a_catalogued_sheet(tmp_path):
    from mtgproxy.cricut import printing
    from mtgproxy.catalog import Catalog
    from PIL import Image

    cat = Catalog(db_path=tmp_path / "catalog.db", images_dir=tmp_path / "images")
    img = tmp_path / "Sol Ring.png"
    Image.new("RGB", (60, 84), "red").save(img)
    cat.catalog_sheet([img], deck_or_queue="sheets-test", sheet_file="sheet_01.png")

    printing._record_print(cat, "sheets-test", "sheet_01.png")

    card = cat.resolve(name="Sol Ring", variant_label="sheets-test")
    assert card.times_printed == 1


def test_open_catalog_returns_none_and_warns_instead_of_raising(monkeypatch, capsys):
    """A broken catalog (locked db file, permission error, ...) must degrade
    to 'no history logged', never crash the print run that's about to start."""
    from mtgproxy.cricut import printing

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated: db file locked")

    # printing.py does `from mtgproxy.catalog import Catalog`, so the name it
    # calls is bound in printing's own namespace -- patch it there, not on
    # mtgproxy.catalog, or this test would pass while calling the real Catalog.
    monkeypatch.setattr(printing, "Catalog", _boom)

    cat = printing._open_catalog(Path("unused.db"), Path("unused-images"))

    assert cat is None
    assert "catalog" in capsys.readouterr().out.lower()
