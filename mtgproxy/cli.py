import argparse
from pathlib import Path

from mtgproxy.batch import build_sheets, save_sheets
from mtgproxy.geometry import GeometryConfig
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
    args = parser.parse_args(argv)

    cfg = GeometryConfig(bleed_mm=args.bleed, gap_mm=args.gap)
    manifest = Path(args.manifest) if args.manifest else None
    card_paths = resolve_card_list(Path(args.input), manifest)
    sheets = build_sheets(card_paths, cfg)
    written = save_sheets(sheets, Path(args.out))

    print(f"Wrote {len(written)} sheet(s) from {len(card_paths)} card(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
