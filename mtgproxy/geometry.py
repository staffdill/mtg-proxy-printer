from dataclasses import dataclass

MM_PER_INCH = 25.4


@dataclass(frozen=True)
class GeometryConfig:
    card_w_mm: float = 63.0
    card_h_mm: float = 88.0
    corner_radius_mm: float = 3.0
    bleed_mm: float = 3.0
    gap_mm: float = 8.0
    cols: int = 2
    rows: int = 2
    sheet_w_mm: float = 215.9  # US Letter 8.5 in
    sheet_h_mm: float = 279.4  # US Letter 11 in
    dpi: int = 300

    def __post_init__(self):
        if self.gap_mm < 2 * self.bleed_mm:
            raise ValueError(
                f"gap_mm ({self.gap_mm}) must be >= 2*bleed_mm ({2 * self.bleed_mm}) "
                "so adjacent card bleed does not overlap"
            )

    @property
    def cards_per_sheet(self) -> int:
        return self.cols * self.rows

    def px_per_mm(self) -> float:
        return self.dpi / MM_PER_INCH


@dataclass(frozen=True)
class CardBox:
    print_x_px: int
    print_y_px: int
    print_w_px: int
    print_h_px: int
    trim_x_mm: float
    trim_y_mm: float


def sheet_size_px(cfg: GeometryConfig) -> tuple[int, int]:
    ppm = cfg.px_per_mm()
    return (round(cfg.sheet_w_mm * ppm), round(cfg.sheet_h_mm * ppm))


def card_boxes(cfg: GeometryConfig) -> list[CardBox]:
    ppm = cfg.px_per_mm()
    content_w = cfg.cols * cfg.card_w_mm + (cfg.cols - 1) * cfg.gap_mm
    content_h = cfg.rows * cfg.card_h_mm + (cfg.rows - 1) * cfg.gap_mm
    left = (cfg.sheet_w_mm - content_w) / 2
    top = (cfg.sheet_h_mm - content_h) / 2

    boxes: list[CardBox] = []
    for r in range(cfg.rows):
        for c in range(cfg.cols):
            trim_x = left + c * (cfg.card_w_mm + cfg.gap_mm)
            trim_y = top + r * (cfg.card_h_mm + cfg.gap_mm)
            print_x_mm = trim_x - cfg.bleed_mm
            print_y_mm = trim_y - cfg.bleed_mm
            print_w_mm = cfg.card_w_mm + 2 * cfg.bleed_mm
            print_h_mm = cfg.card_h_mm + 2 * cfg.bleed_mm
            boxes.append(
                CardBox(
                    print_x_px=round(print_x_mm * ppm),
                    print_y_px=round(print_y_mm * ppm),
                    print_w_px=round(print_w_mm * ppm),
                    print_h_px=round(print_h_mm * ppm),
                    trim_x_mm=trim_x,
                    trim_y_mm=trim_y,
                )
            )
    return boxes


def content_bbox_px(cfg: GeometryConfig) -> tuple[int, int, int, int]:
    """Pixel bounding box (left, top, right, bottom) of the union of all print
    boxes — the card block with bleed, excluding the surrounding page margin."""
    boxes = card_boxes(cfg)
    left = min(b.print_x_px for b in boxes)
    top = min(b.print_y_px for b in boxes)
    right = max(b.print_x_px + b.print_w_px for b in boxes)
    bottom = max(b.print_y_px + b.print_h_px for b in boxes)
    return (left, top, right, bottom)


def content_size_mm(cfg: GeometryConfig) -> tuple[float, float]:
    """Width/height in mm of the card block with bleed (the cropped sheet size).
    This is the exact size the image must be set to in Cricut Design Space."""
    w = cfg.cols * cfg.card_w_mm + (cfg.cols - 1) * cfg.gap_mm + 2 * cfg.bleed_mm
    h = cfg.rows * cfg.card_h_mm + (cfg.rows - 1) * cfg.gap_mm + 2 * cfg.bleed_mm
    return (w, h)


def trim_bbox_px(cfg: GeometryConfig) -> tuple[int, int, int, int]:
    """Pixel bounding box (left, top, right, bottom) of the union of card TRIM
    boxes (no bleed) — used for sticker/auto-cut sheets where the card edge is
    the printed edge."""
    ppm = cfg.px_per_mm()
    boxes = card_boxes(cfg)
    left = min(round(b.trim_x_mm * ppm) for b in boxes)
    top = min(round(b.trim_y_mm * ppm) for b in boxes)
    right = max(round((b.trim_x_mm + cfg.card_w_mm) * ppm) for b in boxes)
    bottom = max(round((b.trim_y_mm + cfg.card_h_mm) * ppm) for b in boxes)
    return (left, top, right, bottom)


def trim_content_size_mm(cfg: GeometryConfig) -> tuple[float, float]:
    """Width/height in mm of the card block measured to the card edges (no bleed).
    This is the size a sticker/auto-cut sheet must be set to in Design Space."""
    w = cfg.cols * cfg.card_w_mm + (cfg.cols - 1) * cfg.gap_mm
    h = cfg.rows * cfg.card_h_mm + (cfg.rows - 1) * cfg.gap_mm
    return (w, h)


def card_offsets_content_mm(cfg: GeometryConfig) -> list[tuple[float, float]]:
    """Top-left of each card's trim box in mm, measured from the top-left of the
    cropped (content) image — the offsets for placing Design Space cut rectangles."""
    boxes = card_boxes(cfg)
    origin_x = min(b.trim_x_mm for b in boxes) - cfg.bleed_mm
    origin_y = min(b.trim_y_mm for b in boxes) - cfg.bleed_mm
    return [(b.trim_x_mm - origin_x, b.trim_y_mm - origin_y) for b in boxes]
