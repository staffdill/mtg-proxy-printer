"""Driving the native Windows dialogs Design Space opens, via UI Automation.

These are real Win32 windows with real control handles, unlike Design Space's own
Chromium UI (see screen.py), so we address controls directly instead of matching
pixels. This is what replaces the macOS version's AppleScript "Go to Folder"
dance: no typing races, no warm-up keystrokes, no double-Enter, no reading the
field back to find out what actually landed in it.

Two facts about this dialog were established by driving the real UI (see
docs/superpowers/notes/cricut-ui-recon.md), and both are load-bearing:

1. Electron spawns the file dialog in a SEPARATE PROCESS, and
   `Desktop(backend="uia").windows()` does not return it — `exists()` reports
   False while the dialog is plainly on screen. It has to be found by raw
   EnumWindows and attached to by handle.
2. Its Open control is a SplitButton, not a Button. Two other controls are also
   titled "Open" (the split-button dropdown arrows), so selecting by title picks
   the wrong one. Address it by automation_id instead, which is also immune to
   the display language.
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from pathlib import Path

from pywinauto import Desktop

DIALOG_CLASS = "#32770"
DESIGN_SPACE_TITLE = "Cricut Design Space"

#: Win32 common-dialog control ids. Stable across Windows versions and languages.
FILE_NAME_EDIT_ID = "1148"
OPEN_BUTTON_ID = "1"

_user32 = ctypes.windll.user32
_EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class DialogNotFound(RuntimeError):
    """A native dialog did not appear in time. Always fatal — never fall through
    to clicking blind."""


class DesignSpaceNotFocused(RuntimeError):
    """Design Space is not the foreground window.

    Fatal before any keystroke, because keystrokes go wherever the focus is. The
    canvas is cleared with Ctrl+A then Delete; sent to the wrong window that
    selects and destroys somebody else's work.
    """


def _window_text(hwnd: int) -> str:
    n = _user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    _user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def require_design_space_foreground() -> tuple[int, int, int, int]:
    """Rect (left, top, right, bottom) of Design Space — but only if it is the
    foreground window. Raises otherwise.

    Call this before sending a keystroke that destroys something. It is the only
    thing standing between a mis-aimed Ctrl+A/Delete and whatever application
    happens to have focus instead.
    """
    hwnd = _user32.GetForegroundWindow()
    title = _window_text(hwnd)
    if DESIGN_SPACE_TITLE not in title:
        raise DesignSpaceNotFocused(
            f"foreground window is {title!r}, not Design Space — refusing to send "
            "keystrokes that would land in it"
        )
    rect = _RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.left, rect.top, rect.right, rect.bottom)


def find_dialog(title: str = "Open") -> int | None:
    """Handle of a visible top-level #32770 dialog with this exact title, or None.

    Uses raw EnumWindows rather than pywinauto's desktop enumeration, which
    cannot see dialogs owned by Electron's separate dialog process.
    """
    found: list[int] = []

    def callback(hwnd, _lparam):
        if _user32.IsWindowVisible(hwnd) and _class_name(hwnd) == DIALOG_CLASS:
            if _window_text(hwnd) == title:
                found.append(hwnd)
        return True

    _user32.EnumWindows(_EnumWindowsProc(callback), 0)
    return found[0] if found else None


def wait_for_dialog(title: str = "Open", timeout: float = 30.0):
    """Block until the dialog appears, then return it wrapped for UI Automation."""
    deadline = time.time() + timeout
    while True:
        hwnd = find_dialog(title)
        if hwnd is not None:
            return Desktop(backend="uia").window(handle=hwnd)
        if time.time() >= deadline:
            raise DialogNotFound(f"no {title!r} dialog appeared within {timeout}s")
        time.sleep(0.3)


def choose_file(path: Path, timeout: float = 30.0) -> None:
    """Put an absolute path into the file dialog's File name box and confirm it.

    The path is set directly rather than typed, so — unlike the macOS version —
    there is no keystroke to drop and nothing to retry. We still read the field
    back before confirming, because pressing Open on a half-written path would
    dump us into a broken dialog rather than fail cleanly.
    """
    target = str(Path(path).resolve())
    dialog = wait_for_dialog("Open", timeout=timeout)

    edit = dialog.child_window(auto_id=FILE_NAME_EDIT_ID, control_type="Edit")
    edit.wait("exists enabled visible ready", timeout=10)
    edit.set_edit_text(target)
    time.sleep(0.2)

    landed = edit.get_value()
    if landed != target:
        raise DialogNotFound(
            f"file name box holds {landed!r}, expected {target!r} — refusing to open it"
        )

    dialog.child_window(auto_id=OPEN_BUTTON_ID, control_type="SplitButton").click_input()

    deadline = time.time() + timeout
    while find_dialog("Open") is not None:
        if time.time() >= deadline:
            raise DialogNotFound("the Open dialog did not close after clicking Open")
        time.sleep(0.2)
