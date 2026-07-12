"""
Deterministic, template-matched upload of proxy sheets into Cricut Design
Space's "Upload Image" -> Print Then Cut flow.

Requires: pip install pyautogui opencv-python pillow

Usage:
    python3 upload_to_cricut.py

Bring Cricut Design Space to the foreground with a project open on the
Canvas tab before running. Move the mouse to a screen corner at any time
to abort (pyautogui fail-safe).
"""
import os
import subprocess
import time
import pyautogui

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Adjust confidence if matching is too strict (misses) or too loose (false hits)
CONFIDENCE_LEVEL = 0.8
IMAGE_DIR = os.path.join(SCRIPT_DIR, "ui_templates")
UPLOAD_FOLDER = os.path.join(SCRIPT_DIR, "..", "sheets")

SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".svg")

# On Retina displays, pyautogui.locateOnScreen() returns coordinates in
# physical screenshot pixels (e.g. 3584x2240), but moveTo()/click() expect
# logical points (e.g. 1792x1120) -- half that. Without this conversion,
# every click lands ~2x too far from the top-left corner and silently
# misses its target.
_shot_w, _ = pyautogui.screenshot().size
_screen_w, _ = pyautogui.size()
SCALE = _shot_w / _screen_w


def wait_and_click(template_name, timeout=10, post_click_delay=1.0):
    """Scans the screen for a UI element and clicks it when found."""
    template_path = os.path.join(IMAGE_DIR, template_name)
    start_time = time.time()

    print(f"  Looking for {template_name}...")
    while time.time() - start_time < timeout:
        try:
            location = pyautogui.locateCenterOnScreen(
                template_path, confidence=CONFIDENCE_LEVEL
            )
        except pyautogui.ImageNotFoundException:
            location = None

        if location:
            pyautogui.moveTo(location.x / SCALE, location.y / SCALE, duration=0.2)
            pyautogui.click()
            time.sleep(post_click_delay)
            return True

        time.sleep(0.5)

    print(f"  Timed out waiting for {template_name}")
    return False


def _read_go_to_folder_field():
    """Reads back the "Go to Folder" sheet's text field via Accessibility.
    Used to catch cases where pyautogui.write() starts typing before the
    sheet's slide-in animation has finished, which silently drops the
    first keystroke or two (e.g. "/Users/..." becomes "/ers/...")."""
    script = (
        'tell application "System Events" to tell process "Cricut Design Space" '
        'to return value of text field 1 of sheet 1 of sheet 1 of window 1'
    )
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return result.stdout.strip()


def _clear_go_to_folder_field():
    subprocess.run(
        [
            "osascript",
            "-e", 'tell application "System Events"',
            "-e", 'tell process "Cricut Design Space"',
            "-e", 'keystroke "a" using command down',
            "-e", 'key code 51',  # delete
            "-e", 'end tell',
            "-e", 'end tell',
        ],
        capture_output=True, text=True,
    )


def select_file_in_open_dialog(file_path, max_attempts=5):
    """Uses Cmd+Shift+G ('Go to folder') to jump straight to an absolute
    path in the macOS Open panel, instead of visually hunting for a
    specific thumbnail (which is unreliable when every sheet's preview
    looks like a similar card grid).

    Verifies what actually landed in the field before confirming. Something
    in the sheet's animation/focus handling reliably swallows the first
    keystroke or two of the *next* real input after any focus change --
    seen both right after the sheet slides in and again right after
    clearing the field for a retry. A throwaway "warm-up" keystroke before
    each real write() absorbs that loss instead of the real path.

    Returns False (instead of pressing Enter on a garbage path) if the
    field still doesn't match after every attempt, so the caller can abort
    the sheet cleanly rather than waste minutes stuck in a broken dialog.
    """
    abs_path = os.path.abspath(file_path)
    time.sleep(1.0)  # let the system Open panel finish appearing
    pyautogui.hotkey("command", "shift", "g")
    time.sleep(1.0)  # let the "Go to folder" sheet finish sliding in

    verified = False
    for attempt in range(max_attempts):
        pyautogui.write("x", interval=0.05)  # warm-up: absorbs the dropped keystroke
        time.sleep(0.2)
        _clear_go_to_folder_field()
        time.sleep(0.2)
        pyautogui.write(abs_path, interval=0.05)
        time.sleep(0.3)
        if _read_go_to_folder_field() == abs_path:
            verified = True
            break
        print(f"  ! Go to folder field mismatch on attempt {attempt + 1}, retrying...")

    if not verified:
        print("  ! Could not get the correct path into the Go to Folder field")
        return False

    pyautogui.press("enter")  # dismiss "Go to folder", select the file
    time.sleep(0.7)
    pyautogui.press("enter")  # activate the Open panel's default Open button
    time.sleep(0.7)
    # A single Enter here is unreliable -- the Open button can still be
    # settling into its enabled/default state right after the file gets
    # selected, so the keypress lands before it's actually wired up. A
    # second press a beat later reliably closes the dialog when the first
    # one didn't land; it's a no-op if the dialog already closed.
    pyautogui.press("enter")
    return True


def ensure_upload_panel_open():
    """After a successful upload, Design Space (a) leaves the new layer
    selected on canvas, which shows an object-properties toolbar instead of
    the left panel regardless of which rail tab is active, and (b)
    auto-switches the rail to the Images tab. Both hide the Upload Image
    button. Deselect first, then only click the Upload rail tab if the
    button isn't already visible: the tab icon template matches both its
    active and inactive styling (color is discarded during grayscale
    matching), so clicking an already-open tab would toggle it *closed*.
    """
    pyautogui.press("escape")
    time.sleep(0.3)
    template_path = os.path.join(IMAGE_DIR, "01_upload_image_btn.png")
    try:
        already_visible = pyautogui.locateOnScreen(template_path, confidence=CONFIDENCE_LEVEL)
    except pyautogui.ImageNotFoundException:
        already_visible = None
    if not already_visible:
        wait_and_click("00_upload_tab.png", timeout=5, post_click_delay=0.5)


def upload_sheet_to_cricut(file_path):
    """Executes the deterministic click sequence for a single sheet."""
    name = os.path.basename(file_path)
    print(f"\nStarting upload for: {name}")

    # 0. Make sure the Upload Image button is actually reachable before
    #    hunting for it (see ensure_upload_panel_open for why this is
    #    needed after the first sheet).
    ensure_upload_panel_open()

    # 1. Click the main "Upload Image" button on the Canvas left rail
    if not wait_and_click("01_upload_image_btn.png"):
        return False

    # 2. Click "Browse" to open the system file dialog
    if not wait_and_click("02_browse_btn.png"):
        return False

    # 3. Pick the file via absolute path instead of clicking a thumbnail
    if not select_file_in_open_dialog(file_path):
        return False

    # 4. Image preview loads -> click "Continue" (large sheets can take a
    #    while to render a first preview, hence the generous timeout)
    if not wait_and_click("04_continue_btn.png", timeout=45):
        return False

    # 5. Background Remover screen -> skip removal, "Apply & Continue"
    #    (proxy sheets are already fully rendered, nothing to remove).
    #    Button stays disabled/greyed (won't template-match) until the
    #    full-res preview finishes rendering, which is slow for large sheets.
    if not wait_and_click("05_apply_continue_btn.png", timeout=60):
        return False

    # 6. "Convert Upload To" screen defaults to "Multiple Layers", NOT Flat
    #    Graphic -- must select it explicitly, or every sheet gets converted
    #    wrong for Print Then Cut.
    if not wait_and_click("06a_flat_graphic_option.png", timeout=15):
        return False
    if not wait_and_click("06_continue_btn.png"):
        return False

    # 7. Image Details screen (name is pre-filled from the filename) ->
    #    click "Upload" to save it to the library
    if not wait_and_click("07_upload_btn.png", timeout=30):
        return False

    print(f"Upload successful: {name}")
    return True


def main():
    pyautogui.FAILSAFE = True

    print("Bring Cricut Design Space to the foreground. Starting in 5 seconds...")
    time.sleep(5)

    sheets = sorted(
        os.path.join(UPLOAD_FOLDER, f)
        for f in os.listdir(UPLOAD_FOLDER)
        if f.lower().endswith(SUPPORTED_EXTENSIONS)
    )

    if not sheets:
        print(f"No sheet images found in {UPLOAD_FOLDER}")
        return

    for sheet_path in sheets:
        success = upload_sheet_to_cricut(sheet_path)
        if not success:
            print("Automation broken or UI changed. Pausing script.")
            break
        time.sleep(2.0)  # cool-down between uploads to let Cricut cloud-sync


if __name__ == "__main__":
    main()
