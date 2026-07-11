from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


def list_card_images(folder: Path) -> list[Path]:
    files = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    return sorted(files, key=lambda p: p.name)


def read_manifest(path: Path) -> list[tuple[str, int]]:
    entries: list[tuple[str, int]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "," in line:
            name, qty = line.rsplit(",", 1)
            entries.append((name.strip(), int(qty.strip())))
        else:
            entries.append((line, 1))
    return entries


def resolve_card_list(folder: Path, manifest: Path | None = None) -> list[Path]:
    if manifest is None:
        return list_card_images(folder)
    paths: list[Path] = []
    for name, qty in read_manifest(manifest):
        paths.extend([folder / name] * qty)
    return paths
