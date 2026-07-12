# Enclosures

Mechanical and enclosure design happens in **Onshape** (Anish), not in this repo.

This directory is reserved for:
- links to the Onshape document(s), once they exist
- exported files (STEP / STL / 3MF) for printing and archival

Nothing to see yet. The leaves will need: a radiation-shielded pocket for the SHTC3/SHT4x,
airflow for the PMS7003, a clear-of-metal zone for the AS3935 and the LoRa antenna, and a
mast mount that survives the subject matter of the project.

**Decided (2026-07-12):** the core box is a **separate sealed enclosure below and offset
from the Stevenson screen** (~30–50 cm, shaded side) — not the screen's floor — so the
board's charging-time dissipation (~0.1–0.3 W) can't plume into the louvre intake.
The box's connector face points down: GX bulkheads (solar GX12-2, rain GX12-3, masthead
GX16-5) + two glands for the fixed screen pigtails (Board B XH-5, PMS XH-4).
See architecture §6 and boards/board-a-core.md §6a.
