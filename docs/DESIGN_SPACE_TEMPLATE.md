# Cricut Design Space — Two ways to cut

## Method A — Sticker mode (easy, recommended, no template)

Generate sheets with `--sticker`. Each card is drawn with rounded corners on a
transparent background, so Design Space makes the cut lines for you.

```
python -m mtgproxy.cli --input "<your images>" --out .\out --sticker
```

In Design Space:

1. Left toolbar → **Upload** → **Upload Image** → **Browse** → pick `sheet_01.png`.
2. Image type: **Complex** → **Continue**. Don't erase anything (the background is
   already transparent) → **Continue**.
3. Select upload type: **Print Then Cut image** → **Upload**.
4. Select the uploaded image → **Add to Canvas**.
5. Select it on the canvas. In the top toolbar, set **Size → W: 5.276 in**
   (height auto-fills to ~7.244 in). This makes each card 63 × 88 mm.
6. **Make It.** You'll see a cut line hugging each rounded card.
7. Follow the prompts: **Print** (your HP prints the 4 cards + registration marks —
   use **100% / actual size**, matte paper), then load the printed sheet in the
   Cricut and **Cut**.

That's the whole flow — no rectangles, no coordinates. Repeat step 1–7 per sheet.

---

## Method B — Manual cut template (only if Method A ever misbehaves)

Uses the default (non-sticker) sheets: a flat image plus four cut rectangles you
place once and reuse.

> Design Space ignores the PNG's DPI, so you must set the image size by hand.

1. **New Project.** Machine: **Cricut Explore Air 2**. Material size: **US Letter**.
2. **Upload** a default `sheet_NN.png` as a **Print Then Cut image**, add it, and set
   its size to **EXACTLY 140 × 190 mm (5.512 × 7.480 in)**. Note its **X**/**Y**.
3. **Insert 4 rounded rectangles**, each **63 × 88 mm (2.480 × 3.465 in)**, corner
   radius **3 mm (0.118 in)**.
4. Position each rectangle at the offset below, added to the image's own X/Y:

```
Card 1: x=3.00 mm (0.118 in), y=3.00 mm (0.118 in)
Card 2: x=74.00 mm (2.913 in), y=3.00 mm (0.118 in)
Card 3: x=3.00 mm (0.118 in), y=99.00 mm (3.898 in)
Card 4: x=74.00 mm (2.913 in), y=99.00 mm (3.898 in)
```

   Worked example with image placed at X=1.0, Y=1.0 in:
   Card 1 (1.118, 1.118), Card 2 (3.913, 1.118), Card 3 (1.118, 4.898), Card 4 (3.913, 4.898).

5. Select the four rectangles + image → **Group** → **Save** as "MTG 4-up template".
6. Per sheet: swap in the next image at the same size/position; Make It → Print Then Cut.

Regenerate these numbers any time with: `python -m mtgproxy.template_coords`
