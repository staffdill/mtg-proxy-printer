# MTG Proxy Printer — Documentation

Practical runbooks for this repo. Specs and implementation plans live under
`docs/superpowers/` (design history); day-to-day ops live here.

## What do you want to do?

| Scenario | Runbook |
|----------|---------|
| **First time** — install, calibrate, printer defaults | [runbooks/00-setup.md](runbooks/00-setup.md) |
| **Full MTG deck** from an MPC Autofill folder → sheets → library → print → cut | [runbooks/01-full-mtg-deck.md](runbooks/01-full-mtg-deck.md) |
| **Unattended print** (`--auto-print`) of a whole sheet folder | [runbooks/02-automated-print.md](runbooks/02-automated-print.md) |
| **Build one project** for cutting later / on another machine | [runbooks/03-build-project-and-cut.md](runbooks/03-build-project-and-cut.md) |
| **Cut only** from an already-saved Design Space project | [runbooks/04-cut-only-saved-project.md](runbooks/04-cut-only-saved-project.md) |
| **One Piece / PDF** (or other multi-card sheet) → named cards → sheets | [runbooks/05-one-piece-pdf.md](runbooks/05-one-piece-pdf.md) |
| **Reprints / one-offs via CLI** (catalog search → queue → build → print) | [runbooks/06-catalog-reprints-cli.md](runbooks/06-catalog-reprints-cli.md) |
| **Reprints via web UI** (LAN browser over the catalog) | [runbooks/07-catalog-web-ui.md](runbooks/07-catalog-web-ui.md) |
| **Resume** a halted upload or print run | [runbooks/08-resume-failed-run.md](runbooks/08-resume-failed-run.md) |

## Shared reference

| Topic | Doc |
|-------|-----|
| Hardware, paper, mat, blade | [reference/hardware.md](reference/hardware.md) |
| Critical numbers (5.276 in, Letter vs A4, bleed) | [reference/numbers.md](reference/numbers.md) |
| Symptom → fix table | [reference/troubleshooting.md](reference/troubleshooting.md) |
| CLI quick map | [reference/cli-cheatsheet.md](reference/cli-cheatsheet.md) |

## Design notes (not runbooks)

- `docs/superpowers/specs/` — approved designs  
- `docs/superpowers/plans/` — implementation plans  
- `docs/superpowers/notes/` — UI recon findings  

## Legacy

[`RUNBOOK.md`](RUNBOOK.md) is a short pointer to this index. Prefer the scenario
runbooks above.
