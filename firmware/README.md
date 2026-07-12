# Forsyth firmware

Two programs and one contract:

| | |
|---|---|
| [`PROTOCOL.md`](PROTOCOL.md) | **Read this first.** The wire contract: LoRa binary frames (leaf ↔ coordinator) and MQTT JSON (coordinator → cloud). Authoritative over both implementations. |
| [`leaf/`](leaf/) | ATtiny3226 on Board A — bare-metal C, avr-gcc. Sleeps at µA, wakes for wind buckets, rain tips, lightning IRQs, and a radio burst every few minutes. All tuning in `leaf/src/config.h`. |
| [`coordinator/`](coordinator/) | ESP32-S3 (Waveshare mini) — MicroPython. Always-on: decodes frames, timestamps, publishes to the droplet's MQTT broker, ACKs with piggybacked leaf config. All knobs in `coordinator/src/config.py`. |

Written 2026-07-13 against Board A REV0 (pre-fab) — **bench-untested**: it
compiles against the datasheets and the reviewed schematic, but no hardware
existed yet when it was written. The bring-up checklists in each README are
the path from "compiles" to "trusted"; expect the `[B]`-marked calibration
knobs and the register-level driver corners (ADC timebase, AS3935 tuning,
E220 NVRAM echo) to be where bench reality bites first.

Design lineage worth knowing before editing:

- The E220 handling implements the **lokki law** (architecture.md §3) —
  power-gating, atomic M0/M1, two-edge AUX waits, bulk capacitance at the
  module. lokki's `lora_config.py` is the reference implementation; the
  register byte encoding here matches it deliberately.
- The leaf has **no wall clock**; the coordinator timestamps at receipt and
  lightning frames carry their age. Don't add RTC-keeping to the leaf without
  a reason — it's a solved non-problem.
- Rain calibration lives coordinator-side, everything else leaf-side (OTA
  TLVs). PROTOCOL.md explains the asymmetry.
- The cloud side is already deployed and expects exactly the JSON the
  coordinator emits (`cloud/api/app/mqtt_bridge.py`, `ingest.py`). The
  simulator publishes the same shape — flipping a real station live is a
  config entry, not a migration.
