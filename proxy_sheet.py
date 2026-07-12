#!/usr/bin/env python3
"""
proxy_sheet.py — Build Cricut Print-Then-Cut ready MTG proxy sheets.

Takes a folder of card images and outputs sheet PNGs with:
  - Exact MTG card dimensions (63 x 88 mm) at 300 DPI
  - Rounded corners (3 mm radius, matches real cards)
  - Transparent background, so Design Space auto-generates a
    separate cut path around each card
  - Layout constrained to the Print Then Cut printable area

Usage:
    python proxy_sheet.py ./cards/                # all images in folder
    python proxy_sheet.py ./cards/ -o ./sheets/   # custom output dir
    python proxy_sheet.py ./cards/ --ptc-w 8.05 --ptc-h 10.4   # larger PTC area
    python proxy_sheet.py ./cards/ --dpi 600      # sharper text, 4x file size

Upload each output PNG to Design Space as a Print Then Cut image.
The canvas is cropped to the exact card grid (Design Space trims
transparent margins anyway). On the canvas, set the sheet's WIDTH to
the value printed by this script (aspect lock ON) and every card
lands at exactly 2.48 x 3.46 in.
"""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

# ---- Card + sheet geometry -------------------------------------------------

MM_PER_IN = 25.4

CARD_W_MM = 63.0
CARD_H_MM = 88.0
CORNER_RADIUS_MM = 3.0          # real MTG corner radius ~2.5-3 mm

DEFAULT_DPI = 300               # use --dpi 600 for sharper text (4x file size)


class Geometry:
    """All pixel dimensions derived from DPI at runtime."""

    def __init__(self, dpi: int):
        self.dpi = dpi
        self.card_w = round(CARD_W_MM / MM_PER_IN * dpi)   # 744 @300, 1488 @600
        self.card_h = round(CARD_H_MM / MM_PER_IN * dpi)   # 1039 @300, 2079 @600
        self.radius = round(CORNER_RADIUS_MM / MM_PER_IN * dpi)
        self.gap = round(GAP_IN * dpi)

# Default Print Then Cut printable area (letter paper): 6.75 x 9.25 in.
# Explore 3 / Maker 3 on larger media can go bigger — see --ptc-w/--ptc-h.
DEFAULT_PTC_W_IN = 6.75
DEFAULT_PTC_H_IN = 9.25

GAP_IN = 0.15                   # spacing between cards; keeps cut paths distinct
ASPECT_TOLERANCE = 0.02         # warn if source image aspect is off by >2%

SUPPORTED = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    """Antialiased rounded-rectangle alpha mask (rendered 4x and downsampled)."""
    ss = 4
    big = Image.new("L", (size[0] * ss, size[1] * ss), 0)
    draw = ImageDraw.Draw(big)
    draw.rounded_rectangle(
        [0, 0, size[0] * ss - 1, size[1] * ss - 1],
        radius=radius * ss,
        fill=255,
    )
    return big.resize(size, Image.LANCZOS)


def prepare_card(path: Path, geo: Geometry) -> Image.Image:
    """Load, aspect-check, resize to exact card px, apply rounded corners."""
    img = Image.open(path).convert("RGBA")

    src_aspect = img.width / img.height
    target_aspect = geo.card_w / geo.card_h
    drift = abs(src_aspect - target_aspect) / target_aspect
    if drift > ASPECT_TOLERANCE:
        print(
            f"  ! {path.name}: aspect ratio {src_aspect:.3f} vs target "
            f"{target_aspect:.3f} ({drift * 100:.1f}% off) — image will be "
            f"stretched to fit. Fix the source if this matters."
        )

    if img.width < geo.card_w:
        print(
            f"  ! {path.name}: source is {img.width}px wide but target is "
            f"{geo.card_w}px — upscaling won't add detail. Consider a "
            f"higher-res source or a lower --dpi."
        )
    img = img.resize((geo.card_w, geo.card_h), Image.LANCZOS)
    img.putalpha(rounded_mask((geo.card_w, geo.card_h), geo.radius))
    return img


def build_sheets(card_paths: list[Path], out_dir: Path,
                 ptc_w_in: float, ptc_h_in: float, geo: Geometry) -> None:
    sheet_w = round(ptc_w_in * geo.dpi)
    sheet_h = round(ptc_h_in * geo.dpi)
    gap = geo.gap

    cols = max(1, (sheet_w + gap) // (geo.card_w + gap))
    rows = max(1, (sheet_h + gap) // (geo.card_h + gap))
    per_sheet = cols * rows

    # Design Space auto-crops transparent margins on upload, so the canvas
    # IS the card grid — no padding. What you upload is what you size.
    used_w = cols * geo.card_w + (cols - 1) * gap
    used_h = rows * geo.card_h + (rows - 1) * gap
    sheet_w, sheet_h = used_w, used_h
    off_x = off_y = 0

    canvas_w_in = used_w / geo.dpi
    canvas_h_in = used_h / geo.dpi

    print(
        f"PTC area {ptc_w_in} x {ptc_h_in} in @ {geo.dpi} DPI -> grid "
        f"{cols} x {rows} ({per_sheet} cards/sheet, "
        f"{sheet_w} x {sheet_h} px = "
        f"{canvas_w_in:.2f} x {canvas_h_in:.2f} in)"
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    sheet_num = 0
    for start in range(0, len(card_paths), per_sheet):
        batch = card_paths[start:start + per_sheet]
        sheet_num += 1
        sheet = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))

        for i, path in enumerate(batch):
            r, c = divmod(i, cols)
            x = off_x + c * (geo.card_w + gap)
            y = off_y + r * (geo.card_h + gap)
            card = prepare_card(path, geo)
            sheet.alpha_composite(card, (x, y))
            print(f"  + {path.name}")

        out_path = out_dir / f"proxy_sheet_{sheet_num:02d}.png"
        sheet.save(out_path, dpi=(geo.dpi, geo.dpi))
        print(f"  -> {out_path}  ({len(batch)} cards)")

    print(
        f"\nDone: {sheet_num} sheet(s).\n"
        f"In Design Space: upload as Print Then Cut, then set sheet WIDTH "
        f"to exactly {canvas_w_in:.2f} in (aspect lock ON; height should "
        f"read {canvas_h_in:.2f}). Cards will be 2.48 x 3.46 in each.\n"
        f"If the height reads anything else, the wrong file was uploaded."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Build Cricut PTC proxy sheets")
    ap.add_argument("input_dir", type=Path, help="folder of card images")
    ap.add_argument("-o", "--out", type=Path, default=Path("./sheets"))
    ap.add_argument("--ptc-w", type=float, default=DEFAULT_PTC_W_IN,
                    help="Print Then Cut printable width in inches")
    ap.add_argument("--ptc-h", type=float, default=DEFAULT_PTC_H_IN,
                    help="Print Then Cut printable height in inches")
    ap.add_argument("--dpi", type=int, default=DEFAULT_DPI,
                    help="output resolution (300 default, 600 for sharper text)")
    args = ap.parse_args()

    if not args.input_dir.is_dir():
        sys.exit(f"Not a directory: {args.input_dir}")

    cards = sorted(
        p for p in args.input_dir.iterdir() if p.suffix.lower() in SUPPORTED
    )
    if not cards:
        sys.exit(f"No images found in {args.input_dir} (looked for {SUPPORTED})")

    build_sheets(cards, args.out, args.ptc_w, args.ptc_h, Geometry(args.dpi))


if __name__ == "__main__":
    main()
