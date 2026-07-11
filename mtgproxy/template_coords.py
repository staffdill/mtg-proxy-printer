from mtgproxy.geometry import (
    MM_PER_INCH,
    GeometryConfig,
    card_offsets_content_mm,
    content_size_mm,
)


def format_template_coords(cfg: GeometryConfig) -> str:
    card_w_in = cfg.card_w_mm / MM_PER_INCH
    card_h_in = cfg.card_h_mm / MM_PER_INCH
    radius_in = cfg.corner_radius_mm / MM_PER_INCH
    img_w_mm, img_h_mm = content_size_mm(cfg)
    img_w_in = img_w_mm / MM_PER_INCH
    img_h_in = img_h_mm / MM_PER_INCH

    lines = [
        "Cricut Design Space - 4-up cut template",
        "",
        f"1. Import a sheet PNG and set its size to EXACTLY "
        f"{img_w_mm:.0f} x {img_h_mm:.0f} mm ({img_w_in:.3f} x {img_h_in:.3f} in).",
        "   Design Space ignores the file's DPI, so you must set this by hand.",
        f"2. Add 4 rounded rectangles, each {cfg.card_w_mm:.0f} x {cfg.card_h_mm:.0f} mm "
        f"({card_w_in:.3f} x {card_h_in:.3f} in), "
        f"corner radius {cfg.corner_radius_mm:.0f} mm ({radius_in:.3f} in).",
        "3. Position each rectangle at the offset below, measured from the",
        "   top-left corner of the imported image (add the image's own X/Y).",
        "4. Group all four + the image, save as 'MTG 4-up template'.",
        "",
    ]
    for i, (x_mm, y_mm) in enumerate(card_offsets_content_mm(cfg), start=1):
        x_in = x_mm / MM_PER_INCH
        y_in = y_mm / MM_PER_INCH
        lines.append(
            f"Card {i}: x={x_mm:.2f} mm ({x_in:.3f} in), "
            f"y={y_mm:.2f} mm ({y_in:.3f} in)"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_template_coords(GeometryConfig()))
