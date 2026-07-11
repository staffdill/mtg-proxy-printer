from pathlib import Path

from PIL import Image

from mtgproxy.geometry import GeometryConfig
from mtgproxy.layout import composite_sheet


def build_sheets(card_paths: list[Path], cfg: GeometryConfig) -> list[Image.Image]:
    n = cfg.cards_per_sheet
    sheets: list[Image.Image] = []
    for start in range(0, len(card_paths), n):
        chunk = card_paths[start : start + n]
        images = [Image.open(p) for p in chunk]
        sheets.append(composite_sheet(images, cfg))
    return sheets


def save_sheets(sheets: list[Image.Image], out_dir: Path, dpi=300, prefix="sheet") -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    width = len(str(len(sheets)))
    written: list[Path] = []
    for i, sheet in enumerate(sheets, start=1):
        path = out_dir / f"{prefix}_{str(i).zfill(width)}.png"
        sheet.save(path, "PNG", dpi=(dpi, dpi))
        written.append(path)
    return written
