# Runbook: First-time setup

Do this **once** on a machine before any deck runs.

## Prerequisites

- Windows PC that will run Design Space + automation
- Python 3.13+ recommended
- Design Space installed and signed in
- Hardware from [reference/hardware.md](../reference/hardware.md)

## 1. Install Python dependencies

From the repo root:

```bat
pip install -r requirements.txt
```

Includes Pillow, OpenCV, pyautogui/pywinauto, Flask (web UI), pytest.

## 2. Design Space Print Then Cut calibration

Run Design Space’s **Print Then Cut calibration** once for this machine + printer + paper type.

Wrong calibration shows up as registration miss or white edges — not as a Python error.

## 3. One-time printer preferences (HP)

Set defaults in Windows **Printing Preferences** (persistent), **not** inside a single print dialog:

```bat
rundll32 printui.dll,PrintUIEntry /e /n "HP6C5B66 (HP OfficeJet Pro 8710)"
```

(Adjust the printer name if yours differs — Settings → Printers.)

Recommended for this project:

- **Paper/Quality** → Paper type: **Other matte inkjet papers**, Quality: **Best**
- **Advanced** → **Print in Max DPI**

Dialog-only Preferences apply to **one job**. Deck runs would then require re-clicking driver tabs every sheet. Windows defaults let automation ignore the driver UI.

## 4. Design Space: leave “Use system dialog” OFF

If **Use system dialog** is on, the Windows print dialog covers Design Space’s Print Setup and hides **Add Bleed**. The automation refuses to print without confirming bleed — the run **halts**.

Correct: system dialog **off**; quality settings already set as Windows defaults.

## 5. Optional: web UI secrets

If you use the LAN catalog UI ([07-catalog-web-ui.md](07-catalog-web-ui.md)):

```bat
set MTGPROXY_WEB_PASSWORD=your-shared-password
set MTGPROXY_WEB_SECRET=long-random-string
```

Password is required. Secret should be stable across restarts or sessions reset.

## 6. Optional smoke tests

```bat
python -m pytest tests/ -q
```

Does not need hardware.

## Done

You are ready for:

- [01-full-mtg-deck.md](01-full-mtg-deck.md) — first full deck  
- [07-catalog-web-ui.md](07-catalog-web-ui.md) — browser catalog  

First physical success: verify dimensions with [hardware.md](../reference/hardware.md#first-run-verification-once).
