from PIL import Image
from mtgproxy.geometry import GeometryConfig, sheet_size_px, card_boxes
from mtgproxy.layout import resize_cover, composite_sheet


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
