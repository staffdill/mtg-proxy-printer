# MTG Proxy Print-and-Cut Run-book

## One-time setup
- Install deps: `pip install -r requirements.txt`
- Cricut: run **Print Then Cut calibration** in Design Space.
- Build the cut template (see DESIGN_SPACE_TEMPLATE.md).
- Load LightGrip (blue) mat; install a clean Fine-Point blade.

## Each batch
1. In the desktop **MPC Autofill** app, choose the art per card; let it download images.
2. Point the script at the downloaded image folder:
   `python -m mtgproxy.cli --input "<mpc-autofill-image-folder>" --out ./out`
   - Optional exact quantities/order: add `--manifest order.txt`
     (lines `filename.png,quantity`).
   - Sheets are cropped to the card block (~5.512 × 7.480 in) so they fit Print Then Cut.
     The CLI prints the exact import size to use; add `--full-sheet` only if you want the
     old full 8.5×11 page.
3. For each `out/sheet_NN.png`: in Design Space open the template, upload the sheet as a
   Print Then Cut image, **set its size to 5.512 × 7.480 in** (Design Space ignores the
   file's DPI), align it under the cut grid, Make It → Print Then Cut.
   (See DESIGN_SPACE_TEMPLATE.md for exact positions.)
4. Print at **100% / actual size**, matte paper, Best quality; let ink dry flat 2-3 min.
5. Cut. Remove by peeling the **mat away from the card** (flip mat face-down, roll back).
6. Sleeve each proxy with a real card/land behind it (opaque-back sleeves).

## First-run verification (do once, then trust it)
- Print one test sheet; check with calipers:
  - Card size 63 × 88 mm (±0.3 mm)
  - Corner radius ~3 mm
  - Cut sits just inside the art on all sides (no white sliver)
  - No tearing on removal
- If off, adjust template offset / confirm 100% scaling, then re-test.

## Troubleshooting
| Symptom | Fix |
|---|---|
| Cricut can't read registration marks | good black ink; matte paper; even lighting, no glare/shadow; marks not cut off; mat loaded straight |
| White sliver on cut edge | rely on the 3 mm bleed; re-run Print Then Cut calibration; verify 100% scaling |
| Paper curls -> sensor fails | dry flat, gently back-roll, load flat |
| Card tears on removal | LightGrip mat + mat-off-card technique |
| Cut doesn't go all the way through | custom/"more" pressure, fresh blade, multi-cut x2 |
| Colors dull vs screen | inherent to matte inkjet; acceptable sleeved; nudge saturation if wanted |
