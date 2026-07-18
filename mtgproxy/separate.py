"""Separate multi-card proxy sheets into individual card images.

Limitless One Piece (and similar tools) export a Letter PDF with a 3×3 grid of
cards per page. Cricut Print Then Cut needs each card as its own sticker with
transparent gaps, so this module extracts every card placement into a single
PNG that the existing ``mtgproxy.cli --sticker`` pipeline can tile.

Also accepts a multi-card sheet image (PNG/JPG) and splits it on a regular grid.

Usage:
    python -m mtgproxy.separate --input deck.pdf --out ./cards
    python -m mtgproxy.separate --input sheet.png --out ./cards --cols 3 --rows 3
    # then:
    python -m mtgproxy.cli --input ./cards --out ./sheets --sticker --bleed 0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
PDF_EXTS = {".pdf"}


def _pil_from_pixmap(pix) -> Image.Image:
    """Convert a PyMuPDF Pixmap to a Pillow image (RGB or RGBA)."""
    # CMYK / other exotic spaces → RGB first
    if pix.n - pix.alpha > 3:
        import fitz

        pix = fitz.Pixmap(fitz.csRGB, pix)
    mode = "RGBA" if pix.alpha else "RGB"
    return Image.frombytes(mode, (pix.width, pix.height), pix.samples)


def extract_cards_from_pdf(pdf_path: Path) -> list[Image.Image]:
    """Return one image per card *placement* in reading order (top→bottom, left→right).

    Limitless reuses the same XObject for duplicate copies of a card. We follow
    every placement so deck quantities are preserved.
    """
    try:
        import fitz
    except ImportError as e:
        raise ImportError(
            "pymupdf is required to read proxy PDFs. Install with: pip install pymupdf"
        ) from e

    doc = fitz.open(pdf_path)
    cards: list[Image.Image] = []
    cache: dict[int, Image.Image] = {}

    try:
        for page in doc:
            infos = page.get_image_info(xrefs=True)
            # Stable reading order: row (y) then column (x)
            infos = sorted(
                infos,
                key=lambda info: (
                    round(info["bbox"][1], 2),
                    round(info["bbox"][0], 2),
                ),
            )
            for info in infos:
                xref = info["xref"]
                if xref not in cache:
                    pix = fitz.Pixmap(doc, xref)
                    try:
                        cache[xref] = _pil_from_pixmap(pix)
                    finally:
                        pix = None
                # Fresh copy so callers can mutate without sharing pixels
                cards.append(cache[xref].copy())
    finally:
        doc.close()

    return cards


def split_grid_image(
    img: Image.Image,
    cols: int,
    rows: int,
    *,
    margin_px: int = 0,
    gap_px: int = 0,
) -> list[Image.Image]:
    """Slice a regular cols×rows card grid into individual images.

    ``margin_px`` is empty border around the whole grid; ``gap_px`` is the
    gutter between cards (same on both axes). Cards are assumed equal size.
    """
    if cols < 1 or rows < 1:
        raise ValueError(f"cols and rows must be >= 1 (got {cols}x{rows})")
    if margin_px < 0 or gap_px < 0:
        raise ValueError("margin_px and gap_px must be >= 0")

    w, h = img.size
    inner_w = w - 2 * margin_px - (cols - 1) * gap_px
    inner_h = h - 2 * margin_px - (rows - 1) * gap_px
    if inner_w <= 0 or inner_h <= 0:
        raise ValueError(
            f"margin/gap leave no room for cards on a {w}x{h} image "
            f"(margin={margin_px}, gap={gap_px}, grid={cols}x{rows})"
        )
    if inner_w % cols or inner_h % rows:
        # Allow 1px remainder by flooring; better than failing on off-by-one scans
        pass
    card_w = inner_w // cols
    card_h = inner_h // rows
    if card_w < 1 or card_h < 1:
        raise ValueError("computed card size is empty — check margin/gap/cols/rows")

    cards: list[Image.Image] = []
    for r in range(rows):
        for c in range(cols):
            left = margin_px + c * (card_w + gap_px)
            top = margin_px + r * (card_h + gap_px)
            box = (left, top, left + card_w, top + card_h)
            cards.append(img.crop(box))
    return cards


def detect_content_margin(img: Image.Image, threshold: int = 250) -> tuple[int, int, int, int]:
    """Tight bounding box of non-near-white content as (left, top, right, bottom).

    Useful before ``split_grid_image`` when a sheet has uneven page margins.
    """
    rgb = img.convert("RGB")
    # Downsample for speed on big sheets; scale coords back up
    scale = 1
    work = rgb
    if max(rgb.size) > 2000:
        scale = 4
        work = rgb.resize((rgb.width // scale, rgb.height // scale), Image.BOX)

    pixels = work.load()
    w, h = work.size
    left, top, right, bottom = w, h, 0, 0
    found = False
    for y in range(h):
        for x in range(w):
            r, g, b = pixels[x, y]
            if r < threshold or g < threshold or b < threshold:
                found = True
                if x < left:
                    left = x
                if y < top:
                    top = y
                if x > right:
                    right = x
                if y > bottom:
                    bottom = y
    if not found:
        return (0, 0, img.width, img.height)
    return (
        left * scale,
        top * scale,
        min(img.width, (right + 1) * scale),
        min(img.height, (bottom + 1) * scale),
    )


def split_grid_image_auto(
    img: Image.Image,
    cols: int,
    rows: int,
    *,
    gap_px: int = 0,
    threshold: int = 250,
) -> list[Image.Image]:
    """Crop to content, then split on a regular grid (no outer margin)."""
    left, top, right, bottom = detect_content_margin(img, threshold=threshold)
    cropped = img.crop((left, top, right, bottom))
    return split_grid_image(cropped, cols, rows, margin_px=0, gap_px=gap_px)


def save_cards(
    cards: list[Image.Image],
    out_dir: Path,
    *,
    prefix: str = "card",
    start: int = 1,
) -> list[Path]:
    """Write cards as ``prefix_001.png`` … Returns paths written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    width = max(3, len(str(start + len(cards) - 1)))
    written: list[Path] = []
    for i, card in enumerate(cards):
        n = start + i
        path = out_dir / f"{prefix}_{str(n).zfill(width)}.png"
        # Face-only proxies are fine as RGB; keep alpha if present
        to_save = card if card.mode in ("RGB", "RGBA") else card.convert("RGBA")
        to_save.save(path, "PNG")
        written.append(path)
    return written


def save_named_cards(cards: list[Image.Image], out_dir: Path, names: list[str]) -> list[Path]:
    """Write cards named after their real card name, in placement order.

    Duplicate placements of the same name (a card printed more than once in
    the deck) are disambiguated with a " (2)", " (3)"... suffix so each
    placement gets its own file. The catalog normalizes that suffix back off
    when it identifies the card -- all those placements are the same card.
    """
    if len(cards) != len(names):
        raise ValueError(
            f"{len(cards)} card(s) but {len(names)} manifest name(s) -- must match exactly"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    seen: dict[str, int] = {}
    written: list[Path] = []
    for card, name in zip(cards, names):
        seen[name] = seen.get(name, 0) + 1
        n = seen[name]
        filename = f"{name}.png" if n == 1 else f"{name} ({n}).png"
        path = out_dir / filename
        to_save = card if card.mode in ("RGB", "RGBA") else card.convert("RGBA")
        to_save.save(path, "PNG")
        written.append(path)
    return written


def _read_manifest_names(path: Path) -> list[str]:
    """Read a manifest file with one card name per line.

    Skips empty lines and lines starting with '#' (comments).
    Strips whitespace from each line.
    """
    names = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        names.append(line)
    return names


def separate_path(
    source: Path,
    out_dir: Path,
    *,
    cols: int = 3,
    rows: int = 3,
    gap_px: int = 0,
    margin_px: int = 0,
    auto_margin: bool = True,
    prefix: str = "card",
    names: list[str] | None = None,
) -> list[Path]:
    """Dispatch on file type and write individual cards to ``out_dir``."""
    suffix = source.suffix.lower()
    if suffix in PDF_EXTS:
        cards = extract_cards_from_pdf(source)
    elif suffix in IMAGE_EXTS:
        img = Image.open(source)
        if auto_margin and margin_px == 0:
            cards = split_grid_image_auto(img, cols, rows, gap_px=gap_px)
        else:
            cards = split_grid_image(
                img, cols, rows, margin_px=margin_px, gap_px=gap_px
            )
    else:
        raise ValueError(
            f"unsupported input type {suffix!r}; expected PDF or image "
            f"({', '.join(sorted(IMAGE_EXTS | PDF_EXTS))})"
        )
    if not cards:
        raise ValueError(f"no cards found in {source}")
    if names is not None:
        return save_named_cards(cards, out_dir, names)
    return save_cards(cards, out_dir, prefix=prefix)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Separate multi-card proxy PDFs/sheets into individual card images "
            "for Cricut Print Then Cut (feeds mtgproxy.cli --sticker)."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Proxy PDF (e.g. Limitless One Piece) or a multi-card sheet image.",
    )
    parser.add_argument(
        "--out",
        default="./cards-separated",
        help="Output folder for individual card PNGs (default: ./cards-separated).",
    )
    parser.add_argument(
        "--cols",
        type=int,
        default=3,
        help="Grid columns for sheet images (default: 3). Ignored for PDFs.",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=3,
        help="Grid rows for sheet images (default: 3). Ignored for PDFs.",
    )
    parser.add_argument(
        "--gap",
        type=int,
        default=0,
        dest="gap_px",
        help="Gutter between cards in pixels (sheet images only).",
    )
    parser.add_argument(
        "--margin",
        type=int,
        default=0,
        dest="margin_px",
        help="Outer margin in pixels (sheet images). 0 + auto-crop is the default.",
    )
    parser.add_argument(
        "--no-auto-margin",
        action="store_true",
        help="Do not auto-detect content bounds on sheet images.",
    )
    parser.add_argument(
        "--prefix",
        default="card",
        help="Filename prefix for output cards (default: card).",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Text file, one card name per line in placement order (top-to-bottom, "
        "left-to-right), used to name output files after real card names instead of "
        "card_NNN.png. Needed for the catalog to know what each card actually is.",
    )
    args = parser.parse_args(argv)

    source = Path(args.input)
    if not source.is_file():
        print(f"error: input file not found: {source}", file=sys.stderr)
        return 1

    names = None
    if args.manifest:
        manifest_path = Path(args.manifest)
        if not manifest_path.is_file():
            print(f"error: manifest not found: {manifest_path}", file=sys.stderr)
            return 1
        names = _read_manifest_names(manifest_path)

    try:
        written = separate_path(
            source,
            Path(args.out),
            cols=args.cols,
            rows=args.rows,
            gap_px=args.gap_px,
            margin_px=args.margin_px,
            auto_margin=not args.no_auto_margin,
            prefix=args.prefix,
            names=names,
        )
    except (ValueError, ImportError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"Wrote {len(written)} card(s) to {args.out}")
    print(
        "Next — build Cricut sticker sheets (One Piece / face-only art uses --bleed 0):\n"
        f"  python -m mtgproxy.cli --input {args.out} --out ./sheets "
        f"--sticker --bleed 0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
