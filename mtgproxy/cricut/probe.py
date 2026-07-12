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
