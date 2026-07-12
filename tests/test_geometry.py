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


def test_gap_smaller_than_double_bleed_raises():
    with pytest.raises(ValueError):
        GeometryConfig(bleed_mm=5.0, gap_mm=8.0)  # 8 < 2*5


def test_card0_geometry_values():
    box = card_boxes(GeometryConfig())[0]
    # centered content: left=(215.9-134)/2=40.95mm, top=(279.4-184)/2=47.7mm
    assert box.trim_x_mm == pytest.approx(40.95)
    assert box.trim_y_mm == pytest.approx(47.7)
    # print box = trim shifted out by 3mm bleed, size 69x94mm, at 300dpi
    assert (box.print_x_px, box.print_y_px) == (448, 528)
    assert (box.print_w_px, box.print_h_px) == (815, 1110)


from mtgproxy.geometry import DESIGN_SPACE_BLEED_MM, validate_sticker_gap


def test_validate_sticker_gap_rejects_gap_below_design_space_bleed():
    # bleed=0 slips past __post_init__'s gap >= 2*bleed check, but Design Space
    # still smears ~1.6mm outward from each cut line, so touching cards bleed
    # into each other.
    cfg = GeometryConfig(bleed_mm=0.0, gap_mm=2.0)
    with pytest.raises(ValueError, match="gap"):
        validate_sticker_gap(cfg)


def test_validate_sticker_gap_accepts_the_default_gap():
    validate_sticker_gap(GeometryConfig())  # 8mm gap, comfortably clear


def test_design_space_bleed_is_one_sixteenth_inch():
    assert abs(DESIGN_SPACE_BLEED_MM - 25.4 / 16) < 1e-9
