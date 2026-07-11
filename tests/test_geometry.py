import pytest
from mtgproxy.geometry import GeometryConfig, sheet_size_px, card_boxes


def test_cards_per_sheet_is_four():
    assert GeometryConfig().cards_per_sheet == 4


def test_sheet_size_px_is_letter_at_300dpi():
    assert sheet_size_px(GeometryConfig()) == (2550, 3300)


def test_card_boxes_count_and_order():
    boxes = card_boxes(GeometryConfig())
    assert len(boxes) == 4
    # row-major: card 0 top-left, card 1 to its right, card 2 below card 0
    assert boxes[1].trim_x_mm > boxes[0].trim_x_mm
    assert boxes[1].trim_y_mm == pytest.approx(boxes[0].trim_y_mm)
    assert boxes[2].trim_y_mm > boxes[0].trim_y_mm
    assert boxes[2].trim_x_mm == pytest.approx(boxes[0].trim_x_mm)


def test_card0_geometry_values():
    box = card_boxes(GeometryConfig())[0]
    # centered content: left=(215.9-134)/2=40.95mm, top=(279.4-184)/2=47.7mm
    assert box.trim_x_mm == pytest.approx(40.95)
    assert box.trim_y_mm == pytest.approx(47.7)
    # print box = trim shifted out by 3mm bleed, size 69x94mm, at 300dpi
    assert (box.print_x_px, box.print_y_px) == (448, 528)
    assert (box.print_w_px, box.print_h_px) == (815, 1110)
