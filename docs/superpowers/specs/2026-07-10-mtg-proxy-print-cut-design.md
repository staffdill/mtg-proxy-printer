# MTG Proxy Print-and-Cut Setup — Design Spec

**Date:** 2026-07-10
**Status:** Approved design, ready for implementation planning

## Goal

A repeatable, high-volume workflow to print Magic: The Gathering proxies on an
HP inkjet printer and cut them to size on a Cricut Explore Air 2. Target quality:
**"looks like a real card in a sleeve"** — sharp fronts, exact card size, authentic
rounded corners, consistent sizing. Proxies are always sleeved with a real card or
basic land behind them, so single-sided printing is sufficient and front/back
alignment is a non-issue.

## Hardware & materials

- **Printer:** HP inkjet (exact model TBD-at-build; affects max paper thickness only).
- **Cutter:** Cricut Explore Air 2 (optical Print Then Cut registration).
- **Paper:** Epson Presentation Paper Matte, 8.5 × 11 in, ~102 gsm. Bright white and
  matte — ideal for the Cricut's registration sensor. Thin, so it relies on a card
  behind it for rigidity and needs care on removal to avoid tearing.
- **Mat:** LightGrip (blue) preferred to avoid tearing thin paper.
- **Blade:** Fine-Point (Premium) blade.
- **Sleeves:** opaque-back sleeves; each proxy backed by a real card or land.

## Key constraints (design drivers)

1. **Registration is the hard part, not printing.** The Explore Air 2 only aligns
   cuts to a print via **Print Then Cut**, where the printer lays down registration
   marks that the Cricut's optical sensor reads. All alignment design flows from this.
2. **Print Then Cut caps throughput.** On the Explore Air 2 the usable Print Then Cut
   area is ~6.75 × 9.25 in, which fits **4 cards per Letter sheet**. This is a hard
   limit; a 60-card deck is ~15 print-and-cut cycles regardless of approach. We
   optimize **labor per sheet**, not cards per sheet.
3. **Matte, non-reflective, white paper** is required for reliable sensor reads.
   Glossy stock is avoided. (Our paper already satisfies this.)
4. **Scaling breaks registration.** Everything prints at 100% / actual size.

## Chosen approach: composite sheets + reusable cut template

Rejected alternatives:

- **Pure Design Space (all manual):** upload and place every card image by hand every
  sheet. Fine for a handful, unworkable at volume.
- **Print elsewhere, blind-cut on Cricut:** no sensor registration, so cuts drift and
  rounded corners won't sit correctly on the art. Fails the quality bar.

**Selected:** a small compositing script produces pre-arranged 4-up sheet images that
match a **build-once** Design Space cut template. Per sheet the user just loads the
next image behind the fixed cut grid and clicks Print Then Cut.

## Architecture / pipeline

```
Art selection (choose art per card):
   • Desktop MPC Autofill app  ← chosen: widest art choice + bleed baked into images
        │  (downloads chosen high-res card images, with bleed, to a local cache folder)
        ▼
   Folder of curated card images (with bleed)
        │
        ▼
[Compositing script]  ← geometry config (card size, positions, bleed, DPI)
   • reads the curated image folder
   • lays out 4 cards per Letter sheet at exact 63×88 mm, fixed positions
        │
        ▼
   sheet_01.png … sheet_NN.png
        │
        ▼
[Cricut Design Space]  ← reusable "4-up cut template" (built once)
   • drop next sheet image behind the locked rounded-rect cut grid
   • Print Then Cut
        │
        ├──► HP inkjet prints sheet + registration marks (matte paper, 100% scale)
        │
        ▼
[Cricut Explore Air 2] reads marks → cuts 4 rounded cards (inside the bleed)
        │
        ▼
   Sleeve each proxy with a real card/land behind it
```

**Single source of truth:** one geometry config defines card size, corner radius,
sheet size, DPI, and the 4 card positions. The script and the Design Space template
both derive from it, so prints and cuts inherently agree.

## Art selection via MPC Autofill

- The user picks the exact art/version per card in the **desktop MPC Autofill** app
  (community database includes full-art and custom proxies beyond official printings).
- MPC Autofill downloads the chosen images to a local cache folder as part of its
  normal flow. We **intercept that folder** and feed it to the compositing script;
  nothing is ordered from MakePlayingCards.
- **MPC-format images include bleed** (~3 mm of art past the 63 × 88 mm trim). This is
  a deliberate advantage: cutting at trim means the blade cuts *inside* printed art,
  so registration drift of a millimeter never exposes a white edge.

## Component 1 — Compositing script

- **Platform:** Python + Pillow, on Windows.
- **Input:** the MPC Autofill image cache folder. Optionally parse MPC Autofill's
  project/order file so card quantities and ordering match the decklist.
- **Geometry config (shared source of truth):**
  - Card trim: 63 × 88 mm; corner radius 3 mm.
  - Bleed: present in source images; place full-bleed image, cut at trim.
  - Sheet: US Letter, 300 DPI (2550 × 3300 px).
  - Layout: 2 × 2 = 4 cards/sheet, centered, ~4 mm gaps, inside the ~6.75 × 9.25 in
    Print Then Cut safe area.
- **Output:** `sheet_01.png … sheet_NN.png`, cards at fixed pixel coordinates matching
  the cut template. A partial final sheet fills from the top-left first so the template
  still lines up.

## Component 2 — Design Space "4-up" cut template

- **Built once:** insert 4 rounded rectangles (63 × 88 mm, 3 mm radius) at coordinates
  matching the script's card positions; group and lock; save as "MTG 4-up template."
- **Per sheet:** upload the next composite PNG as a Print Then Cut image, size/align to
  the fixed origin, send behind the locked cut grid, Print Then Cut.
- **Print dialog:** 100% / actual size, "fit to page" OFF, Best quality, matte paper,
  borderless OFF (marks need a white margin).

## Component 3 — Physical run-book

- **HP inkjet settings:** matte presentation paper type, Best/Max DPI, 100% scale,
  borderless OFF, dry flat 2–3 minutes.
- **Paper handling:** load flat, keep away from humidity to limit curl.
- **Mat:** LightGrip (blue); de-tack a StandardGrip on fabric if that is all available.
- **Blade:** clean, sharp Fine-Point.
- **Cricut material setting:** start from a light paper/copy-paper setting; test and
  adjust pressure; add multi-cut ×2 only if cuts are incomplete.
- **Removal:** peel the **mat away from the card** (flip mat face-down, roll it back);
  never lift the card off the mat.
- **Sleeving:** proxy plus a real card/land behind it, in opaque-back sleeves.

## Calibration & testing

- One-time: run Design Space's **Print Then Cut calibration** routine.
- First run: print one test sheet, then verify with calipers —
  - Card size 63 × 88 mm (±0.3 mm).
  - Corner radius ~3 mm.
  - Cut sits just inside the art on all sides (no white sliver).
  - No tearing on removal.
- Adjust template offset or scaling as needed. Once dialed in, positions are fixed and
  every subsequent batch is a pure repeat.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Cricut can't read registration marks | good black ink; matte paper (✓); even lighting, no glare/shadow; marks not cut off; mat loaded straight |
| White sliver on cut edge | rely on MPC bleed; inset cut ~0.3 mm; re-run Print Then Cut calibration |
| Paper curls → sensor fails | dry flat, gently back-roll, load flat |
| Card tears on removal | LightGrip mat + mat-off-card technique |
| Cut doesn't go all the way through | custom/"more" pressure, fresh blade, multi-cut ×2 |
| Colors dull vs screen | inherent to matte inkjet; acceptable when sleeved; nudge saturation if wanted |

## Deliverables

1. The Python compositing script plus its geometry config.
2. A written run-book/checklist for the physical print-and-cut cycle.
3. Design Space template setup steps, including the exact card coordinates in mm/inches.

## Open items to resolve during implementation

- Confirm the exact local folder/path where the current desktop MPC Autofill app caches
  downloaded card images, and whether to parse its project/order file for quantities.
- Confirm the HP printer model and its max paper thickness / best matte print settings.
- Confirm the precise Print Then Cut safe-area dimensions for the installed Design Space
  version, and finalize the 4 card coordinates from that.
```
