# CAD sources & derived design outputs

Per board, per revision, exported from **EasyEDA Pro** at the moment the fab
order went out — paired with the matching gerber zip in `../fab/`.

## board-a/ — REV0 (ordered 2026-07-13)

| File | What it is |
|---|---|
| `board-a-rev0.epro2` | **The source of truth** — full EasyEDA Pro project export (schematic + PCB + library parts). Re-importable; open this to continue design work. |
| `board-a-rev0-schematic.pdf` | Schematic, human-readable — what reviews read |
| `board-a-rev0-pcb.pdf` | PCB layers, human-readable |
| `board-a-rev0-bom.xlsx` | BOM as exported from the design — the real designators (reconcile docs against this, per the standing plan) |
| `board-a-rev0-pick-and-place.xlsx` | Component coordinates (for assembly services) |
| `board-a-rev0-schematic.enet` / `-pcb.enet` | Netlists from each editor — diffable pair; they should describe the same design |
| `board-a-rev0.step` | 3D model (32 MB) — feeds the Onshape enclosure work |

Convention: every future fab order commits a fresh export set here, same
names with the new rev, plus its gerber zip in `../fab/`.
