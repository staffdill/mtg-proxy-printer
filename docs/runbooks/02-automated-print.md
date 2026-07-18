# Runbook: Unattended automated print

Drive Design Space through **Print** for every sheet without babysitting the Print button.

**Danger:** spends paper and ink unattended. Load enough matte stock for **every** sheet first.

## When to use

- Full deck already uploaded to the library
- Sheet folder known good (`./sheets-mydeck`)
- You’ve done a semi-automated print once and trust bleed + Letter + size

## Preconditions

- [00-setup.md](00-setup.md) done (especially “Use system dialog” **OFF**)
- Design Space open, interactive session (not a locked RDP desktop)
- Tray full of matte Letter paper
- Sheets already in Design Space library ([01-full-mtg-deck.md](01-full-mtg-deck.md) upload step)

## Command

```bat
python -m mtgproxy.cricut.printing --sheets ./sheets-mydeck --auto-print
```

Queue-built reprints:

```bat
python -m mtgproxy.cricut.printing --sheets ./sheets-reprints --queue reprints --auto-print
```

## While it runs

- **Do not touch mouse/keyboard.** Corner abort still works.
- Watch the printer for jams / out-of-paper.
- If it stops, **look at the printer before resuming** — the current sheet may already be printing.

## Resume after a halt

```bat
python -m mtgproxy.cricut.printing --sheets ./sheets-mydeck --auto-print --start-at N
```

See [08-resume-failed-run.md](08-resume-failed-run.md). Confirm sheet `N` is not already on paper.

## After all sheets print

1. Dry stacks flat (2–3 min per sheet is a good habit).
2. Either cut sheet-by-sheet on this machine, or  
   [03-build-project-and-cut.md](03-build-project-and-cut.md) for a multi-mat cut project.

## Do not

- Run `--auto-print` and `--build-project` in the same breath without understanding order: **print first, build project last**.
- Resume blindly after a mid-print crash.
