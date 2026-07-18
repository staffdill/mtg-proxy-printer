# Runbook: Full MTG deck (MPC Autofill → print → cut)

End-to-end path for a normal Magic deck folder of card images.

**Related:** [numbers.md](../reference/numbers.md) · [troubleshooting.md](../reference/troubleshooting.md)

## Inputs

- Folder of card images (e.g. MPC Autofill export). Subfolder `_not_in_list` is ignored.
- Empty Design Space canvas, Design Space focused and visible.
- Matte Letter stock loaded as needed.

## 1. Generate sheets

```bat
python -m mtgproxy.cli --input "C:\path\to\mpc-folder" --out ./sheets-mydeck --sticker
```

- One **output folder per deck** (`sheets-mydeck`).
- Uses sticker mode (transparent, rounded) so Design Space builds cut lines.
- Catalogues cards into `catalog.db` automatically (variant = `sheets-mydeck` folder name).

**Options:**

| Need | Flag |
|------|------|
| Face-only images | `--bleed 0` |
| Exact order / qty | `--manifest order.txt` (`filename.png,quantity` per line) |

Sheet physical size: **5.276 × ~7.244 in**. You will set width in Design Space later.

## 2. Upload to Design Space library

1. Open Design Space → Canvas, empty project.
2. Do not use the mouse while the script runs.

```bat
python -m mtgproxy.cricut.upload --sheets ./sheets-mydeck
```

- Corner failsafe aborts.
- On halt: note `--start-at N` and `debug/` screenshot → [08-resume-failed-run.md](08-resume-failed-run.md).
- Optional: `--dry-run` checks templates without clicking.

## 3. Print (semi-automated)

Default: automation drives each sheet to **Print Setup**; **you** click Print (or use
[02-automated-print.md](02-automated-print.md) for unattended).

```bat
python -m mtgproxy.cricut.printing --sheets ./sheets-mydeck
```

Per sheet the flow handles Make → Letter material → Send to Printer → bleed check.

**After each print (if you’re cutting as you go):** dry 2–3 minutes, load mat, cut, peel mat from card. Or finish all printing first, then cut from a built project ([03-build-project-and-cut.md](03-build-project-and-cut.md)).

### Manual checklist (if not fully automated)

1. Sheet on canvas at **width 5.276 in** (not 6.73×9.25).
2. Make → Material Size **Letter** (not A4).
3. Send to Printer → **Add Bleed ON** → Print.
4. Dry flat → Base Material → cut → peel mat from card → sleeve.

## 4. Optional: build project for cutting later

**Only after printing is done** (or you accept a blank canvas first):

```bat
python -m mtgproxy.cricut.printing --sheets ./sheets-mydeck --build-project
```

Then rename the Auto Saved project by hand. See [03-build-project-and-cut.md](03-build-project-and-cut.md).

**Never** run a normal print pass on the same canvas after `--build-project` without a new blank canvas — reset deletes the canvas contents.

## Success criteria

- [ ] Sheet folder has the expected number of `sheet_*.png` (4 cards each; last may be partial only if you force non-catalog tooling — catalog builds leave leftovers instead).
- [ ] All sheets appear in Design Space Uploads / library.
- [ ] Cut card measures ~63×88 mm with ink on the edge.

## Next

- Unattended multi-sheet print: [02-automated-print.md](02-automated-print.md)  
- Cut on another PC: [03-build-project-and-cut.md](03-build-project-and-cut.md) / [04-cut-only-saved-project.md](04-cut-only-saved-project.md)  
