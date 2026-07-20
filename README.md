# forsyth

![status](https://img.shields.io/badge/status-planning-7fa2c4)
![nodes](https://img.shields.io/badge/stations_deployed-000-lightgrey)
![radio](https://img.shields.io/badge/radio-LoRa_868MHz_(E22)-blue)
![power](https://img.shields.io/badge/power-solar_%2B_LiFePO4-forestgreen)
![cloud](https://img.shields.io/badge/uplink-self--hosted_%2B_WU-9cf)

*The relative who always knew it would rain.*

Forsyth is a low-power, solar-capable **weather station mesh**: small "leaf" nodes
scattered across kilometres of terrain measure wind speed and direction, rain,
temperature, pressure, humidity, particulates (AQI), and lightning — then murmur their
readings over LoRa to a **coordinator** that pushes everything to a self-hosted dashboard
and Weather Underground.

A [starstucklab](https://starstucklab.com) project. Site:
[forsyth.starstucklab.com](https://forsyth.starstucklab.com)

## What it does

- **Leaves**: one ATtiny3226, one E22 LoRa module, one LiFePO4 cell, a hand-sized solar
  panel, and whichever senses the site needs. Asleep at microamps almost always;
  everything power-gated off between readings — including the radio.
- **Coordinator**: an ESP32-S3 with an internet connection and, consequently,
  responsibilities. Listens for every leaf, timestamps on receipt, uploads.
- **Mesh, not a backyard**: private point-to-multipoint LoRa (not LoRaWAN — documented
  decision), designed to sprawl across a valley. More ground? Add leaves.
- **No lock-in**: your data lands on your server, plus Weather Underground for the
  neighbours.

## How the forecasting works — in one screen

The live dashboard ([live.forsyth.starstucklab.com](https://live.forsyth.starstucklab.com))
is not a display of model output; it is an argument between three sources, refereed in
public. Full detail, with every threshold and the reasoning behind each decision, in the
**[forecasting white paper](cloud/docs/forecasting-whitepaper.md)**.

**Sources** — (1) the mesh's own stations (cheap sensors, trusted for *tendencies and
density*, never for absolute calibration); (2) free global models via Open-Meteo — ECMWF,
GFS, ICON and a GEFS ensemble, pulled every 3 h per station and **archived forever
alongside what actually happened**; (3) quality-controlled human reports (hail, fog,
snow line, blocked roads — the things no affordable sensor measures). Himachal has
little usable radar at valley scale; the design assumes none and improves with any.

**The "algorithm"** — deliberately not a weather model. A 3–50 station mesh cannot
out-model ECMWF, so it does four things models can't:
1. **Verify in public**: every forecast hour is scored against the stations
   (`/skill`: bias, MAE, rain hit/false-alarm rates by lead time) and the record is
   shown on every station page.
2. **Detect divergence**: when live observations contradict the model's *now* —
   unforecast rain, pressure crashing faster than modeled — that disagreement is
   itself the warning. *Trust the sky, not the model.*
3. **Weigh human eyes**: reports are cross-checked against the nearest station;
   reporters who prove reliably right become trusted observers whose word alone can
   raise the banner.
4. **Accumulate the dataset**: two years of (forecast, local truth) pairs per station
   is the substrate for statistical correction — and doesn't exist anywhere else for
   these valleys.

**Outputs** — a one-sentence banner in four tenses (observed / expected / divergent /
human-reported, EN + हिंदी, freshness-stamped), per-station forecast charts with
ensemble uncertainty and the model's local track record, map layers (stations,
lightning, reports), and open CSV/API for everything.

**Next** (see the [insight](cloud/docs/insight-roadmap.md) and
[engagement](cloud/docs/engagement-roadmap.md) roadmaps): MQTT divergence alerts,
per-station bias correction once ~90 days of real pairs exist, camera-based sky
reading plus a ₹400 zenith thermopile for night clouds, and IMD warnings as an
overlay (API key in progress).

## Where things live

| Path | What |
|---|---|
| [`site/`](site/) | Marketing/landing site (Cloudflare Pages → forsyth.starstucklab.com) |
| [`cloud/`](cloud/) | The cloud side: ingest API + multi-station dashboard + timelapse worker (docker compose, one small VPS) — see [cloud/docs/deploy.md](cloud/docs/deploy.md) |
| [`cloud/docs/forecasting-whitepaper.md`](cloud/docs/forecasting-whitepaper.md) | **How the forecasting works** — sources, method, thresholds, reasoning, limitations, roadmap; written to be critiqued |
| [`firmware/`](firmware/) | Leaf firmware (ATtiny3226, bare-metal C) + coordinator (ESP32-S3, MicroPython) + the [FLP wire protocol](firmware/PROTOCOL.md) between them |
| [`hardware/architecture.md`](hardware/architecture.md) | Block-level architecture, power gating discipline, payload schema, layout notes |
| [`hardware/BOM.md`](hardware/BOM.md) | First-pass BOM with India sourcing and pricing |
| [`hardware/enclosures/`](hardware/enclosures/) | Onshape exports land here (placeholder) |
| [`research/competitive-landscape.md`](research/competitive-landscape.md) | Market survey + datasheet numbers, sourced and dated |

## Status

**Station 000 · Expecting rain.** There are currently zero Forsyth stations on any mast.
There is a design, a bill of materials, a power budget methodology, firmware for both
ends of the LoRa link (bench-untested, written against the reviewed REV0 schematic),
and a workbench in the lower Himalayas. Board A REV0 layout is in its final pre-fab
pass; the PCB is designed by hand in EasyEDA (deliberately not generated), and
enclosures in Onshape.

The **cloud platform runs ahead of the hardware**: `cloud/` stands up the full pipeline
(ingest → TimescaleDB → dashboard → Weather Underground → daily sky timelapses) with
three simulated stations rehearsing plausible Himalayan weather, so the day the first
real leaf speaks, somewhere is already listening.

## Family

Part of [starstucklab](https://starstucklab.com) — building small machines for an
indifferent universe. Sibling machines: [jigawatt](https://github.com/m-anish/jigawatt)
(disagrees with lightning), [lokki](https://github.com/m-anish/lokki) (coordinated light),
[Sirious](https://github.com/m-anish/sirious) (a finderscope with opinions).
