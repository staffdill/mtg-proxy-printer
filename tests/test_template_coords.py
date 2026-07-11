from mtgproxy.geometry import GeometryConfig
from mtgproxy.template_coords import format_template_coords


def test_format_includes_import_size_radius_and_all_cards():
    text = format_template_coords(GeometryConfig())
    # card size (mm and inches) and corner radius (mm and inches)
    assert "63 x 88 mm" in text
    assert "radius 3 mm" in text
    assert "2.480 x 3.465 in" in text  # 63mm/88mm in inches
    assert "0.118 in" in text
    # cropped import size the user must set in Design Space
    assert "140 x 190 mm" in text
    assert "5.512 x 7.480 in" in text
    # one line per card, numbered 1..4
    for n in range(1, 5):
        assert f"Card {n}:" in text
    # card offsets are measured from the image top-left (content-relative)
    assert "x=3.00 mm" in text  # card 1 = bleed offset
    assert "74.00 mm" in text   # card 2/4 x
    assert "99.00 mm" in text   # card 3/4 y
