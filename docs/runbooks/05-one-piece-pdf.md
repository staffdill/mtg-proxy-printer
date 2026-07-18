# Runbook: One Piece (or any multi-card PDF / grid) → sheets

Use when cards start as a **PDF** or a multi-card **grid image**, not as individual MTG
MPC files.

## Goal

1. Split the PDF/grid into **named** individual card PNGs.  
2. Tile into sticker sheets.  
3. Continue with upload/print like a normal deck.

## 1. Manifest of names

Text file, **one card name per line**, in the same order as placements in the PDF:

- Top → bottom, left → right (matches `extract_cards_from_pdf` / grid walk order).
- Blank lines and `#` comments are skipped.
- Repeat a name for duplicate copies; files become `Name.png`, `Name (2).png`, …

Example `names.txt`:

```text
# Order matches PDF placement
Nami
Luffy
Zoro
Zoro
```

Count of non-comment lines **must equal** number of cards extracted.

## 2. Separate

```bat
python -m mtgproxy.separate --input "path\to\proxy.pdf" --out ./cards-onepiece --manifest names.txt
```

Without `--manifest`, files are anonymous `card_001.png` — **catalog will not know real names**.

Grid images (not PDF) use the same command with image input; adjust `--cols` / `--rows` if needed.

## 3. Build sheets

One Piece face art is often **without** source bleed:

```bat
python -m mtgproxy.cli --input ./cards-onepiece --out ./sheets-onepiece --sticker --bleed 0
```

If sources already include bleed, omit `--bleed 0`.

Catalog variant label defaults to the **out folder name** (`sheets-onepiece`).

## 4. Print path

Same as MTG:

1. [Upload](01-full-mtg-deck.md#2-upload-to-design-space-library)  
2. [Print](01-full-mtg-deck.md#3-print-semi-automated) or [02-automated-print.md](02-automated-print.md)  
3. [Cut](04-cut-only-saved-project.md) or [03-build-project-and-cut.md](03-build-project-and-cut.md)  

Still set canvas width **5.276 in** and material **Letter**.

## Mixing MTG + OP in one catalog queue

Catalog `build` uses non-zero bleed config so layout can **auto-detect** bleed vs face-only
per image by aspect ratio. Full MTG deck runs still use normal `cli` settings.

## Pitfalls

| Mistake | Result |
|---------|--------|
| Manifest line count ≠ card count | `separate` errors |
| No manifest | Catalog names become `card_001`, useless for reprints |
| `--bleed 3` on face-only art | Wrong crop / scaling |
