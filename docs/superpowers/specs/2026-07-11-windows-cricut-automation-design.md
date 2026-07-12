# Windows Cricut Automation — Design Spec

**Date:** 2026-07-11
**Status:** Approved design, ready for implementation planning
**Supersedes parts of:** `2026-07-10-mtg-proxy-print-cut-design.md` (drops the manual
Design Space cut template; see "Divergences from the 2026-07-10 spec")

## Goal

Run the full proxy pipeline on the Windows 11 desktop: generate 4-up sheets from MPC
Autofill card images, then drive Cricut Design Space through Print Then Cut for each
sheet — stopping at the Windows print dialog so a human clicks Print.

The existing `image-upload-workflow/upload_to_cricut.py` was written for macOS and
cannot run here. It shells out to `osascript` (AppleScript), uses `Cmd+Shift+G`
("Go to Folder"), compensates for Retina screenshot scaling, and matches against
screenshots of the *macOS* Design Space UI. All four assumptions are false on Windows.

## Verified environment

Established by inspection on 2026-07-11, not assumed:

| Fact | Value | Consequence |
|---|---|---|
| OS | Windows 11 Home 26200 | AppleScript path is dead; native dialogs are Win32 |
| Display | Single 5120×1440, 96 DPI (100%) | Retina `SCALE` divisor is a no-op (computes to 1.0) |
| Design Space | 9.76.91, Electron/Chromium | Auto-updates; UI templates are a maintenance surface |
| **Design Space UIA tree** | **Not exposed** | **In-app buttons can only be found by pixel matching** |
| Python | 3.13.12 on PATH | — |
| Installed deps | pillow, numpy, opencv-python-headless | Need to add `pywinauto` |
| Card images | `~/Downloads/card_images_2026-07-11` (84 imgs) | Aspect 0.734–0.735 ⇒ ~3 mm bleed present |

### The decisive finding

Probing the Design Space window through Windows UI Automation returns **3 descendants,
two of them opaque `Chrome Legacy Window` panes**. The entire application UI is invisible
to UIA. Electron exposes its accessibility tree only when launched with a flag we cannot
set on a packaged install, and querying it (which is what normally switches Chromium's
tree on) did not populate it.

Therefore: **in-app buttons must be located by pixel template matching. Native Windows
dialogs must not be.** That asymmetry is the central design decision.

## Scope

**In scope:** per sheet — upload, place on canvas, set exact size, Make It, confirm bleed
ON, Print Then Cut, halt at the print dialog. Then reset the canvas and repeat.

**Deliberately out of scope:** clicking **Print**, and pressing the Cricut's **Go**
button. Both consume physical materials and both remain manual. The riskiest surface in
the system is one we choose not to automate.

## Component 1 — Sheet generation (`mtgproxy`)

### Bug: `--sticker` mode mis-scales bleed images

`layout.rounded_card()` calls `resize_cover(img, trim_w, trim_h)`, squeezing the whole
69 × 94 mm bleed image into the 63 × 88 mm trim box. Measured against a real source
(`002 - Zack Fair.jpg`, 2213×3012): the card art renders at **11.053 px/mm against a
sheet of 11.811 px/mm — the card face is 6.4% too small**, with the bleed ring left
showing as a fake border. The sheet cuts to a correct 63 × 88 mm and still looks wrong.

**Fix:** render the source at the *bleed* box (63 + 2·bleed × 88 + 2·bleed mm — the scale
it was authored at), crop the bleed ring away to leave the true card face, then round the
corners. This mirrors what `composite_sheet()` already does correctly on the non-sticker
path. With `--bleed 0` the bleed box equals the trim box and the crop is a no-op, so the
`no bleed` folder (aspect 0.7158 = exactly 63/88) still works.

### Generation step

```
python -m mtgproxy.cli --input "C:\Users\Staff\Downloads\card_images_2026-07-11" \
                       --out .\sheets --sticker
```

84 cards → **21 sheets**, each 134 × 184 mm (**5.276 × 7.244 in**): four rounded cards on
a transparent background, inside the 6.75 × 9.25 in Print Then Cut area.

`--out .\sheets` matters: the uploader reads from `sheets/` while the CLI defaults to
`out/`. Today those disagree. The automation will take an explicit sheets path rather than
inherit that mismatch.

### Consequences of having no cut template

- **Design Space traces the transparency** to generate cut lines, so the cut lands on the
  true card edge. We rely on Design Space's own **bleed toggle** (Make It screen) to smear
  edge pixels outward past the cut line, so registration drift bites into ink rather than
  white paper. Bleed-ON is an asserted automation step, not a thing a human remembers.
- **Size must be set numerically.** Design Space ignores PNG DPI. The script sets width to
  **5.276 in** with aspect lock on; height follows. Error vs. the ±0.3 mm tolerance is
  ~0.01 mm.
- **The gap between cards now has a floor.** Design Space's bleed smears roughly 1/16 in
  (~1.6 mm) outward from every cut line, so adjacent cards need ≥ ~3.2 mm of separation or
  their bleeds collide. The current 8 mm default is comfortably clear, but `--gap` must not
  be lowered below ~4 mm. `GeometryConfig.__post_init__` already enforces
  `gap ≥ 2·bleed`; that check keeps its meaning for the non-sticker path and should gain a
  sticker-mode equivalent rather than being silently bypassed.

### Removal

Delete `template_coords.py` and `tests/test_template_coords.py`. They exist solely to emit
coordinates for the manual cut template we are no longer building.

## Component 2 — Cricut automation (`mtgproxy/cricut/`)

`image-upload-workflow/` is promoted to a package so it is importable and testable. Four
modules, split on the question *who drew these pixels*:

**`native.py` — Windows dialogs, via UI Automation (pywinauto).** Waits for the file-open
dialog, sets its "File name" edit to the absolute path, invokes Open. Detects the print
dialog's appearance. Real control handles: no guessing, no sleep-and-hope. This replaces
the entire AppleScript block — `_read_go_to_folder_field`, `_clear_go_to_folder_field`,
the warm-up keystroke, and the double-Enter all cease to exist.

**`screen.py` — Chromium pixels, via OpenCV template matching.** Screenshot capture, the
DPI scale factor (computed, not assumed — 1.0 here), `locate(template) → point`, click. On
a miss it writes a full screenshot to `debug/` named for the failed template, then
**raises**. "Not found" is never a return value a caller can ignore.

**`flow.py` — the per-sheet sequence, as data.** A list of step objects
(`name`, `template` | `native` action, `timeout`), not imperative code. A Cricut UI update
becomes a one-line edit plus a re-screenshot. The sequence:

```
Upload Image → Browse → [native: pick file] → Continue → Apply & Continue
  → Flat Graphic → Continue → Upload            (image is now in the library)
  → select the new image → Add to Canvas        (it does NOT land on the canvas by itself)
  → set width = 5.276 in, aspect lock on
  → Make It → enable the "bleed" toggle on the print preview → Send to Printer
  → [native: print dialog appears] → HALT
```

Note the two steps the macOS script never reached: an uploaded image lands in the
**library**, not on the canvas, so it must be explicitly selected and added; and the size
fields only exist once it is *on* the canvas.

**`run.py` — CLI and loop.** Enumerates sheets, runs each through `flow.py`, owns the gate
and the inter-sheet reset.

Two hard-won facts from the macOS version remain true on Windows and must be carried over:
"Flat Graphic" is **not** the default on the Convert Upload To screen (the default is
Multiple Layers, which is wrong for Print Then Cut); and a completed upload leaves the new
layer selected, which hides the Upload Image button behind an object-properties toolbar.

**New dependency:** `pywinauto`. `pyautogui`, `pillow`, `opencv-python-headless` are
already present (headless is fine — template matching needs no GUI).

## Component 3 — Gate, reset, and failure handling

**The gate.** After Print Then Cut, wait for the print dialog *by UIA* — an actual window
appearing, not a sleep — then print `Sheet N/21 ready. Print it, cut it, reload paper,
then press Enter.` and block on stdin.

**The inter-sheet reset.** The macOS script never faced this, because it stopped after
upload. After a print, Design Space sits on a post-print screen with sheet N still on the
canvas; starting sheet N+1 would stack images and corrupt every subsequent sheet. Each
cycle therefore ends by returning to a known-empty canvas: dismiss the post-print screen,
then `Escape` → `Ctrl+A` → `Delete`. **Invariant: exactly one image on the canvas at a
time**, asserted before the next sheet begins rather than assumed.

**Failing safely.** A wrong click here moves a blade, so three layers:

1. A template miss raises, dumps a `debug/` screenshot of the actual screen, and **halts
   the entire run** — never advancing to the next step or sheet. A half-recognized UI is
   exactly when blind clicking is most dangerous.
2. `pyautogui.FAILSAFE` on: mouse to a screen corner aborts instantly.
3. Preflight before sheet 1: Design Space running, restored (it was *minimized* when
   probed), foregrounded; sheets folder exists and is non-empty; every template file
   loads. Fail before touching anything, not halfway through sheet 7.

**Resumability.** `--start-at N` resumes mid-run. Without it, a bad match on sheet 18 means
reprinting seventeen good sheets.

**Known limitation, stated plainly:** template matching against an auto-updating Chromium
app is inherently brittle. The design's answer is that breakage is *loud, diagnosable, and
cheap to repair* — not that it won't happen.

## Component 4 — Testing and bring-up

Pure logic gets real tests. Live-UI automation cannot be meaningfully unit-tested, so it
gets a dry run instead of pretend coverage.

**Unit tests** (extending `tests/`, existing style):

- The bleed-crop fix: assert card art renders at 11.811 px/mm — the card *face* is
  63 × 88 mm, not a squeezed 69 × 94. A synthetic source with a known border makes this
  exact. This test would have caught the 6.4% bug.
- `--bleed 0` round-trips: bleed box equals trim box, crop is a no-op.
- Partial final sheet fills from the top-left (84 divides evenly by 4; 83 must not break).
- `flow.py`'s step list is well-formed: every referenced template file exists on disk. Turns
  "you forgot to screenshot a button" into a test failure, not a mid-run halt.

**Dry run.** `run.py --dry-run` walks the full step sequence and, at each step, *locates*
its template and reports found/not-found with match confidence — **clicking nothing**. A
human steps through Design Space; the script reports whether it can see each button. This
is how we validate the Windows templates before anything can misfire. Capturing those
templates is itself part of the work: every screenshot in `ui_templates/` is macOS and
unusable.

**Bring-up order.** Each step attempted only once the previous is clean:

1. Generate 21 sheets; **inspect `sheet_01.png` by eye** — face size, rounded corners,
   transparency. Free, and catches geometry errors before any paper is used.
2. Dry run until every step reports a confident match.
3. **One sheet live to the print gate — do not print.** Confirm the canvas image is
   5.276 in, bleed is ON, preview shows 4 cards plus registration marks.
4. **One sheet printed and cut.** Calipers: 63 × 88 mm ± 0.3 mm; ~3 mm corner radius; cut
   sits in ink with no white sliver. This is the real go/no-go.
5. Only then, the full 21-sheet run.

If step 4 shows drift, the fix is Design Space's **Print Then Cut calibration** routine — a
one-time machine procedure, not a code change. Worth knowing before hunting through Python
for a hardware problem.

## Divergences from the 2026-07-10 spec

| 2026-07-10 | Now | Why |
|---|---|---|
| Manual 4-up cut template in Design Space | None; transparency drives the cut | User decision: the Python script formats the pages |
| Real MPC bleed, cut *inside* the art | Cut at trim; Design Space's bleed toggle smears ink past the cut line | Follows from having no cut template; alpha boundary *is* the cut path |
| Automation stops after upload | Runs to the print dialog | User decision: full run with a printer gate |
| macOS / AppleScript | Windows / UIA + template matching | Target machine |

## Open items

- HP printer model and its best matte settings are still unconfirmed (affects the manual
  print step only, not the code).
- Whether Design Space's edge-smear bleed is visually acceptable at the "real card in a
  sleeve" bar. Resolved empirically at bring-up step 4, not by argument.
