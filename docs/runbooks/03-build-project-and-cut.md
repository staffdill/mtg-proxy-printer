# Runbook: Build one project, then cut (possibly elsewhere)

Puts **every** sheet from a folder onto **one** Design Space canvas (each sized to 5.276 in)
so Auto Save keeps a multi-mat project you can open later to cut.

## When to use

- Printing already finished (or sheets already printed from another path)
- You want one named project for cutting on this or another machine
- Cutting session is separate from printing session

## Critical order rule

**Build the project LAST — after printing — never before.**

`printing.py` starts normal runs with a canvas reset (select-all + delete). If you
`--build-project` and then run a print pass on the **same** project canvas, you **wipe**
the built project.

If you must print after building: **File → New** (blank canvas) first.

## 1. Build

Design Space open, interactive:

```bat
python -m mtgproxy.cricut.printing --sheets ./sheets-mydeck --build-project
```

- Places each library sheet on the canvas, sized correctly.
- Auto Save stores the project; rename it in Design Space (there is no save dialog).

## 2. Cut (same machine)

1. Open the project from **My Stuff** if you left it.
2. **Make It** → one mat per sheet.
3. Prepare: **Material Size = Letter (8.5 × 11)** every time (defaults to A4; not saved).
4. Continue → **I’ve Already Printed**.
5. Base Material → load LightGrip → Go.
6. Peel mat from card. Next mat.

**Do not resize** sheets in the cut project — they are already 5.276 in.

## 3. Cut on another machine

1. Ensure the project synced / is available under My Stuff on the other PC.
2. Same Make It flow as above.
3. Hardware/paper same as [hardware.md](../reference/hardware.md).

## Success

- Project contains one layer/group per sheet.
- Cut cards measure ~63×88 mm.

## Related

- Print-only automation: [02-automated-print.md](02-automated-print.md)  
- Cut-only checklist: [04-cut-only-saved-project.md](04-cut-only-saved-project.md)  
