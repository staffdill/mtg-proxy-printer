from PIL import Image
from mtgproxy.geometry import (
    GeometryConfig,
    card_boxes,
    content_bbox_px,
    content_size_mm,
    sheet_size_px,
)
from mtgproxy.geometry import trim_bbox_px
from mtgproxy.layout import (
    resize_cover,
    composite_sheet,
    composite_sticker_sheet,
    rounded_card,
)


def test_resize_cover_exact_size_no_distortion():
    src = Image.new("RGB", (100, 100), "red")  # square source
    out = resize_cover(src, 60, 90)
    assert out.size == (60, 90)


def test_composite_places_cards_and_leaves_white_margin():
    cfg = GeometryConfig()
    imgs = [Image.new("RGB", (100, 140), "red") for _ in range(4)]
    sheet = composite_sheet(imgs, cfg)
    assert sheet.size == sheet_size_px(cfg)

    box0 = card_boxes(cfg)[0]
    # a point inside card 0's print box is red
    inside = (box0.print_x_px + 10, box0.print_y_px + 10)
    assert sheet.getpixel(inside) == (255, 0, 0)
    # top-left corner of the sheet is white margin
    assert sheet.getpixel((5, 5)) == (255, 255, 255)


def test_composite_partial_sheet_ok():
    cfg = GeometryConfig()
    sheet = composite_sheet([Image.new("RGB", (100, 140), "red")], cfg)
    assert sheet.size == sheet_size_px(cfg)
    # only card 0 filled; card 3 region stays white
    box3 = card_boxes(cfg)[3]
    assert sheet.getpixel((box3.print_x_px + 10, box3.print_y_px + 10)) == (255, 255, 255)


def test_composite_crop_trims_to_card_block():
    cfg = GeometryConfig()
    imgs = [Image.new("RGB", (100, 140), "red") for _ in range(4)]
    sheet = composite_sheet(imgs, cfg, crop=True)

    left, top, right, bottom = content_bbox_px(cfg)
    assert sheet.size == (right - left, bottom - top)
    # cropped size matches content_size_mm at the config DPI (within 1px rounding)
    w_mm, h_mm = content_size_mm(cfg)
    ppm = cfg.px_per_mm()
    assert abs(sheet.width - round(w_mm * ppm)) <= 1
    assert abs(sheet.height - round(h_mm * ppm)) <= 1
    # top-left corner is now printed card art (outer card's bleed), not white margin
    assert sheet.getpixel((2, 2)) == (255, 0, 0)


def test_sticker_sheet_transparent_with_rounded_cards():
    cfg = GeometryConfig()
    imgs = [Image.new("RGB", (100, 140), "red") for _ in range(4)]
    sheet = composite_sticker_sheet(imgs, cfg)

    # RGBA, cropped to the card-block (trim) bounds
    assert sheet.mode == "RGBA"
    left, top, right, bottom = trim_bbox_px(cfg)
    assert sheet.size == (right - left, bottom - top)

    # the very corner of card 1 is rounded away -> transparent
    assert sheet.getpixel((0, 0))[3] == 0
    # a point well inside card 1 is opaque red
    ppm = cfg.px_per_mm()
    inside = (round(20 * ppm), round(30 * ppm))  # 20mm,30mm into the first card
    px = sheet.getpixel(inside)
    assert px[3] == 255 and px[:3] == (255, 0, 0)


def test_rounded_card_crops_bleed_instead_of_shrinking_the_face():
    # A source authored the way MPC authors them: a bleed ring around the card
    # face. Card face RED, bleed ring BLUE, rendered at exactly 10 px/mm.
    # bleed_mm=6 (not the 3mm default) so the ring is thick enough that a
    # sampled point cannot land ambiguously on the boundary.
    cfg = GeometryConfig(bleed_mm=6.0, gap_mm=12.0)
    src = Image.new("RGB", (750, 1000), "blue")  # 75 x 100 mm at 10 px/mm
    src.paste(Image.new("RGB", (630, 880), "red"), (60, 60))  # the 63x88mm face

    out = rounded_card(src, cfg)

    ppm = cfg.px_per_mm()
    assert out.size == (round(cfg.card_w_mm * ppm), round(cfg.card_h_mm * ppm))

    # 2mm inside each edge midpoint must be the card FACE (red), not bleed (blue).
    # The bug renders the bleed ring inside the trim box, so these come out blue.
    inset = round(2 * ppm)
    w, h = out.size
    for point in [
        (inset, h // 2),          # left edge
        (w - inset - 1, h // 2),  # right edge
        (w // 2, inset),          # top edge
        (w // 2, h - inset - 1),  # bottom edge
    ]:
        r, g, b, a = out.getpixel(point)
        assert a == 255, f"{point} should be opaque"
        assert r > 200 and b < 55, f"{point} is bleed, not card face: {(r, g, b)}"


def test_rounded_card_with_zero_bleed_is_a_plain_trim_resize():
    # The "no bleed" folder: source art IS the card face, nothing to crop.
    cfg = GeometryConfig(bleed_mm=0.0, gap_mm=8.0)
    src = Image.new("RGB", (630, 880), "red")
    out = rounded_card(src, cfg)

    ppm = cfg.px_per_mm()
    assert out.size == (round(cfg.card_w_mm * ppm), round(cfg.card_h_mm * ppm))
    px = out.getpixel((out.width // 2, out.height // 2))
    assert px[3] == 255 and px[:3] == (255, 0, 0)
