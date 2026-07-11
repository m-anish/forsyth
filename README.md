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

## Where things live

| Path | What |
|---|---|
| [`site/`](site/) | Marketing/landing site (Cloudflare Pages → forsyth.starstucklab.com) |
| [`cloud/`](cloud/) | The cloud side: ingest API + multi-station dashboard + timelapse worker (docker compose, one small VPS) — see [cloud/docs/deploy.md](cloud/docs/deploy.md) |
| [`hardware/architecture.md`](hardware/architecture.md) | Block-level architecture, power gating discipline, payload schema, layout notes |
| [`hardware/BOM.md`](hardware/BOM.md) | First-pass BOM with India sourcing and pricing |
| [`hardware/enclosures/`](hardware/enclosures/) | Onshape exports land here (placeholder) |
| [`research/competitive-landscape.md`](research/competitive-landscape.md) | Market survey + datasheet numbers, sourced and dated |

## Status

**Station 000 · Expecting rain.** There are currently zero Forsyth stations on any mast.
There is a design, a bill of materials, a power budget methodology, and a workbench in
the lower Himalayas. Firmware and PCB layout come next; the PCB is designed by hand in
KiCad (deliberately not generated), and enclosures in Onshape.

The **cloud platform runs ahead of the hardware**: `cloud/` stands up the full pipeline
(ingest → TimescaleDB → dashboard → Weather Underground → daily sky timelapses) with
three simulated stations rehearsing plausible Himalayan weather, so the day the first
real leaf speaks, somewhere is already listening.

## Family

Part of [starstucklab](https://starstucklab.com) — building small machines for an
indifferent universe. Sibling machines: [jigawatt](https://github.com/m-anish/jigawatt)
(disagrees with lightning), [lokki](https://github.com/m-anish/lokki) (coordinated light),
[Sirious](https://github.com/m-anish/sirious) (a finderscope with opinions).
