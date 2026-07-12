# MTG Proxy Print-and-Cut Run-book (Windows)

Verified end to end on 2026-07-11: sheet 1 printed and cut correctly.

## Hardware

- **Printer:** HP OfficeJet Pro 8710 (network / WSD)
- **Cutter:** Cricut Explore Air 2
- **Paper:** Epson Presentation Paper Matte, 8.5 × 11 in. Matte and bright white — the
  Cricut's optical sensor needs that to read the registration marks.
- **Mat:** LightGrip (blue). **Blade:** clean Fine-Point.

**Do not laminate.** Laminate is glossy, and the Print Then Cut sensor cannot read
registration marks through a reflective surface. It is also far harder to cut than paper.
Sleeving each proxy with a real card behind it already gives the gloss and the rigidity.

## One-time setup

- `pip install -r requirements.txt`
- Run Design Space's **Print Then Cut calibration** once.
- **No cut template is needed.** The sheets are transparent PNGs and Design Space
  generates the cut lines from the transparency itself.

## 1. Generate the sheets

```
python -m mtgproxy.cli --input "<mpc-autofill-folder>" --out ./sheets --sticker
```

- 4 cards per sheet. MPC Autofill's `_not_in_list` subfolder is correctly ignored — only
  top-level images are used, so the sheet count reflects the actual decklist.
- Source images with no bleed: add `--bleed 0`.
- Exact quantities/order: `--manifest order.txt` (lines `filename.png,quantity`).

Each sheet is 134 × 184 mm = **5.276 × 7.244 in**. Note that number; Design Space ignores
the PNG's DPI and you must set the size by hand.

## 2. Upload the sheets to your Cricut library

Open Design Space, Canvas tab, empty canvas, then:

```
python -m mtgproxy.cricut.upload --sheets ./sheets
```

Do not touch the mouse or keyboard while it runs — it is driving the pointer. Move the
mouse into a screen corner to abort. If it halts, it prints the `--start-at N` to resume
from and leaves a screenshot in `debug/` showing what was actually on screen.

`--dry-run` locates every template and reports match confidence without clicking anything.

## 3. Print and cut, one sheet at a time

For each sheet, in Design Space:

1. Place the sheet on the canvas from your library.
2. **Set its width to 5.276 in** (aspect lock on — height follows to 7.248). It imports at
   about 10.98 in, which is outside the Print Then Cut area and raises a warning.
3. **Make** → on the Prepare screen, **set Material Size to Letter (8.5 × 11)**. It
   defaults to **A4**, which lays the registration marks out for the wrong page. Mirror off.
4. Continue → **Send to Printer**.
5. In the Print Setup dialog, confirm **Add Bleed is ON** and the printer has populated
   (it briefly shows "No printers found" while enumerating). Click **Print**.
6. Let the ink dry flat 2–3 minutes.
7. Set Base Material (start from a light paper setting), load the LightGrip mat, press Go.
8. Remove by peeling the **mat away from the card** — flip the mat face-down and roll it
   back. Never lift the card off the mat; this paper is thin and tears.
9. Sleeve each proxy with a real card or basic land behind it.

**Add Bleed makes the printed card look slightly larger than a real card on all edges.
That is correct** — the bleed is printed outside the cut line and the blade removes it.
Judge the size on a *cut* card, never on the printed sheet.

## First-run verification (do once, then trust it)

Measure a **cut** card with calipers:

- 63 × 88 mm (± 0.3 mm)
- corner radius ~3 mm
- the cut sits in ink, no white sliver
- no tearing on removal

If the size or registration is off, re-run Design Space's **Print Then Cut calibration**.
That is a machine procedure, not a code bug — don't go looking in the Python for it.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Upload script halts on a template it cannot see | Design Space auto-updated its UI, or its zoom changed. Look at the screenshot in `debug/`, re-crop that template, resume with `--start-at N`. |
| Cards printed slightly oversized | Expected before cutting — that's Add Bleed. Measure a cut card. |
| Cards genuinely oversized after cutting | The canvas width wasn't set to 5.276 in. |
| Cricut can't read registration marks | Matte paper only (no laminate, no gloss); good black ink; even lighting, no glare; marks not cut off; mat loaded straight. |
| White sliver on a cut edge | Add Bleed was OFF in Print Setup. Re-run Print Then Cut calibration. |
| Paper curls → sensor fails | Dry flat, gently back-roll, load flat. |
| Card tears on removal | LightGrip mat, and peel the mat away from the card. |
| Cut doesn't go all the way through | Custom / "more" pressure, fresh blade, multi-cut ×2. |
