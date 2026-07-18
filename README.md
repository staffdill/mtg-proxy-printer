# mtg-proxy-printer

Generate 4-up sticker sheets for MTG (and similar) proxies, upload/print via Cricut
Design Space automation on Windows, and track reprints in a local catalog.

## Documentation

**Start with scenario runbooks:** [docs/README.md](docs/README.md)

| I want to… | Runbook |
|------------|---------|
| Set up this PC | [docs/runbooks/00-setup.md](docs/runbooks/00-setup.md) |
| Print a full MTG deck | [docs/runbooks/01-full-mtg-deck.md](docs/runbooks/01-full-mtg-deck.md) |
| Unattended print | [docs/runbooks/02-automated-print.md](docs/runbooks/02-automated-print.md) |
| Build a cut project | [docs/runbooks/03-build-project-and-cut.md](docs/runbooks/03-build-project-and-cut.md) |
| Cut only | [docs/runbooks/04-cut-only-saved-project.md](docs/runbooks/04-cut-only-saved-project.md) |
| One Piece / PDF | [docs/runbooks/05-one-piece-pdf.md](docs/runbooks/05-one-piece-pdf.md) |
| Reprints (CLI) | [docs/runbooks/06-catalog-reprints-cli.md](docs/runbooks/06-catalog-reprints-cli.md) |
| Reprints (web UI) | [docs/runbooks/07-catalog-web-ui.md](docs/runbooks/07-catalog-web-ui.md) |
| Resume a failed run | [docs/runbooks/08-resume-failed-run.md](docs/runbooks/08-resume-failed-run.md) |

Critical numbers (5.276 in, Letter not A4): [docs/reference/numbers.md](docs/reference/numbers.md)

## Quick install

```bat
pip install -r requirements.txt
```

## License / status

Personal tooling; Design Space UI automation is fragile across app updates.
