# Board D — wind interface

**Role:** masthead junction. Turns 8 vane reeds + 1 anemometer reed into two clean
signals on one 5-core cable. Fully passive — nothing up here can be killed by weather
except the reeds themselves (₹10 parts).
**Status:** reference sheet v1 (2026-07-11). The ladder value set below is a
**starting point**; the 16-position table must be verified on the bench and the
firmware LUT calibrated from measurements, not from this sheet.

## 1. Wind direction — the resistor ladder

Topology (ratiometric — excitation and ADC reference are both VBAT, so battery
voltage cancels):

```
J1.1 (VBAT excitation) ── R_top 10 k ──┬───────────── J1.3 (VANE_ADC, to Board A)
                                       │
        reed N ── R1 ──┤               ├── C1 100 nF ── GND   (at the cable exit)
        reed NE ── R2 ──┤   … all 8 reeds+resistors
        reed …  ── R… ──┴── common ── GND (J1.2)
```

Each reed shorts its resistor to the bottom of the divider; the vane magnet closes
one reed per 45° sector, or **two adjacent reeds** in between — their parallel value
gives 8 more sectors → 16 directions from one wire, Davis-style.

Candidate set (E12), reading `V/VBAT = R/(R + 10 k)`:

| Sector | R | V/VBAT | Between-sector (‖ pair) | V/VBAT |
|---|---|---|---|---|
| N | 1.0 k | 0.091 | N+NE (0.69 k) | 0.064 |
| NE | 2.2 k | 0.180 | NE+E (1.41 k) | 0.123 |
| E | 3.9 k | 0.281 | E+SE (2.48 k) | 0.199 |
| SE | 6.8 k | 0.405 | SE+S (4.34 k) | 0.303 |
| S | 12 k | 0.545 | S+SW (7.76 k) | 0.437 |
| SW | 22 k | 0.688 | SW+W (15.0 k) | 0.600 |
| W | 47 k | 0.825 | W+NW (33.8 k) | 0.772 |
| NW | 120 k | 0.923 | **NW+N (0.99 k) → 0.090 — collides with N!** |

**Known wart, on purpose:** the wrap-around pair NW+N is indistinguishable from N
alone with any monotone value ordering — the biggest resistor paralleled with the
smallest ≈ the smallest. Options, pick during bench pass: (a) accept 15 usable
sectors (N reads as "N-ish", fine for a weather vane), (b) reorder values around the
compass so the wrap pair lands somewhere distinguishable and re-check *all* 16
spacings, or (c) the AS5600 upgrade path (architecture §2.2) which makes the whole
question obsolete. Firmware uses a calibrated LUT with ±half-gap windows either way.

- All 8 resistors 1 %; R_top 1 %.
- C1 100 nF at the cable exit + the 1 k series resistor lives on **Board A's**
  protection row (so the cable, not the mast board, is what it protects).

## 2. Wind speed — anemometer reed

Reed in series to GND, pulled up by Board A (internal pull-up on `ANEMO`), RC
debounce **on this board**: R9 1 k series + C2 100 nF (τ ≈ 100 µs — bounces die,
20 Hz spins don't). One pulse per rotation; Board A's Event System counts in sleep.
Calibration factor (m/s per Hz) comes from the cup geometry — bench/field job.

## 3. Cable & connector

J1 → one shielded 5-core down the mast to Board A's GX16-5:

| GX16-5 pin | Net |
|---|---|
| 1 | VBAT (ladder excitation) |
| 2 | GND |
| 3 | vane analog |
| 4 | anemometer pulse |
| 5 | cable shield (grounded at Board A only) |

Drip loop at the mast exit; UV-stable cable; the vane/anemometer mount hardware is
Onshape territory.

## 4. Board BOM

| Ref | Part | Note |
|---|---|---|
| SW1–SW8 | glass reed, NO | vane, 45° ring |
| SW9 | glass reed, NO | anemometer |
| R1–R8 | 1.0 k…120 k 1 % | table above |
| R_top | 10 k 1 % | divider top |
| R9 | 1 k | anemo debounce |
| C1, C2 | 100 nF | at cable exit |
| J1 | GX16-5 plug + pigtail | to Board A J3 |

## 5. Bring-up checklist

1. Ohmmeter every sector: rotate a magnet through 360°, log all 16 resistance steps.
2. Power via bench Board A; log ADC counts per sector → firmware LUT (do not trust
   the table above; trust the measurements).
3. Confirm the NW+N decision (§1 wart) with the real vane geometry.
4. Spin test: drill-spin the cups, scope the pulse train after the RC — clean edges,
   no double-counts at any speed.
