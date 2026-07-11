from PIL import Image

from mtgproxy.geometry import GeometryConfig, card_boxes, sheet_size_px


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


def composite_sheet(images: list[Image.Image], cfg: GeometryConfig) -> Image.Image:
    canvas = Image.new("RGB", sheet_size_px(cfg), "white")
    for img, box in zip(images, card_boxes(cfg)):
        placed = resize_cover(img.convert("RGB"), box.print_w_px, box.print_h_px)
        canvas.paste(placed, (box.print_x_px, box.print_y_px))
    return canvas
