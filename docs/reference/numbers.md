# Critical numbers

Memorize these. Most “wrong size” disasters are one of these traps.

## Sheet size in Design Space: **5.276 in width**

Each generated sticker sheet is **134 × 184 mm** ≈ **5.276 × 7.244 in**.

| Fact | Detail |
|------|--------|
| What you set | **Width = 5.276 in** (aspect lock on → height ~7.248) |
| What Design Space does | Imports around **~10.98 in** — it **ignores PNG DPI** |
| Opening a **saved** project | Size is already stored — **do not resize** |

### The 6.73 × 9.25 trap

**6.73 × 9.25 in is NOT a size you type in.**  
That is the *maximum* Print Then Cut area — a boundary artwork fits **inside**, not a target.

Sizing the sheet to fill that area scales everything ~**1.28×**. Cards that should be
63 × 88 mm cut out near **80 × 112 mm**. Aspect ratios look almost identical on screen
(6.73/9.25 ≈ 0.7276 vs sheet ≈ 0.7278), so it *looks* right until you measure a cut card.

## Material size: **Letter (8.5 × 11)**, not A4

On the **Prepare** screen (after Make It), set **Material Size → Letter**.

- Design Space often defaults to **A4**.
- A4 is **not** saved with the project — set it **every** Make It session.
- Wrong material size lays registration marks for the wrong page; the cut misses.

Mirror stays **off**.

## Cards per sheet

Always **4** (2×2). Partial sheets are not built by the catalog (`build` leaves leftovers
queued until you have a full group of 4).

## Bleed

| Mode | Behavior |
|------|----------|
| Default MTG / MPC Autofill | Source images usually have bleed; `cli` default `bleed_mm=3` |
| Face-only art (e.g. some OP extracts) | Use `--bleed 0` on `cli`, or rely on auto-detect when bleed_mm > 0 |
| Design Space **Add Bleed** | Must be **ON** at Print Setup. Printed cards look slightly oversized on the sheet — correct; the blade removes the bleed |
| Catalog `build` | Always uses non-zero bleed config so mixed MTG/OP queues auto-detect per image |

Judge final size on a **cut** card, never on the printed sheet alone.

## Folder rule

**One folder of sheets per deck or queue.**  
Sheets are named `sheet_1.png`, `sheet_2.png`, … Print automation matches art against
siblings in that folder. Mixing two decks in one folder risks printing the wrong sheet.

## Catalog keys

| Built by | `sheet_contents` / print key | When printing |
|----------|------------------------------|---------------|
| `python -m mtgproxy.cli --out ./sheets-chocobo` | folder basename: `sheets-chocobo` | `--sheets ./sheets-chocobo` (no `--queue`) |
| `python -m mtgproxy.catalog build reprints --out ./sheets-reprints` | **queue name**: `reprints` | `--sheets ./sheets-reprints --queue reprints` |

Forgetting `--queue` on a queue-built folder logs a soft catalog warning and **never
drains the queue**.
