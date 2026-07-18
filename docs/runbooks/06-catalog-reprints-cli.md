# Runbook: Catalog reprints / one-offs (CLI)

Print specific cards again without rebuilding an entire deck folder by hand.

**Requires:** cards already in the catalog (from a prior `cli` or `catalog build` run).  
No retroactive import of old decks in v1.

## Concepts

| Term | Meaning |
|------|---------|
| Card identity | `(name, variant_label)` — usually variant = deck/out folder that first imported it |
| Queue | Named basket (`reprints`, `one-offs`, …) with quantities |
| Build | Tiles full groups of **4** into `sheet_*.png`; leaves 1–3 leftover in the queue |
| Drain | Queue qty drops only after a **successful print** (not on build) |

## 1. Search

Exact name (case-insensitive):

```bat
python -m mtgproxy.catalog search "Sol Ring"
```

Note `id` and `variant_label` if multiple variants exist.

## 2. Add to a queue

```bat
python -m mtgproxy.catalog add "Sol Ring" --variant sheets-chocobo --to reprints --qty 2
```

Or by id (no ambiguity):

```bat
python -m mtgproxy.catalog add --id 42 --to reprints --qty 1
```

`qty` must be ≥ 1. Multiple adds **accumulate** quantity.

## 3. List

```bat
python -m mtgproxy.catalog list reprints
```

## 4. Build sheets

Only full 4-card sheets:

```bat
python -m mtgproxy.catalog build reprints --out ./sheets-reprints
```

Example output:

```text
Built 1 sheet(s) (4 cards). 1 card(s) left in 'reprints' -- not enough for a full sheet yet.
Print with: python -m mtgproxy.cricut.printing --sheets ./sheets-reprints --queue reprints
```

**Build does not remove queue items.** Print does.

Usage discipline: build → print that folder before building the same queue again (or you
can double-build; rebuild of the same sheet names overwrites DB rows for those files).

## 5. Upload and print **with `--queue`**

```bat
python -m mtgproxy.cricut.upload --sheets ./sheets-reprints
python -m mtgproxy.cricut.printing --sheets ./sheets-reprints --queue reprints
```

Or unattended:

```bat
python -m mtgproxy.cricut.printing --sheets ./sheets-reprints --queue reprints --auto-print
```

Without `--queue`, print history may not match and **the queue will not drain**.

## 6. History

```bat
python -m mtgproxy.catalog history "Sol Ring" --variant sheets-chocobo
```

## Web alternative

Same flows in a browser: [07-catalog-web-ui.md](07-catalog-web-ui.md).

## Related

- Numbers / folder keys: [numbers.md](../reference/numbers.md)  
- Full deck first import: [01-full-mtg-deck.md](01-full-mtg-deck.md)  
