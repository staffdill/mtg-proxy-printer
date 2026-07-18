import argparse
import sys
from pathlib import Path

from mtgproxy.batch import build_sheets, save_sheets
from mtgproxy.catalog import DEFAULT_DB_PATH, DEFAULT_IMAGES_DIR, Catalog
from mtgproxy.geometry import (
    MM_PER_INCH,
    GeometryConfig,
    content_size_mm,
    trim_content_size_mm,
    validate_sticker_gap,
)
from mtgproxy.sources import resolve_card_list


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Tile MTG card images into 4-up US-Letter print sheets."
    )
    parser.add_argument("--input", required=True, help="Folder of card images (with bleed).")
    parser.add_argument("--out", default="./out", help="Output folder for sheet PNGs.")
    parser.add_argument("--manifest", default=None, help="Optional filename,quantity manifest.")
    parser.add_argument("--bleed", type=float, default=3.0, help="Bleed mm per side.")
    parser.add_argument("--gap", type=float, default=8.0, help="Gap mm between cards.")
    parser.add_argument(
        "--full-sheet",
        action="store_true",
        help="Output the full 8.5x11 page instead of cropping to the card block. "
        "The cropped default is what fits Cricut Print Then Cut.",
    )
    parser.add_argument(
        "--sticker",
        action="store_true",
        help="Output transparent sheets with rounded cards so Design Space "
        "auto-creates the cut lines (no manual cut template needed).",
    )
    parser.add_argument(
        "--catalog-db", default=str(DEFAULT_DB_PATH), help="Card catalog database path."
    )
    parser.add_argument(
        "--catalog-images-dir",
        default=str(DEFAULT_IMAGES_DIR),
        help="Card catalog's owned image storage.",
    )
    args = parser.parse_args(argv)

    input_dir = Path(args.input)
    if not input_dir.is_dir():
        print(f"error: input folder not found: {input_dir}", file=sys.stderr)
        return 1

    manifest = Path(args.manifest) if args.manifest else None
    try:
        cfg = GeometryConfig(bleed_mm=args.bleed, gap_mm=args.gap)
        if args.sticker:
            validate_sticker_gap(cfg)
        card_paths = resolve_card_list(input_dir, manifest)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    crop = not args.full_sheet
    sheets = build_sheets(card_paths, cfg, crop=crop, sticker=args.sticker)
    written = save_sheets(sheets, Path(args.out), dpi=cfg.dpi)

    cat = Catalog(db_path=Path(args.catalog_db), images_dir=Path(args.catalog_images_dir))
    try:
        deck_name = Path(args.out).name
        n = cfg.cards_per_sheet
        for sheet_path, start in zip(written, range(0, len(card_paths), n)):
            chunk = card_paths[start : start + n]
            cat.catalog_sheet(chunk, deck_or_queue=deck_name, sheet_file=sheet_path.name)
    finally:
        cat.close()

    print(f"Wrote {len(written)} sheet(s) from {len(card_paths)} card(s) to {args.out}")
    if args.sticker:
        w_mm, h_mm = trim_content_size_mm(cfg)
        print(
            f"Sticker mode: upload as a Print Then Cut image (Design Space makes the "
            f"cut lines). Set each sheet to {w_mm / MM_PER_INCH:.3f} x "
            f"{h_mm / MM_PER_INCH:.3f} in ({w_mm:.0f} x {h_mm:.0f} mm)."
        )
    elif crop:
        w_mm, h_mm = content_size_mm(cfg)
        print(
            f"In Design Space, set each imported sheet to "
            f"{w_mm / MM_PER_INCH:.3f} x {h_mm / MM_PER_INCH:.3f} in "
            f"({w_mm:.0f} x {h_mm:.0f} mm) - Design Space ignores the file's DPI."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
