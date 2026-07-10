# Forsyth — Competitive Landscape

**Compiled:** 11 July 2026
**Status:** Planning reference. Prices are indicative retail (USD unless noted) at time of
writing; verify before quoting anywhere. Functional comparison only — no vendor marketing
copy or imagery reproduced.

---

## 1. Why this document exists

Forsyth is a solar-capable, LoRa-meshed weather station: leaf nodes measuring wind
speed/direction, rain, temperature, pressure, humidity, particulates (AQI), and lightning,
reporting to an internet-connected coordinator that pushes to a self-hosted dashboard and
Weather Underground. Before claiming any of that is novel, this document surveys what
already exists — consumer personal weather stations (PWS) and the open-source/hobbyist
mesh-sensor world — and identifies where Forsyth genuinely differs.

---

## 2. Consumer personal weather stations

### 2.1 Davis Instruments Vantage Pro2 / Pro2 Plus

- **What it is:** the reference-grade consumer/prosumer station since the early 2000s.
  Solar-powered integrated sensor suite (ISS) with battery backup; cabled or ~300 m
  wireless link to a console; NIST-traceable sensors; updates every ~2.5 s.
- **Sensors:** temp/humidity in a passive radiation shield, cup anemometer + wind vane
  (wind-tunnel tested to 200 mph; a sonic anemometer option now exists), tipping-bucket
  rain. Optional UV, solar radiation, soil moisture. **No lightning detection, no
  particulates.**
- **Relevant precedent:** Davis's classic anemometer measures wind speed with a **magnet
  sweeping a reed switch — the same pulse-counting approach Forsyth uses**. It is a
  genuinely useful proof that magnet-plus-reed survives decades outdoors on a mast.
- **Price:** roughly $700–900 fully equipped (Pro2 Plus with console). Full-resolution
  data access and API ride on WeatherLink cloud subscription tiers.
- **Architecture:** one station, one backyard. "More coverage" means buying more complete
  stations; there is no mesh concept.
- Sources: [Davis Vantage Pro2 collection](https://www.davisinstruments.com/collections/vantage-pro2),
  [Vantage Pro2 overview](https://www.davisinstruments.com/pages/vantage-pro2),
  [The-Weather.com Vantage Pro2 review, 2026](https://the-weather.com/davis-vantage-pro2-review/)

### 2.2 WeatherFlow Tempest

- **What it is:** the design benchmark for "no moving parts" — a single sealed solar
  unit with sonic anemometer, haptic rain sensor, and (notably) **lightning detection
  to ~40 km**. Real-time updates every ~3 s, ~300 m wireless to its hub. LTO battery
  chemistry for cold tolerance and long cycle life.
- **Sensors:** temp, humidity, pressure, wind (ultrasonic), rain (haptic), UV/solar
  radiation, lightning. **No particulates/AQI.**
- **Price:** ~$329–339.
- **Architecture & lock-in:** one unit + hub; data lives in WeatherFlow's cloud with an
  ML "Nearcast" correction layer. There is a local UDP broadcast and a public API, but
  the product is built around the vendor's cloud, and the haptic rain gauge's accuracy
  depends on their cloud-side corrections. A hub-and-device concept, not a
  geographic mesh you own.
- Sources: [Tempest shop page](https://shop.tempest.earth/products/tempest),
  [Tempest System FAQs](https://help.tempest.earth/hc/en-us/articles/360052101413-Tempest-System-FAQs),
  [The-Weather.com Tempest review, 2026](https://the-weather.com/tempest-weather-system-review/),
  [TechHive review](https://www.techhive.com/article/578636/weatherflow-tempest-review.html)

### 2.3 Ecowitt (Wittboy / WS90 + gateway ecosystem)

- **What it is:** the modular value ecosystem. Wittboy (WS90 7-in-1 sensor + GW2001/GW
  gateway) ~$190–210: sonic wind, haptic rain, temp/humidity/light/UV, solar powered
  with backup batteries, ~100–300 m proprietary 915 MHz RF to the gateway.
- **Expandable:** this is the one consumer system where lightning and AQI are *available*
  — the **WH57 lightning sensor** (AS3935-class, ~40 km range, reports every 79 s) and
  **WH41/WH45 PM2.5** sensors join the same gateway (up to 4 PM sensors per gateway).
  Pushes to Weather Underground, WeatherCloud, Ecowitt's own server; gateways expose a
  usable local API — the least locked-in of the consumer options.
- **Caveats:** each capability is a separate battery-powered accessory around a single
  home gateway; RF range is house-scale, not area-scale. Quality is consumer-grade;
  no NIST traceability story.
- Sources: [Wittboy product page](https://shop.ecowitt.com/products/wittboy-electronic-weather-station),
  [WH57 lightning sensor](https://shop.ecowitt.com/products/wh57),
  [WH41 PM2.5 sensor](https://shop.ecowitt.com/products/wh41),
  [WH45 5-in-1 AQ sensor](https://shop.ecowitt.com/products/wh45),
  [SmartHomeExplorer GW2001 review](https://www.smarthomeexplorer.com/reviews/sensors/ecowitt-wittboy-weather-station-gw2001)

### 2.4 Ambient Weather (WS-2902 / WS-5000)

- **What it is:** the mainstream US brand. WS-2902 (~$170–200) is the entry benchmark:
  cup anemometer, tipping bucket, temp/humidity, solar assist. WS-5000 (~$400+) steps up
  to a sonic anemometer and separately-sited rain gauge, with an add-on sensor ecosystem
  (shares hardware lineage with Ecowitt/Fine Offset).
- **Cloud:** AmbientWeather.net with WU forwarding; app-centric. Same single-backyard
  architecture as the rest.
- Sources: [Ambient Weather comparison chart](https://ambientweather.com/weather-station-comparison-chart),
  [WeatherStationExperts buyer's guide](https://theweatherstationexperts.com/ambient-weather-stations/)

---

## 3. Open-source / hobbyist landscape

### 3.1 LoRa/LoRaWAN weather stations (TTN community, Hackaday)

A well-trodden genre: ESP32 or ATmega + BME280 + solar panel + LoRa radio, reporting to
The Things Network or a private receiver, often onward to Grafana/InfluxDB and sometimes
Weather Underground. Representative examples:

- [Hackaday Prize 2022: solar-powered LoRa weather station](https://hackaday.com/2022/09/22/hackaday-prize-2022-solar-powered-lora-weather-station-for-the-masses/) — ESP32 sender/receiver pair.
- [balena: solar weather station on TTN](https://blog.balena.io/build-a-simple-solar-powered-weather-station-with-lora-the-things-network/) — tutorial-grade single node.
- [henri98/LoRaWAN-Weather-Station](https://github.com/henri98/LoRaWAN-Weather-Station) — BME280 → TTN → Weather Underground.
- [SoLoRa always-on solar node](https://hackaday.io/project/159658-solora-solar-powered-always-on-iot-sensor-node),
  [Weather Pyramid](https://hackaday.io/project/153208-weather-pyramid),
  [32nibbles LoRa solar station](https://www.32nibbles.ca/posts/weatherstation1/).

**Pattern:** almost all are single nodes or tutorials, temp/pressure/humidity-centric.
Wind and rain appear occasionally (usually salvaged commercial anemometers); **lightning
and AQI almost never in the same build**; power engineering (proper charge chemistry,
power-gated radios) is usually the weak point. They are projects, not deployable fleets.

### 3.2 Meshtastic environmental telemetry

Meshtastic firmware auto-detects I2C sensors (BME280 etc.) and broadcasts environment
telemetry over its mesh (default every 30 min); solar rooftop nodes are common.
Genuinely meshed and off-grid — but it's a *communications* project with weather bolted
on: no wind/rain/lightning story, phone-app-centric consumption, and duty cycling is
constrained by the mesh's need to stay awake and route.
Sources: [Meshtastic telemetry module docs](https://meshtastic.org/docs/configuration/module/telemetry/),
[mictronics Meshtastic weather station](https://mictronics.de/posts/Meshtastic-Weatherstation/),
[CreateLabz Heltec weather node](https://createlabz.store/blogs/createlabz-tutorials/heltec-lora-v3-esp32-implement-meshtastic-autonomous-weather-and-water-level-node)

### 3.3 Sensor.Community (ex-Luftdaten) & openSenseMap

Large citizen-science networks (tens of thousands of nodes, mostly Europe) built on
cheap particulate sensors (SDS011, PMS7003) + ESP8266/ESP32 on **home WiFi**, publishing
open data. openSenseMap/senseBox is the education-flavored equivalent.
**Pattern:** stationary, mains/USB-powered, WiFi-tethered AQ monitors — no wind, rain,
or lightning, and no off-grid capability. Strong precedent that PMS7003-class sensors
hold up in continuous outdoor community use.
Sources: [Sensor.Community background](https://www.samenvoorzuiverelucht.eu/en/inspiratie/sensorcommunity),
[openSenseMap overview](https://citizen-assembly.com/citizenscience/opensensemap),
[AQICN PMS5003/7003 evaluation](https://aqicn.org/sensor/pms5003-7003/),
[LoRaWAN city-scale PM monitoring (peer-reviewed)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6339063/)

---

## 4. Datasheet numbers pulled for Phase 4 (recorded here so they're sourced)

From the **Ebyte E22-900T30D user manual** ([cdebyte PDF](https://www.cdebyte.com/pdf-down.aspx?id=1230), fetched 2026-07-11):

| Parameter | E22-900T30D | E22-900T22D |
|---|---|---|
| Operating voltage | 3.3–5.5 V, **"≥5.0 V ensures output power"** | 2.1–5.5 V, "≥3.3 V ensures output power" |
| TX current (typ, instantaneous) | **650 mA** | **140 mA** |
| RX current (typ) | 16 mA | 11 mA |
| Sleep current (typ) | 2 µA | 2 µA |
| Max TX power | 30 dBm | 22 dBm |
| Communication level | **3.3 V** ("for 5 V TTL, add level conversion") | same |
| M0/M1 | inputs, **weak pull-up** — must not float | same |
| AUX | LOW during power-on self-check, HIGH when ready; wait for rising edge | same |

(T22D figures from the [E22-900T22D user manual](https://www.cdebyte.com/pdf-down.aspx?id=1463), same date.)

Notes that feed §5.3 of the project brief directly:

- **2× peak-current rule:** T30D ⇒ design the 5 V rail + LiFePO4 discharge path for
  ≥1.3 A momentary; T22D ⇒ ≥300 mA (clears 500 mA comfortably).
- **Logic levels:** the manual states communication level is 3.3 V independent of VCC and
  only warns about *5 V* TTL hosts — consistent with Ebyte's FAQ; a 3.3 V MCU interfaces
  directly. The manual publishes no numeric Vih/Vil table, so treat "3.3 V logic, no
  shifter needed" as confirmed at manual level, not silicon-threshold level.
- **M0/M1 have weak pull-ups:** left floating, the module drifts to M0=M1=1 = deep
  sleep — the exact boot trap that bit lokki. Drive them, always.

**AS3935 lightning sensor** ([ams datasheet](https://www.sciosense.com/wp-content/uploads/2024/01/AS3935-Datasheet.pdf)):
listening mode 60–80 µA (typ 60 µA); power-down 1–2 µA. It must *stay* in listening mode
to be useful, so ~60–80 µA is a floor under the leaf's sleep budget.

**Plantower PMS7003** ([data manual v2.5](https://download.kamami.pl/p564008-PMS7003%20series%20data%20manua_English_V2.5.pdf)):
4.5–5.5 V supply (fan), ≤100 mA active (~25–50 mA steady, ~80 mA during spin-up), ~30 s
warm-up required after wake for a valid reading. **Energy check:** one AQI reading ≈
80 mA × 30 s ≈ 0.67 mAh; one T30D LoRa burst ≈ 650 mA × ~100 ms ≈ 0.018 mAh. The AQI
warm-up costs roughly **35× more energy than the LoRa transmission** — it, not the radio,
dominates the active-mode budget, as the brief anticipated.

---

## 5. Where Forsyth actually differs

Honest scorecard — "differentiated" only where nothing above already does it:

1. **Lightning + AQI + full met suite in one leaf.** No consumer station ships all
   three integrated (Tempest: lightning but no AQI; Ecowitt: both, but as separate
   accessories on a home gateway; Davis/Ambient: neither). Hobbyist builds almost never
   combine them.
2. **Geographic mesh, not a backyard.** Every consumer product is one station + one
   home hub. Forsyth's leaf/coordinator split over LoRa is designed to scatter nodes
   across kilometers of terrain with one internet uplink. Only Meshtastic offers this
   shape, and it isn't a weather station.
3. **Solar + LiFePO4 autonomy done as engineering, not accessory batteries.** Purpose-
   built charge chemistry (CN3801, 3.625 V float), power-gated radio and AQI sensor,
   µA-level sleep. Tempest is the only consumer comparable, and it's sealed/proprietary.
4. **No vendor lock-in.** Self-hosted dashboard + Weather Underground + your own
   coordinator. Davis paywalls full data behind WeatherLink; Tempest routes through
   its cloud; Ecowitt is closest to open but still gateway-bound.
5. **Repairable and sourceable.** Hand-solderable SOIC/SOP parts, domestic (India)
   availability, documented BOM — none of the consumer units are serviceable in any
   meaningful way.

What Forsyth is **not** claiming: consumer polish, NIST-traceable accuracy (Davis owns
that), no-moving-parts wind sensing (Tempest/WS90 own that — Forsyth deliberately uses
reed switches for repairability), or certified LoRaWAN interop (private point-to-
multipoint by design).

---

## 6. Comparison matrix (used on the site)

| Capability | Forsyth | Davis VP2+ | Tempest | Ecowitt Wittboy+ | Ambient WS-5000 | DIY LoRa builds |
|---|---|---|---|---|---|---|
| Temp / humidity / pressure | ● | ● | ● | ● | ● | ● |
| Wind + rain | ● | ● | ● | ● | ● | ◐ sometimes |
| Lightning detection | ● integrated | ○ | ● | ◐ add-on | ○ | ○ rare |
| Particulates / AQI | ● integrated | ○ | ○ | ◐ add-on | ◐ add-on | ○ rare |
| Solar, off-grid node | ● LiFePO4 | ● (ISS only) | ● | ◐ sensor only | ◐ | ◐ varies |
| Multi-km mesh of nodes | ● LoRa | ○ | ○ | ○ (~100 m RF) | ○ | ◐ Meshtastic only |
| Self-hosted data path | ● | ◐ paywalled | ◐ cloud-first | ◐ local API | ◐ | ● |
| Weather Underground | ● | ● | ● | ● | ● | ◐ |
| Repairable / open BOM | ● | ○ | ○ | ○ | ○ | ● |
| Indicative price | ~₹4.2–6.2k/leaf (parts) | $700–900 | ~$330 | ~$200 + add-ons | ~$400 | varies |

● yes · ◐ partial/with caveats · ○ no

---

*Compiled 2026-07-11 from vendor pages, current datasheets, and community documentation
linked above. Prices and stock move; re-verify before purchasing decisions or public
claims.*
