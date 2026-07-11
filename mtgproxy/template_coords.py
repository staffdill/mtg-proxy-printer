from mtgproxy.geometry import GeometryConfig, MM_PER_INCH, card_boxes


def format_template_coords(cfg: GeometryConfig) -> str:
    w_in = cfg.card_w_mm / MM_PER_INCH
    h_in = cfg.card_h_mm / MM_PER_INCH
    sheet_w_in = cfg.sheet_w_mm / MM_PER_INCH
    sheet_h_in = cfg.sheet_h_mm / MM_PER_INCH
    corner_radius_in = cfg.corner_radius_mm / MM_PER_INCH
    lines = [
        "Cricut Design Space — 4-up cut template",
        f"Sheet: {cfg.sheet_w_mm:.1f} x {cfg.sheet_h_mm:.1f} mm ({sheet_w_in:.1f} x {sheet_h_in:.1f} in) (US Letter), {cfg.dpi} DPI",
        f"Each cut: rounded rectangle {cfg.card_w_mm:.0f} x {cfg.card_h_mm:.0f} mm "
        f"({w_in:.3f} x {h_in:.3f} in), radius {cfg.corner_radius_mm:.0f} mm ({corner_radius_in:.3f} in)",
        "Positions are the top-left corner of each card's trim box, measured from the",
        "top-left of the sheet. Place the imported sheet image at the sheet origin.",
        "",
    ]
    for i, box in enumerate(card_boxes(cfg), start=1):
        x_in = box.trim_x_mm / MM_PER_INCH
        y_in = box.trim_y_mm / MM_PER_INCH
        lines.append(
            f"Card {i}: x={box.trim_x_mm:.2f} mm ({x_in:.3f} in), "
            f"y={box.trim_y_mm:.2f} mm ({y_in:.3f} in)"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_template_coords(GeometryConfig()))
