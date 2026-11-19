# Fabrication outputs

Exactly what was sent to the fab, archived per board per revision — if a
board ever needs re-ordering or a fault traced, this zip is the ground truth,
not whatever the CAD file has drifted to since.

| File | Board | Rev | Ordered | Notes |
|---|---|---|---|---|
| [board-a/board-a-rev0-gerber-2026-07-13.zip](board-a/board-a-rev0-gerber-2026-07-13.zip) | A (core) | REV0 | 2026-07-13 | 2-layer; full set incl. PTH/NPTH/via drills; EasyEDA Pro export |
| [board-b/board-b-rev0-gerber-2026-11-13.zip](board-b/board-b-rev0-gerber-2026-11-13.zip) | B (environment) | REV0 | 2026-11-18 | 2-layer 58 x 70 mm, trimmed (SHT40 + MS5607 soldered, PH-5 for the lightning module); tongue slots on the outline layer, two NPTH tie slots; J3/J4 on the back; BOM + pick-and-place CSVs, JLCPCB costing and India sourcing notes alongside; ERC/DRC clean at export |

CAD source lives in
`../cad/` — commit a fresh export alongside every fab order.
