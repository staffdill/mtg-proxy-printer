# Troubleshooting

Cross-cutting symptom table. Scenario-specific tips also appear in each runbook.

## Automation / Design Space

| Symptom | Fix |
|---------|-----|
| Run halts mid-flow; “cannot see” a template | Often Design Space **dropped a click while rendering** (slower with large libraries). Check `debug/`: if the *previous* screen is still showing, resume with `--start-at N`. |
| Halts on `07_upload_btn` with “Convert Upload To” still on screen | Continue click swallowed mid-render. Flow re-clicks; if still stuck, `--start-at N`. |
| Sheets pile up on canvas (`sheet_11`, … in Layers) | Upload places images asynchronously; clear must wait for the image. If it recurs, grace period may be too short on your machine. |
| Print says sheet “not in the library” | Uploads grid is **newest first** and scrolls. Deep decks need scroll; if still missing, upload failed — check library. |
| Halts waiting for `51_add_bleed` | Something covers Print Setup (often Windows system print dialog). Turn Design Space **“Use system dialog” OFF**. Set HP defaults via Windows Preferences (see [00-setup](../runbooks/00-setup.md)). |
| Template never matches after a Design Space update | UI changed. Inspect `debug/`, re-crop template PNG, resume `--start-at N`. |
| Foreground / remote desktop issues | Automation must take focus; RDP can lock foreground. Prefer local interactive session. |

## Size & cut quality

| Symptom | Fix |
|---------|-----|
| Cards look slightly oversized **on the printed sheet** | Expected with **Add Bleed ON**. Measure a **cut** card. |
| Cards oversized **after cutting** | Canvas width was not **5.276 in** (or you sized to 6.73×9.25). See [numbers.md](numbers.md). |
| White sliver on cut edge | Add Bleed was OFF, or calibration off. Re-run Print Then Cut calibration. |
| Cricut can’t read registration marks | Matte paper only (no laminate/gloss); good black ink; even light, no glare; marks not cropped; mat loaded straight. |
| Paper curls → sensor fails | Dry flat 2–3 min; gently back-roll; load flat. |
| Card tears on removal | LightGrip; peel **mat** away from card. |
| Cut doesn’t go through | More pressure / multi-cut ×2; fresh blade. |

## Catalog & queues

| Symptom | Fix |
|---------|-----|
| Queue not draining after print | Queue-built sheets need `--queue <name>`. Without it, soft warning and no drain. |
| `build` does nothing | Fewer than 4 card slots queued — leftover stays in queue (by design). |
| Wrong card queued | Always disambiguate with `--variant` or `--id` (or use web UI thumbnails). |
| History art wrong after re-import | Snapshots under `catalog/images/snapshots/` should preserve print-time art; re-import only overwrites canonical images. |
| Web UI + CLI fighting | Prefer one writer at a time against `catalog.db`. |

## Print double-spend

If a run dies under `--auto-print`, **check the physical printer** before `--start-at N`. The sheet may already be on paper; resuming can print it twice.

## Where to look

| Artifact | Meaning |
|----------|---------|
| `debug/*.png` | What the screen looked like when a step failed |
| Terminal `--start-at N` hint | Resume point printed by the automation |
| Design Space Auto Save | Projects persist; wiping canvas after `--build-project` destroys the cut project |
