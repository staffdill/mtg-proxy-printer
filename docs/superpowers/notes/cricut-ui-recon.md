# Cricut Design Space — Windows UI Reconnaissance

**Date:** 2026-07-11
**Design Space:** 9.76.91 (Electron/Chromium)
**Machine:** Windows 11, single 5120×1440 @ 96 DPI (100% scaling)
**Method:** drove the real UI end-to-end, one sheet, stopping at the print gate.

This supersedes the guesses in the 2026-07-11 plan. Several findings contradict it.
Every claim here was observed, not assumed.

## 1. Design Space exposes no UIA tree (confirmed)

`AutomationElement.FromHandle(ds_hwnd).FindAll(Descendants)` returns **3 elements**, two
of them opaque `Chrome Legacy Window` panes. The entire application UI is invisible to UI
Automation. In-app buttons must be located by pixel template matching. Confirmed, not
assumed.

Window: class `Chrome_WidgetWin_1`, title `Cricut Design Space  v9.76.91`.
It does **not** maximize to the full 5120 px width; it settled at 2059×1392. Template
matching scans the whole screen, so window position/size does not matter — but do not
hardcode coordinates.

## 2. The file-open dialog lives in a SEPARATE PROCESS

**This breaks the plan's `native.py`.**

| Property | Value |
|---|---|
| Class | `#32770` |
| Title | `Open` |
| Process | **pid 36568 — NOT Design Space's pid 29088** |

Because Electron spawns the dialog in a utility process, **`Desktop(backend="uia").windows()`
does not return it** — `dlg.exists()` is `False` even while the dialog is plainly on screen.
The plan's `wait_for_dialog()` would have hung until timeout on every single sheet.

**The fix:** find it by raw `EnumWindows` (ctypes), filter on class `#32770`, then attach
with `Desktop(backend="uia").window(handle=hwnd)`. Verified working.

### Controls (by automation_id — language-independent, prefer these over titles)

| Control | friendly_class | automation_id | Notes |
|---|---|---|---|
| File name box | `Edit` | **`1148`** | `set_edit_text()` then read back to verify |
| Open | **`SplitButton`** | **`1`** | **NOT a `Button`** |
| Cancel | `Button` | `2` | |

The plan used `child_window(title="Open", control_type="Button")`. There are **two** other
controls titled "Open" with `auto_id='DropDown'` (the split-button arrows), so that selector
would have matched a dropdown arrow, not the Open button. Address by `auto_id="1"` +
`control_type="SplitButton"`.

**Verified end-to-end:** set the path, read it back (exact match, no dropped keystrokes),
clicked Open, dialog closed. The entire macOS AppleScript apparatus — `_read_go_to_folder_field`,
`_clear_go_to_folder_field`, the warm-up keystroke, the double-Enter — is unnecessary.

## 3. The flow, as it actually is

```
Upload (left rail)
  → Upload Image
  → Browse
  → [native Open dialog — see §2]
  → preview screen                → Continue
  → Background Remover            → Apply & Continue     (transparency survives; nothing to remove)
  → Convert Upload To             → Flat Graphic, then Continue
  → Image Details (name prefilled)→ Upload
  → *** image lands ON THE CANVAS automatically ***
  → toolbar "Size" → set W = 5.276 in (aspect lock is ON by default; H follows)
  → Make (top-right)
  → Prepare screen → *** set Material Size to Letter *** → Continue
  → Make screen (4 steps) → Send to Printer
  → Print Setup modal  ← THE GATE
```

### Divergences from the plan

**(a) There is no "Add to Canvas" step.** The plan assumed the macOS behavior: image lands
in the library, then you select it and add it. On Windows 9.76.91, **Upload places the image
directly on the canvas**, selected, with the Layers panel showing `sheet_01 / Print Then Cut`.
The plan's `08_library_first_image.png` and `09_add_to_canvas_btn.png` steps must be deleted.

**(b) "Multiple Layers" is preselected on Convert Upload To** — the macOS trap is real here
too. Flat Graphic must be clicked explicitly, or the sheet converts wrong for Print Then Cut.

**(c) Material Size defaults to A4 (8.3 × 11.7 in).** Our paper is Letter (8.5 × 11).
Left unchanged, registration marks are laid out for the wrong page. **The automation must set
this every run.** Dropdown options: A4 / Letter / Legal / Tabloid / A3. Mirror defaults Off
(correct).

**(d) The image imports at ~10.98 × 15.08 in** — far outside the Print Then Cut area, which
raises a red warning badge on the layer. Setting W = 5.276 in clears it. Aspect lock is on by
default, so H follows automatically (lands at 7.248 in; ideal is 7.244, i.e. 0.1 mm over
184 mm — inside the ±0.3 mm tolerance, and cards land within ~0.02 mm of 63 × 88).

## 4. The gate is the Print Setup modal, NOT a native print dialog

**This also breaks the plan.** The Print Setup modal has a **"Use System Dialog"** toggle,
and it is **OFF by default**. With it off, clicking Print sends **straight to the printer** —
no Windows print dialog ever appears. The plan's `wait_for_print_dialog()` would have waited
120 s for a window that never comes, and worse, the sheet could print unattended.

**The gate is therefore the Print Setup modal itself.** The script drives up to it and stops;
the human reviews and clicks Print. This is strictly better than the plan: nothing past this
modal is automated, and the human sees the actual preview before committing paper.

### Print Setup modal contents (all verified on screen)

| Field | Observed |
|---|---|
| Preview | 4 cards **with registration marks** (corner brackets) |
| Page Size | 8.5 × 11 in (Letter) — follows the Prepare screen |
| Printer | `HP6C5B66 (HP OfficeJet Pro 8710)` |
| Copies | 1 |
| **Add Bleed** | **ON by default (green)** — still assert it; do not assume |
| Use System Dialog | OFF |
| Print | green button — **the script must never click this** |

**Printer enumeration is slow.** The modal first showed **"No printers found"** plus a native
`#32770` "Waiting for printer connection…" dialog, then resolved to the HP a few seconds later
on its own. The automation must **wait for the printer dropdown to populate** before handing
over to the human, or the gate could present an unprintable modal.

## 5. Hardware

**Printer: HP OfficeJet Pro 8710** (WSD network port, `PrinterStatus: Normal`). This closes
the design spec's open item. Windows sees it fine; the transient "No printers found" is
Design Space's own enumeration lag, not a printer fault.

## 6. Consequences for the implementation

- `native.py` — find dialogs by `EnumWindows` handle, not desktop enumeration. Address the
  file dialog by `auto_id` (`1148` / `1`). **Delete `wait_for_print_dialog()`** — no such
  dialog exists in this flow.
- `flow.py` — delete the "select image in library" and "Add to Canvas" steps. **Add** a
  "set Material Size to Letter" step on the Prepare screen. The gate becomes "wait for the
  Print Setup modal, with the printer populated and Add Bleed on, then hand to the human".
- Templates needed (revised): upload rail tab, Upload Image, Browse, Continue (preview),
  Apply & Continue, Flat Graphic, Continue (convert), Upload, Size, W field, Make,
  Material Size dropdown, Letter option, Continue (prepare), Send to Printer,
  Add Bleed (on/off), the Print Setup modal itself.
