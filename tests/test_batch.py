from PIL import Image
from mtgproxy.geometry import GeometryConfig, sheet_size_px
from mtgproxy.batch import build_sheets, save_sheets


def _make_images(tmp_path, n):
    paths = []
    for i in range(n):
        p = tmp_path / f"card_{i}.png"
        Image.new("RGB", (100, 140), "red").save(p)
        paths.append(p)
    return paths


def test_build_sheets_chunks_by_four(tmp_path):
    cfg = GeometryConfig()
    paths = _make_images(tmp_path, 5)  # 5 cards -> 2 sheets
    sheets = build_sheets(paths, cfg)
    assert len(sheets) == 2
    assert all(s.size == sheet_size_px(cfg) for s in sheets)


def test_save_sheets_zero_pads_names(tmp_path):
    cfg = GeometryConfig()
    paths = _make_images(tmp_path, 5)
    sheets = build_sheets(paths, cfg)
    out = tmp_path / "out"
    written = save_sheets(sheets, out)
    assert [p.name for p in written] == ["sheet_1.png", "sheet_2.png"]
    assert all(p.exists() for p in written)
