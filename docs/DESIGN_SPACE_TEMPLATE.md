# Cricut Design Space — Build the 4-up Cut Template (once)

The generated sheets are **cropped to the card block** (not a full 8.5×11 page),
so they fit inside Print Then Cut's printable area. Design Space adds its own
registration marks and page margins around your design.

> **Important:** Design Space ignores the DPI stored in the PNG and imports it at
> the wrong size. You must set the image size by hand every time (step 2 below).

## Build the template once

1. **New Project.** Machine: **Cricut Explore Air 2**. Material size: **US Letter**.
2. **Upload** a `sheet_NN.png` (flat / single-layer / **Print Then Cut image**), insert it,
   then set its size to **EXACTLY 140 × 190 mm (5.512 × 7.480 in)**.
   Note its position — the **X** and **Y** shown in the top toolbar (say `X0`, `Y0`).
3. **Insert 4 rounded rectangles**, each **63 × 88 mm (2.480 × 3.465 in)**, corner
   radius **3 mm (0.118 in)**.
4. Position each rectangle using the offsets below, **added to the image's own X/Y**
   (offsets are from the top-left corner of the imported image):

```
Card 1: x=3.00 mm (0.118 in), y=3.00 mm (0.118 in)
Card 2: x=74.00 mm (2.913 in), y=3.00 mm (0.118 in)
Card 3: x=3.00 mm (0.118 in), y=99.00 mm (3.898 in)
Card 4: x=74.00 mm (2.913 in), y=99.00 mm (3.898 in)
```

   **Worked example** — if you place the image at **X0 = 1.000 in, Y0 = 1.000 in**,
   set each rectangle's position (top toolbar X / Y) to:

```
Card 1: X = 1.118 in, Y = 1.118 in
Card 2: X = 3.913 in, Y = 1.118 in
Card 3: X = 1.118 in, Y = 4.898 in
Card 4: X = 3.913 in, Y = 4.898 in
```

5. Select all four rectangles **+** the image, **Group**, and **Save** as
   "MTG 4-up template".

Regenerate these numbers any time with: `python -m mtgproxy.template_coords`

## Per-sheet cycle

1. Open the saved template.
2. Delete the old sheet image; **Upload** the next `sheet_NN.png` as a **Print Then Cut
   image**, insert it, and set it to the **same size (5.512 × 7.480 in)** and the **same
   X/Y** as before. The four cut rectangles still line up (same geometry every sheet).
3. Confirm in the Layers panel: sheet image = **Print**, four rectangles = **Cut**.
4. **Make It → Print Then Cut.** In the system print dialog: **100% / actual size**,
   **"fit to page" OFF**, **borderless OFF**, **Best quality**, **matte paper**.
5. Load the printed sheet on the mat and cut.
