# Fabrication outputs

Exactly what was sent to the fab, archived per board per revision — if a
board ever needs re-ordering or a fault traced, this zip is the ground truth,
not whatever the CAD file has drifted to since.

| File | Board | Rev | Ordered | Notes |
|---|---|---|---|---|
| [board-a/board-a-rev0-gerber-2026-07-13.zip](board-a/board-a-rev0-gerber-2026-07-13.zip) | A (core) | REV0 | 2026-07-13 | 2-layer; full set incl. PTH/NPTH/via drills; EasyEDA Pro export |

CAD source (EasyEDA Pro `.epro` project exports + schematic PDFs) lives in
`../cad/` — commit a fresh export alongside every fab order.
