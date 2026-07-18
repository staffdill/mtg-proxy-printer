# Hardware & materials

Verified end to end (print + cut) on 2026-07-11.

## Devices

| Role | Model / notes |
|------|----------------|
| Printer | HP OfficeJet Pro 8710 (network / WSD) |
| Cutter | Cricut Explore Air 2 |
| Software | Cricut Design Space (Windows) |

## Paper & mat

| Item | Spec |
|------|------|
| Paper | Epson Presentation Paper Matte, **8.5 × 11 in** |
| Why matte | Cricut Print Then Cut optical sensor needs a non-gloss surface to read registration marks |
| Mat | LightGrip (blue) |
| Blade | Clean Fine-Point |

## Do not laminate

Laminate is glossy: the Print Then Cut sensor cannot read registration marks through a
reflective surface. It is also harder to cut than paper.

Sleeving each finished proxy with a real card (or basic land) behind it already gives
gloss and rigidity.

## Removal technique

Peel the **mat away from the card** — flip the mat face-down and roll it back.  
Never lift the thin paper off the mat; it tears.

## First-run verification (once)

After the first successful cut, measure a **cut** card with calipers:

- **63 × 88 mm** (± 0.3 mm)
- corner radius ~3 mm
- cut sits **in ink**, no white sliver
- no tearing on removal

If size or registration is off, re-run Design Space’s **Print Then Cut calibration**.
That is a machine procedure, not a Python bug.

See also: [numbers.md](numbers.md), [troubleshooting.md](troubleshooting.md).
