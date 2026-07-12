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
