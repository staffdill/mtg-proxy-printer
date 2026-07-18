# CLI cheatsheet

All commands from the **repo root** unless noted. Install once: `pip install -r requirements.txt`.

## Sheet generation

```bat
python -m mtgproxy.cli --input "<card-folder>" --out ./sheets-<name> --sticker
```

| Flag | Meaning |
|------|---------|
| `--sticker` | Transparent rounded cards for Design Space Print Then Cut |
| `--bleed 0` | Face-only sources (no source bleed) |
| `--manifest order.txt` | Lines `filename.png,quantity` for order/qty |
| `--catalog-db` / `--catalog-images-dir` | Override catalog paths (tests / non-default) |

## PDF / multi-card sheet → individuals

```bat
python -m mtgproxy.separate --input deck.pdf --out ./cards-op --manifest names.txt
```

Manifest: one card name per line, placement order (top→bottom, left→right).  
Duplicates become `Name.png`, `Name (2).png`, …

## Catalog (CLI)

```bat
python -m mtgproxy.catalog search "sol ring"
python -m mtgproxy.catalog add "Sol Ring" --variant chocobo-deck --to reprints --qty 2
python -m mtgproxy.catalog list reprints
python -m mtgproxy.catalog build reprints --out ./sheets-reprints
python -m mtgproxy.catalog history "Sol Ring" --variant chocobo-deck
```

Partial search is available in the **web UI**; CLI search is **exact** name match by default.

## Catalog (web UI)

```bat
set MTGPROXY_WEB_PASSWORD=...
set MTGPROXY_WEB_SECRET=...
python -m mtgproxy.web --host 0.0.0.0 --port 8765
```

## Design Space automation

```bat
REM Upload sheet folder into library
python -m mtgproxy.cricut.upload --sheets ./sheets-<name>

REM Drive each sheet to Print Setup (click Print yourself)
python -m mtgproxy.cricut.printing --sheets ./sheets-<name>

REM Unattended Print clicks
python -m mtgproxy.cricut.printing --sheets ./sheets-<name> --auto-print

REM Queue-built sheets (drain catalog)
python -m mtgproxy.cricut.printing --sheets ./sheets-reprints --queue reprints --auto-print

REM One canvas project for cutting later — LAST step after printing
python -m mtgproxy.cricut.printing --sheets ./sheets-<name> --build-project
```

| Flag | Meaning |
|------|---------|
| `--start-at N` | Resume from sheet N |
| `--only N` | Only sheet N |
| `--dry-run` | Find templates, click nothing |
| `--queue NAME` | Catalog key for queue-built folders |

Do not touch mouse/keyboard during automation. Move cursor to a **screen corner** to abort (failsafe).

## Common paths

| Path | Role |
|------|------|
| `catalog.db` | SQLite catalog |
| `catalog/images/` | Owned card art |
| `catalog/images/snapshots/` | Print-history art copies |
| `sheets-<name>/` | Generated sheet PNGs |
| `debug/` | Failure screenshots from automation |
