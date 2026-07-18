# Runbook: Resume a failed upload or print run

Automation stops with an error, `--start-at N` hint, and usually a screenshot under `debug/`.

## Immediate checks

1. **Read the terminal message** — which template / step failed?
2. **Open the newest `debug/*.png`** — what is actually on screen?
3. **Physical printer** — if you used `--auto-print`, is a page already coming out?  
   Do **not** resume the same sheet if it’s already printed.

## Resume upload

```bat
python -m mtgproxy.cricut.upload --sheets ./sheets-mydeck --start-at N
```

`N` is the 1-based sheet index (the one that failed or the next incomplete).

## Resume print

```bat
python -m mtgproxy.cricut.printing --sheets ./sheets-mydeck --start-at N
```

With auto-print / queue:

```bat
python -m mtgproxy.cricut.printing --sheets ./sheets-mydeck --auto-print --start-at N
python -m mtgproxy.cricut.printing --sheets ./sheets-reprints --queue reprints --auto-print --start-at N
```

Single sheet only:

```bat
python -m mtgproxy.cricut.printing --sheets ./sheets-mydeck --only N
```

## Diagnose before retrying the same N

| `debug/` shows | Likely cause | Action |
|----------------|--------------|--------|
| Previous step’s screen still visible | Click dropped during render | Resume same N after UI settles; or re-click manually then resume N+1 if that sheet finished |
| Unexpected modal (Verify quality, Connect machine, Cancel cut) | Post-print modal chain | Let flow handle, or dismiss carefully; see recent printing fixes |
| Completely wrong screen / zoom | Template mismatch after update | Re-crop template PNGs under `mtgproxy/cricut/templates/` |
| Print Setup missing Add Bleed | System print dialog on | Turn off “Use system dialog”; [00-setup.md](00-setup.md) |
| Blank / wrong app focused | Foreground lost | Click Design Space, re-run |

## Dry-run without risking clicks

```bat
python -m mtgproxy.cricut.upload --sheets ./sheets-mydeck --dry-run
python -m mtgproxy.cricut.printing --sheets ./sheets-mydeck --dry-run
```

Locates templates and reports confidence only.

## Catalog after a partial print

- Sheets that **did** print successfully should already have history if cataloguing was wired and `--queue` was correct.
- Unprinted sheets keep queue qty (drain only on success).
- Resuming does not re-drain a sheet already recorded unless you print it again (would double-count history).

## Nuclear options

1. Close Design Space modals to a clean Canvas.  
2. New blank project if the canvas is polluted.  
3. Re-upload a single sheet if it’s missing from the library.  
4. Re-crop templates from a full-screen capture if Design Space updated UI.

More symptoms: [troubleshooting.md](../reference/troubleshooting.md).
