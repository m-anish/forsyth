/* config.h — every tunable in the leaf firmware lives in this one file.
 *
 * Three kinds of knob, marked in each section:
 *   [C]  compile-time only — changing it means reflash.
 *   [E]  compiled default, overridable over the air (ACK TLVs, PROTOCOL.md §2)
 *        and persisted in EEPROM. The EEPROM copy WINS after first boot; a
 *        reflash alone does not reset it — send TLV 0x7F or bump CFG_VERSION.
 *   [B]  bench-calibration value — the compiled number is a starting point,
 *        the bench measurement is the truth. Marked with what to measure.
 *
 * A future agent doing a hardware tweak should grep this file first; if the
 * tweak isn't representable here, extend this file rather than burying a
 * constant in a driver.
 */
#ifndef FORSYTH_CONFIG_H
#define FORSYTH_CONFIG_H

#include <stdint.h>

#define FW_VERSION          0x0100   /* BCD, reported in STATUS packets */

/* ================= identity & radio (must match coordinator) ============= */
#ifdef STATION_ID_OVERRIDE           /* set per-leaf from the Makefile:      */
#define STATION_ID STATION_ID_OVERRIDE  /* make STATION_ID=2 && make flash   */
#else
#define STATION_ID          1        /* [C] unit_id 1–255; = E220 ADDL and the
                                        id the coordinator maps to a slug.
                                        UNIQUE per leaf — set before flashing. */
#endif
#define LORA_CHANNEL        15       /* [C] 850.125+CH MHz → 865.125 MHz.
                                        India NFAP band 865–867: CH 15–16 ONLY. */
#define LORA_TX_POWER_DBM   22       /* [C] 22/17/13/10 valid for T22D        */
#define LORA_AIR_RATE       2400     /* [C] bps; see PROTOCOL.md §1           */
#define LORA_CRYPT_H        0x0F     /* [C] fleet-wide scrambling key —       */
#define LORA_CRYPT_L        0x57     /*     must equal the coordinator's      */

/* ================= cadence ============================================== */
#define REPORT_INTERVAL_S   300      /* [E 0x01] reading + TX every N s       */
#define AQI_EVERY_N_REPORTS 6        /* [E 0x02] PMS7003 runs every Nth report
                                        (0 = never). Each run costs ~0.67 mAh
                                        ≈ 35 LoRa bursts — the most expensive
                                        thing this firmware does.             */
#define ACK_WAIT_MS         1500     /* [C] RX window after TX; the only
                                        downlink opportunity per cycle        */
#define TX_RETRIES          1        /* [C] extra TX attempts when no ACK     */
#define LIGHTNING_IMMEDIATE_TX 1     /* [C] 1 = strikes wake the radio at once;
                                        0 = ride along with the next reading  */
#define LIGHTNING_QUEUE     4        /* [C] events buffered between TX chances */

/* ================= wind ================================================= */
#define WIND_PARTIAL_MIN_S  3        /* [C] shortest trailing partial gate that
                                        may set the gust. WMO's gust is a 3 s
                                        mean; below that a single stray pulse
                                        in a 1 s remainder would report a
                                        0.67 m/s gust out of nothing.          */
#define RADIO_BOOST_DELAY_MS 25     /* [C] quiet gap between reset and
                                        raising TPS61023 EN for the E220's
                                        5 V rail.
                                        At reset the MCU's own start-up pulls
                                        VDD down; stacking the boost's inrush
                                        (charging 100-220 uF) on top of that
                                        is what a 2.6 V BOD trips on, and the
                                        reset that follows repeats it
                                        forever. A few tens of ms lets VDD
                                        come back before the rail is asked
                                        for anything.
                                        Raised at BOOT and then left up, so
                                        the boost, the cap and the module all
                                        settle during sensor init instead of
                                        in front of the first transmit. The
                                        module is idle (~10-15 mA) for that
                                        extra ~0.5 s, once per boot only —
                                        radio_off() still drops the rail at
                                        the end of the session and later
                                        sessions power it on demand.
                                        REPLACED RADIO_SETTLE_MS (400 ms
                                        before the TX burst), which was the
                                        same idea aimed at the wrong moment
                                        and measured as not helping.        */
#define WIND_GATE_S         10       /* [C] gust bucket width, seconds. WMO
                                        gust is a 3 s mean; 10 s is the power-
                                        friendly compromise. Continuous
                                        back-to-back buckets, no dead time.   */
#define ANEMO_MS_PER_HZ_X1000 333    /* [E 0x06] m/s per CLOSURE-Hz ×1000.
                                        SparkFun SEN-15901 / Fine Offset cup
                                        set. This counts reed CLOSURES, which
                                        is the distinction the value turns on.
                                        WAS 2400, a Davis-style cup default,
                                        which over-reported by 3.6x (it read
                                        the datasheet's 2.4 as m/s, not km/h).
                                        THEN 667, from the English text's "a
                                        wind speed of 2.4 km/h causes the
                                        switch to close once per second"
                                        (2.4 km/h = 0.667 m/s), with the
                                        Chinese text's 0.33 m/s per closure
                                        dismissed as wrong because the rotor
                                        was believed to close the reed once
                                        per revolution. That belief was the
                                        error, and the 2026-10-31 check that
                                        produced it was mistaken.
                                        MEASURED 2026-11-06 with DIAG_WIND:
                                        the LED blinks TWICE per revolution,
                                        180 degrees apart — two magnets, two
                                        closures per turn. That reconciles the
                                        datasheet instead of contradicting it:
                                        0.667 m/s per REVOLUTION-Hz and two
                                        closures per revolution IS 0.333 m/s
                                        per closure-Hz, so both texts describe
                                        the same meter and the English one is
                                        loose about what "once" counts.
                                        Everything this leaf has ever reported
                                        is therefore 2x high; see
                                        firmware/leaf/README.md before
                                        comparing old data with new.
                                        Still open: the CUP aerodynamics,
                                        which only a side-by-side against a
                                        reference anemometer in steady wind
                                        can check [B]. TLV 0x06 makes that a
                                        message, not a ladder trip.          */
#define ANEMO_MIN_EDGE_MS   4        /* [C] ISR-level noise gate; the board RC
                                        (τ≈7 ms vs internal pull-up) already
                                        rounds edges — see board-a §6 item 5  */

/* ================= rain ================================================= */
#define RAIN_DEBOUNCE_MS    150      /* [C] min gap between counted tips, in
                                        ~1 ms RTC ticks (the counter runs at
                                        1024 Hz, so 150 is really ~146 ms).
                                        MEASURED 2026-10-31 with DIAG_PULSE:
                                        one hand-tip of the real bucket gives
                                        exactly one counted tip, so 146 ms
                                        already outlasts this bucket's rock.
                                        Caveat worth keeping: a hand-tip is
                                        GENTLER than a water-driven one, which
                                        snaps over harder and may rock more —
                                        so this is validated for the bench, not
                                        yet for rain. If field totals ever read
                                        high, re-run DIAG_PULSE under a tap
                                        before suspecting the gauge.
                                        Raising it is nearly free: at
                                        0.2794 mm/tip even a violent 300 mm/h
                                        downpour is one tip every 3.4 s, so
                                        anything up to ~1 s still cannot clip
                                        real rain. 300 is the usual answer if
                                        doubles ever appear.                 */
/* mm-per-tip deliberately lives on the COORDINATOR (per-station config) —
 * the leaf ships raw cumulative tips. See PROTOCOL.md reading bit6.          */

/* ================= wind vane LUT ======================================== */
/* Argent/SparkFun-style 16-position vane (SparkFun SEN-15901 / Fine Offset,
 * datasheet DS-15901): ONE reed-switched resistor to ground per position,
 * 688 R … 120 k. All 16 are distinguishable — it is not Board D's ladder and
 * has none of its wrap-around wart. Wiring is the datasheet's own example
 * circuit, mapped onto Board A's J3:
 *
 *   J3.1 VBAT ── vane ──┬── J3.3 VANE_ADC ── R17 1 k ── PA6
 *                       ├── R_DIV 7.5 k 1 % ── GND   (fit at the connector)
 *                       └── C 100 nF + SMAJ5.0A (already on Board A)
 *
 * Ratiometric: the excitation is VBAT and the ADC reference is VDD = VBAT, so
 * the cell voltage cancels exactly and the code is a pure resistance ratio.
 * R17 carries no DC drop (PA6 is nA-class), so it does not enter the maths.
 *
 * Why 7.5 k: the divider cannot be linear across a 175:1 resistance span, so
 * the value maximises the SMALLEST gap between adjacent codes rather than
 * centring the range. The binding pair is always E (1.00 k) / ENE (891 R) —
 * 11 % apart in resistance and high on the curve where it is most compressed.
 * 7.5 k gives 46 counts there, ~3x the tolerance + ADC-noise stack, at ~223 µA
 * averaged over the 16 positions. Nothing gates the excitation (see the
 * README's "known hardware quirk"), so finer resolution is bought with current
 * we never stop paying: 4.7 k would spend +36 % average current for 19 counts
 * nobody reads. 6.8 k and 4.7 k are drop-in if the drawer changes.
 *
 * THE TABLE BELOW IS BENCH-MEASURED, not computed [2026-10-31]. The eight
 * single-reed positions were read off the real vane on the real board. The
 * eight between-reed positions close TWO adjacent reeds at once, putting those
 * resistors in parallel (datasheet, final paragraph), so their codes are
 * derived from the measured neighbours by the parallel identity in ratio
 * space: with x = R_vane/R_DIV = (4095-code)/code, the pair is
 * x_ab = x_a*x_b/(x_a+x_b) and code = 4095/(1+x_ab). R_DIV cancels, so the
 * derived entries inherit the measurement's calibration exactly and no
 * resistor value is assumed anywhere in this table.
 *
 * Measured vs the datasheet prediction at a nominal 7.5 k: +5 to +8 counts
 * across all eight, i.e. an implied R_DIV of ~7.59 k — the fitted resistor
 * reading ~1.2 % high, comfortably inside 1 % part tolerance plus the vane's
 * own. A uniform offset like that is the signature of a healthy divider; a
 * scattered one would mean a bad reed or a cable fault.
 *
 * To re-cut after refitting a different pulldown: either rotate the vane and
 * paste fresh numbers, or set VANE_DIV_R_OHMS and regenerate from the
 * datasheet resistances with VANE_CODE() (kept below for exactly that, and
 * for the 8 intermediates if you only measure the cardinals again).          */
#define VANE_LUT_SIZE 16
#define VANE_DIV_R_OHMS 7500UL       /* [C] nominal value of the fitted part.
                                        NOT used by the measured table below —
                                        it only feeds VANE_CODE() when you
                                        regenerate from datasheet resistances */
#define VANE_CODE(rv) ((uint16_t)((4095UL * VANE_DIV_R_OHMS) \
                                  / (VANE_DIV_R_OHMS + (rv))))
#define VANE_WINDOW   23             /* [B] ± ADC counts. Half the smallest gap
                                        (E/ENE, 46 counts); every other gap is
                                        ≥90, so that one pair sets the knob.   */
#define VANE_DEG_DISABLED 0xFFFF     /* no position needs it on this vane      */
typedef struct { uint16_t adc; uint16_t deg_x10; } vane_entry_t;
/* Sorted by code (cosmetic — vane_lookup is a linear nearest-center scan).   */
#define VANE_LUT_DEFAULT { \
    {  247, 2700 },  /* W   270.0°  measured  120 k  */ \
    {  430, 3150 },  /* NW  315.0°  measured  64.9 k */ \
    {  629, 2925 },  /* WNW 292.5°  derived   42.12k */ \
    {  766,    0 },  /* N     0.0°  measured  33 k   */ \
    { 1056, 3375 },  /* NNW 337.5°  derived   21.88k */ \
    { 1313, 2250 },  /* SW  225.0°  measured  16 k   */ \
    { 1429, 2475 },  /* WSW 247.5°  derived   14.12k */ \
    { 1962,  450 },  /* NE   45.0°  measured  8.2 k  */ \
    { 2190,  225 },  /* NNE  22.5°  derived   6.57 k */ \
    { 2699, 1800 },  /* S   180.0°  measured  3.9 k  */ \
    { 2892, 2025 },  /* SSW 202.5°  derived   3.14 k */ \
    { 3174, 1350 },  /* SE  135.0°  measured  2.2 k  */ \
    { 3453, 1575 },  /* SSE 157.5°  derived   1.41 k */ \
    { 3619,  900 },  /* E    90.0°  measured  1.0 k  */ \
    { 3665,  675 },  /* ENE  67.5°  derived   891 R  */ \
    { 3755, 1125 },  /* ESE 112.5°  derived   688 R  */ \
}
/* Fault signatures the ±window catches for free: an open cable or a vane
 * between reeds reads ~0 (R_DIV alone pulls the node down), a shorted one
 * reads 4095 — both are hundreds of counts from any center, so they raise
 * FLP_F_VANE_FAULT instead of silently reporting W or ESE.                   */
#define VANE_ADC_SAMPLES 8           /* [C] median-of-N per read              */

/* ================= temperature / humidity =============================== */
#define SHTC3_TEMP_OFFSET_X100  0    /* [E 0x04][B] added to SHTC3 °C ×100.
                                        Calibrate against a reference
                                        thermometer inside the screen.        */
#define MCU_TEMP_OFFSET_X100    0    /* [B] trim for the internal sensor that
                                        drives the charge policy; the factory
                                        sigrow cal is ±3 °C — bench-check it  */

/* Cross-check between the two temperature sources, when Board B carries both.
 * env_read()'s priority stack gives temp_c to the SHTx whenever it answers and
 * throws the BMx280's reading away — right by default (better part, and CRC'd)
 * but it means a drifting-yet-responsive SHTx silently beats a healthy BME280.
 * Both numbers are already in hand, so the leaf ships the signed difference
 * (SHTx - BMx280) when it gets large, on reading mask bit 14.
 *
 * 3.00 °C [C]: comfortably outside the two parts' combined spec error — SHTC3
 * ±0.2 °C typ / ±0.8 worst, BME280 ±0.5 typ / ±1.0 worst, so ~1.8 °C even if
 * both are at their limits and opposite — while still tight enough to catch a
 * part that has actually gone wrong. Lower it and normal part-to-part spread
 * starts crying wolf; raise it much and you stop catching slow drift.
 * Not OTA-settable: it is a fault threshold, not a calibration, and the
 * verbose knob already streams the raw delta when you want to watch it.      */
#define ENV_TEMP_DIVERGE_X100 300

/* ================= battery & power policy ================================ */
#define VBAT_DIV_NUM        4030     /* [B] divider ratio ×1000. Nominal
                                        (1 M + 330 k)/330 k = 4.0303; measure
                                        your actual resistors and update.     */
#define BATT_LOW_MV         2900     /* [C] below: skip PMS7003 runs          */
#define BATT_CRIT_MV        2800     /* [C] below: hibernate — no TX, wake
                                        every 10 min to re-check. (Hardware
                                        BMS parachute cuts at ~2.40 V.)       */
#define BATT_HIBERNATE_RECHECK_S 600 /* [C]                                   */

/* --- battery taper -------------------------------------------------------
 * Without this the leaf reports at full cadence right up to BATT_CRIT_MV and
 * then stops dead: the two thresholds above are a cliff, not a ramp, and by
 * 2.90 V a LiFePO4 cell is holding single-digit percent. The taper multiplies
 * the report interval as the cell empties, trading resolution for the days
 * that might reach the next sunny spell.
 *
 * On LiFePO4 the voltage is a poor fuel gauge — the 3.30–3.20 V plateau spans
 * most of the usable charge — so these thresholds sit deliberately LATE, in
 * the region where the curve finally has a slope worth reading. Rough SoC at
 * a low discharge rate: 3.15 V ≈ 20–25 %, 3.05 V ≈ 8–12 %, 2.95 V ≈ 3–5 %.
 * [B] Re-cut them against a real discharge curve for the cell in service —
 * an 18500 sold as 1500 mAh is typically ~1100, and a tired one less.
 *
 * The multiplier applies to REPORT_INTERVAL_S, so AQI (every Nth report) and
 * the ACK downlink window slow down with it — one knob moves the whole duty
 * cycle. Safe mode ignores the taper: a human at the box wants answers now.
 * Reported implicitly — the cloud has batt_mv in every reading and can derive
 * the step; no protocol change, no spare flag bit needed (all 8 are taken).  */
#define BATT_TAPER_ENABLE   1        /* [C] 0 = old cliff behaviour           */
#define BATT_TAPER_HYST_MV  40       /* [C] must clear a threshold by this
                                        much to step back up — stops a cell
                                        sagging under TX from oscillating     */
#define BATT_TAPER_TABLE { \
    { 3150, 2 },   /* ≈20–25 % left: half cadence                            */ \
    { 3050, 4 },   /* ≈8–12 %                                                */ \
    { 2950, 8 },   /* ≈3–5 %: 5 min → 40 min, just above BATT_LOW_MV         */ \
}

/* Charge-inhibit policy (PA3 → 2N7002 → CN3801 MPPT). LiFePO4 must not be
 * charged below 0 °C. Fail-safe is charge-ON (100 k pulldown), so on any
 * doubt — sensor fault, mode auto with no reading — we DEASSERT.            */
#define CHG_MODE_AUTO       0
#define CHG_MODE_INHIBIT    1
#define CHG_MODE_ALLOW      2
#define CHG_POLICY_MODE     CHG_MODE_AUTO  /* [E 0x05] */
#define CHG_LOW_LIMIT_C     0        /* [E 0x05] inhibit below this °C        */
#define CHG_HYSTERESIS_C    2        /* [E 0x05] release at limit + hyst      */
/* Plausibility window for the internal sensor. Outside it the reading is not
 * weather, it is a broken measurement — the policy then ALLOWS charging,
 * which is the documented fail-safe direction and what the 100 k pulldown
 * does anyway. Wider than the part's -40..+105 °C rating on purpose: this is
 * a garbage detector, not a spec check. Symptom it exists to prevent: a
 * mis-scaled sigrow calculation reading hundreds of degrees below zero and
 * silently refusing to charge in full sun.                                 */
#define MCU_TEMP_SANE_MIN_X100 (-5000)   /* [C] −50 °C */
#define MCU_TEMP_SANE_MAX_X100 ( 12500)  /* [C] +125 °C */

/* ================= AS3935 lightning ====================================== */
#define AS3935_I2C_ADDR     0x03     /* [C] DFRobot SEN0290 selector: 1/2/3.
                                        Verify the module's switch position.  */
#define AS3935_AFE_OUTDOOR  1        /* [E 0x03] 1 = outdoor gain (we are)    */
#define AS3935_NOISE_FLOOR  2        /* [E 0x03] 0–7. Raise if noise ints
                                        flood (watch ltg_stats in readings);
                                        every step costs real sensitivity.    */
#define AS3935_WATCHDOG     2        /* [E 0x03] 0–10. Higher = fewer false
                                        events from switchers, less range.
                                        Bench check: run a radio TX cycle and
                                        confirm no disturber storm.           */
#define AS3935_SPIKE_REJ    2        /* [E 0x03] 0–11. Same trade as WDTH but
                                        for spike shape.                      */
#define AS3935_MIN_STRIKES  0        /* [E 0x03] code 0..3 → 1/5/9/16 strikes
                                        before first IRQ of a storm           */
#define AS3935_MASK_DISTURBERS 1     /* [E 0x03] 1 = don't interrupt on
                                        disturbers (we count them via stats
                                        polling instead)                      */
#define AS3935_TUNING_CAP   0        /* [B] 0–15 (×8 pF). Antenna must resonate
                                        at 500 kHz ±3.5 %. Run the bring-up
                                        LCO tune (README §bring-up) and put
                                        the winning value here.               */

/* ================= PMS7003 =============================================== */
#define PMS_WARMUP_S        30       /* [C] datasheet: data stable ≥30 s after
                                        fan start. Don't shave this.          */
#define PMS_SAMPLES         5        /* [C] frames averaged per run           */
#define PMS_FRAME_TIMEOUT_MS 3000    /* [C] give-up per frame                 */

/* ================= diagnostics =========================================== */
#define VERBOSE_DEFAULT     1        /* [E 0x07] include vane_adc + mcu_temp in
                                        readings. Leave ON until the vane LUT
                                        and charge policy are field-proven.   */

/* ================= service button (PB4) ================================= */
#define BTN_DEBOUNCE_MS     20
#define BTN_LONG_PRESS_MS   3000     /* short press: reading + TX now.
                                        long press: safe mode — compiled
                                        defaults, 30 s interval, for 10 min.  */
#define BTN_STUCK_MAX_S     12       /* cap on the debounced release wait, so a
                                        shorted/stuck line can't spin forever   */
#define BTN_RESET_HOLD_S    5        /* hold this long -> hard reset (re-detects
                                        sensors, incl. the boot-only AS3935)    */
#define SAFE_MODE_INTERVAL_S 30
#define SAFE_MODE_DURATION_S 600

/* ================= EEPROM config store =================================== */
#define CFG_MAGIC           0xF57C
#define CFG_VERSION         1        /* bump to force EEPROM re-init on flash */

#endif
