# Forsyth radio bring-up — the incremental ladder (and the war stories)

First proven end-to-end **2026-08-05**: leaf (ATtiny3226 + E220) → LoRa →
coordinator (ESP32-S3 + E220) → decoded → MQTT → live.forsyth. Getting there
took most of three sessions, and **almost none of it was firmware or config** —
it was connections and power. This doc captures the diagnostics and the traps so
the next node comes up in an hour, not a week.

## The one rule: isolate one variable at a time

Bring the radio link up as a ladder, each rung adding exactly one thing. Don't
flash the full firmware and hope — you can't tell power from wiring from config
from RF when they fail together.

| Step | What | Tool |
|---|---|---|
| 0 | Both E220s **powered** and answering config reads | `diag/probe_both.py` |
| 1–2 | Two E220s on the coordinator: **no-config loopback**, both ways | `diag/cfg_loop.py` (or `listen_default.py`) |
| 3 | Write matched config, re-test send/recv | `diag/cfg_loop.py` |
| 4 | **Coordinator TX → leaf RX** (leaf receive draws no surge) | leaf `DIAG_LORARX` + `diag/coord_tx.py` |
| 5 | **Leaf TX → coordinator RX** (adds the leaf's TX current surge) | leaf `DIAG_LORATXC` + `diag/coord_rx.py` |

Step 4 before 5 is deliberate: **RX draws no current spike**, so it proves the
RF link + leaf wiring *without* the leaf's TX brownout in the way. Step 4 pass +
Step 5 fail ⇒ it's the leaf's TX supply, not RF.

## Leaf diagnostic builds (compile flags, see `leaf/Makefile`)

- `make DIAG_BOOST=1` — hold the E220 5 V boost on so you can meter the rail.
- `make DIAG_LORARX=1` — real config (`radio_ensure_nvram`) + listen. **LED status:**
  - boot = 2 blinks
  - repeating **5-blink** groups = `radio_on()` failed (power/AUX — can't reach module)
  - repeating **3-blink** groups = config echo mismatch
  - **slow heartbeat** = configured OK, listening
  - **long flash** = received a packet
- `make DIAG_LORATXC=1` — real config + transmit every ~2 s (exercises the TX surge).
- (`DIAG_LORATX=1` is the older *factory-default, no-config* TX — kept, but it does
  NOT match the leaf's real fixed-mode config; prefer `DIAG_LORATXC`.)

Coordinator scripts live in `coordinator/diag/` — copy one to `:main.py` with
mpremote and power-cycle, or `mpremote run` it. They print to the console and
blink the WS2812 (GPIO48): green = clean RX, amber = bytes but garbled (crypt/
mode mismatch), purple = transmitted.

## The production radio config (both ends must match)

Fixed mode, RSSI byte on, **channel 15**, air **2400**, crypt **0x0F57**.
- Leaf address = its `STATION_ID` (ADDL); `radio_tx` prepends `[0x00,0x00,ch]`.
- Coordinator address = **0xFFFF (monitor mode)** so it hears every frame on the
  channel. See `leaf/src/e220.c build_regs` and `coordinator/src/e220.py`.
- The `0xC2` volatile-write reply header varies by module — some echo `0xC1`,
  some `0xC2`. `e220.py` accepts either; the register **payload** is the real proof.

## Traps that cost us days (check these FIRST)

1. **Dead 5 V header pin on cheap DevKitC clones.** The board's "5V" pin had an
   **unbridged factory power-path ("IN–OUT") jumper**, so it delivered ~1.5 V
   (back-fed through the E220's 3.3 V logic pins) while the rail itself was live
   (LDO made 3.3 V, WS2812 lit). Under-powered E220s give exactly the confusing
   `None` / `AUX-low` / one-byte-reply symptoms. **Meter the 5 V pin against a
   known 5 V point (WS2812 +) on every clone.** Bridge the jumper, or run the
   E220 off 3V3 (it's 3.3–5.5 V; lower TX power, fine for bench).
2. **Loose Dupont jumpers.** Every reseat knocked a *different* wire loose
   (E220 UART, AUX, power). **Solder the E220 header** or use short strain-relieved
   links. The wiring isn't the test — it's the noise.
3. **E220 breakout TXD/RXD labels.** Some are host-referenced ("connect your TXD
   here"), not module-referenced — the orientation that works is empirical. If a
   module answers in only one `tx/rx` orientation, wire/config to that. Confirm
   with `diag/probe_both.py` (it tries both).
4. **SerialUPDI flakiness = ground reference.** UPDI needs a solid common ground
   between the dongle and target. Give the dongle a real GND to the board (or
   power the (unloaded) target from the dongle). Don't power the *whole* leaf +
   E220 from the dongle — it can't source the radio current and browns out.
5. **T30D power footgun.** The E220 power register is *relative to module max*:
   `0b00` = 22 dBm on a T22D, **30 dBm on a T30D** — same bits. Leaf config keeps
   `LORA_TX_POWER_DBM 22` which maps to `0b00` (max), so a T30D transmits at 30 dBm
   with no change. **Do NOT "correct" it to `30`** — `pwr_bits()` has no `case 30:`,
   so it falls through to `0b11` = *minimum* power. Add `case 30: return 0b00;`
   first if you ever want the literal value in the config.

## Success looks like

`rx leaf-01  STATUS fw=0100 ... nvram_ok=1 batt=3.66V` in the coordinator log,
`frames: {'leaf-01': 1}` in `/api/status`, and (once the station is registered on
the cloud) the reading on live.forsyth.
