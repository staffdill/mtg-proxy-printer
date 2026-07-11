from mtgproxy.geometry import GeometryConfig
from mtgproxy.template_coords import format_template_coords


def test_format_includes_size_radius_and_all_cards():
    text = format_template_coords(GeometryConfig())
    assert "63 x 88 mm" in text
    assert "radius 3 mm" in text
    assert "2.480 x 3.465 in" in text  # 63mm/88mm in inches
    # Sheet size in inches
    assert "8.5 x 11.0 in" in text
    # Corner radius in inches
    assert "0.118 in" in text
    # one line per card, numbered 1..4
    for n in range(1, 5):
        assert f"Card {n}:" in text
    # card 1 trim origin in mm
    assert "40.95" in text
    assert "47.70" in text
    # card 4 trim y position in mm
    assert "143.70" in text
