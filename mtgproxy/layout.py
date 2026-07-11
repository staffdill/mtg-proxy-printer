from PIL import Image, ImageDraw

from mtgproxy.geometry import (
    GeometryConfig,
    card_boxes,
    content_bbox_px,
    sheet_size_px,
    trim_bbox_px,
)


def resize_cover(img: Image.Image, w_px: int, h_px: int) -> Image.Image:
    src_w, src_h = img.size
    scale = max(w_px / src_w, h_px / src_h)
    scaled = img.resize(
        (max(w_px, round(src_w * scale)), max(h_px, round(src_h * scale))),
        Image.LANCZOS,
    )
    left = (scaled.width - w_px) // 2
    top = (scaled.height - h_px) // 2
    return scaled.crop((left, top, left + w_px, top + h_px))


def composite_sheet(
    images: list[Image.Image], cfg: GeometryConfig, crop: bool = False
) -> Image.Image:
    canvas = Image.new("RGB", sheet_size_px(cfg), "white")
    for img, box in zip(images, card_boxes(cfg)):
        placed = resize_cover(img.convert("RGB"), box.print_w_px, box.print_h_px)
        canvas.paste(placed, (box.print_x_px, box.print_y_px))
    if crop:
        canvas = canvas.crop(content_bbox_px(cfg))
    return canvas


def rounded_card(img: Image.Image, cfg: GeometryConfig) -> Image.Image:
    """A single card sized to trim (63x88mm) with rounded corners cut out as
    transparency — an RGBA 'sticker' Design Space can auto-cut around."""
    ppm = cfg.px_per_mm()
    w = round(cfg.card_w_mm * ppm)
    h = round(cfg.card_h_mm * ppm)
    radius = round(cfg.corner_radius_mm * ppm)
    card = resize_cover(img.convert("RGB"), w, h).convert("RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    card.putalpha(mask)
    return card


def composite_sticker_sheet(
    images: list[Image.Image], cfg: GeometryConfig
) -> Image.Image:
    """Transparent-background sheet of rounded cards, cropped to the card block.
    Design Space treats each card as a sticker and creates the cut lines itself,
    so no separate cut template is needed."""
    ppm = cfg.px_per_mm()
    canvas = Image.new("RGBA", sheet_size_px(cfg), (255, 255, 255, 0))
    for img, box in zip(images, card_boxes(cfg)):
        card = rounded_card(img, cfg)
        canvas.alpha_composite(
            card, (round(box.trim_x_mm * ppm), round(box.trim_y_mm * ppm))
        )
    return canvas.crop(trim_bbox_px(cfg))
