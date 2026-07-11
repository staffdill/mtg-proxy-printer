from mtgproxy.sources import list_card_images, read_manifest, resolve_card_list


def _touch(folder, name):
    p = folder / name
    p.write_bytes(b"x")
    return p


def test_list_card_images_filters_and_sorts(tmp_path):
    _touch(tmp_path, "b.png")
    _touch(tmp_path, "a.JPG")
    _touch(tmp_path, "notes.txt")
    names = [p.name for p in list_card_images(tmp_path)]
    assert names == ["a.JPG", "b.png"]


def test_read_manifest_parses_quantities_and_comments(tmp_path):
    m = tmp_path / "order.txt"
    m.write_text("# my deck\nsol_ring.png,4\n\nforest.png\n", encoding="utf-8")
    assert read_manifest(m) == [("sol_ring.png", 4), ("forest.png", 1)]


def test_resolve_card_list_expands_manifest_quantities(tmp_path):
    _touch(tmp_path, "sol_ring.png")
    _touch(tmp_path, "forest.png")
    m = tmp_path / "order.txt"
    m.write_text("sol_ring.png,2\nforest.png,1\n", encoding="utf-8")
    paths = resolve_card_list(tmp_path, m)
    assert [p.name for p in paths] == ["sol_ring.png", "sol_ring.png", "forest.png"]


def test_resolve_card_list_without_manifest_lists_folder(tmp_path):
    _touch(tmp_path, "a.png")
    _touch(tmp_path, "b.png")
    paths = resolve_card_list(tmp_path)
    assert [p.name for p in paths] == ["a.png", "b.png"]
