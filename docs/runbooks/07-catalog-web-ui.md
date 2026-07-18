# Runbook: Catalog web UI (LAN)

Browser UI for search → queue → build → history.  
**Does not** drive Design Space or the printer.

## When to use

- Phone or another PC on the home LAN
- Picking variants by **thumbnail** instead of typing `--variant`
- Building reprint queues without CLI

## Security

- **Trusted LAN only** — not the public internet.
- Single shared password (no multi-user accounts).
- Prefer not writing to `catalog.db` from CLI and the web UI at the same time.

## 1. Start the server

On the machine that has the catalog files (`catalog.db`, `catalog/images/`):

```bat
cd C:\Users\Staff\mtg-proxy-printer
set MTGPROXY_WEB_PASSWORD=your-shared-password
set MTGPROXY_WEB_SECRET=long-random-string
python -m mtgproxy.web --host 0.0.0.0 --port 8765
```

Flags override env if both are set (`--password`, `--secret`, `--db`, `--images-dir`, `--sheets-root`).

| Flag | Default |
|------|---------|
| `--host` | `0.0.0.0` (LAN) |
| `--port` | `8765` |
| `--db` | `catalog.db` |
| `--images-dir` | `catalog/images` |
| `--sheets-root` | `.` → builds `./sheets-<queue>/` |

If `MTGPROXY_WEB_SECRET` is missing, an ephemeral secret is generated and **sessions reset** on restart.

## 2. Open in browser

- Same PC: http://127.0.0.1:8765  
- Phone / LAN: http://\<pc-lan-ip\>:8765  

Log in with the shared password only (no username field).

## 3. Day-to-day flow

1. **Search** — type a fragment of the card name (partial match).  
2. Pick the right variant (thumbnail + label).  
3. Set **qty** and **queue** (default `reprints`) → **Add**.  
4. Open **Queue** (nav: reprints / one-offs / free-text name).  
5. When ≥ 4 card slots are queued → **Build full sheets**.  
6. Copy the printed command, e.g.  

   ```text
   python -m mtgproxy.cricut.printing --sheets .\sheets-reprints --queue reprints
   ```

7. On the Design Space machine: upload that folder, then print with **`--queue`**  
   ([06-catalog-reprints-cli.md](06-catalog-reprints-cli.md) steps 5–6).  
8. **History** link on a card shows prior successful prints + snapshot art when available.

## 4. Build leftovers

If fewer than 4 slots: build reports leftover; queue unchanged. Add more cards later and build again.

## Firewall

Windows may prompt to allow Python on private networks the first time you bind `0.0.0.0`. Allow on private LAN; deny public if offered.

## Stop the server

Ctrl+C in the terminal, or kill the process that owns port 8765.

## See also

- Design: `docs/superpowers/specs/2026-07-18-catalog-web-ui-design.md`  
- CLI equivalent: [06-catalog-reprints-cli.md](06-catalog-reprints-cli.md)  
