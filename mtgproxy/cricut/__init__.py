"""Driving Cricut Design Space on Windows.

Design Space is Electron/Chromium and exposes no UI Automation tree — probing
its window returns only opaque "Chrome Legacy Window" panes — so its own
buttons can only be found by matching pixels (screen.py). The native Windows
dialogs it opens DO expose real control handles, and are driven through UI
Automation (native.py). That split is the whole design; do not cross it.
"""
