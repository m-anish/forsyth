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
#define WIND_GATE_S         10       /* [C] gust bucket width, seconds. WMO
                                        gust is a 3 s mean; 10 s is the power-
                                        friendly compromise. Continuous
                                        back-to-back buckets, no dead time.   */
#define ANEMO_MS_PER_HZ_X1000 2400   /* [E 0x06][B] m/s per pulse-Hz ×1000.
                                        2.400 is the Davis-style cup default;
                                        CALIBRATE: drill-spin at known RPM or
                                        drive-by against a phone anemometer.  */
#define ANEMO_MIN_EDGE_MS   4        /* [C] ISR-level noise gate; the board RC
                                        (τ≈7 ms vs internal pull-up) already
                                        rounds edges — see board-a §6 item 5  */

/* ================= rain ================================================= */
#define RAIN_DEBOUNCE_MS    150      /* [C] min gap between tips; a real bucket
                                        can't cycle faster                    */
/* mm-per-tip deliberately lives on the COORDINATOR (per-station config) —
 * the leaf ships raw cumulative tips. See PROTOCOL.md reading bit6.          */

/* ================= wind vane LUT ======================================== */
/* Ratiometric ladder (excitation = VDD = ADC ref, so battery voltage
 * cancels). 12-bit ADC centers computed from the Board D candidate resistor
 * set — board-d-wind.md says in bold: DO NOT TRUST THIS TABLE, measure every
 * sector on the bench and paste the measured centers here. [B]
 * Classification: nearest center wins if within ±VANE_WINDOW counts.
 * The NW+N wrap pair collides with N (the documented ladder wart) — its entry
 * ships disabled; enable it only if you re-ordered the ladder on the bench.  */
#define VANE_LUT_SIZE 16
#define VANE_WINDOW   60             /* [B] ± ADC counts; half the smallest
                                        measured gap, minus margin            */
#define VANE_DEG_DISABLED 0xFFFF
typedef struct { uint16_t adc; uint16_t deg_x10; } vane_entry_t;
#define VANE_LUT_DEFAULT { \
    {  262, 225  },  /* N+NE  22.5° */ \
    {  369, VANE_DEG_DISABLED }, /* NW+N 337.5° — collides with N, disabled */ \
    {  373, 0    },  /* N      0.0° */ \
    {  504, 675  },  /* NE+E  67.5° */ \
    {  737, 450  },  /* NE    45.0° */ \
    {  815, 1125 },  /* E+SE 112.5° */ \
    { 1151, 900  },  /* E     90.0° */ \
    { 1241, 1575 },  /* SE+S 157.5° */ \
    { 1659, 1350 },  /* SE   135.0° */ \
    { 1790, 2025 },  /* S+SW 202.5° */ \
    { 2232, 1800 },  /* S    180.0° */ \
    { 2457, 2475 },  /* SW+W 247.5° */ \
    { 2818, 2250 },  /* SW   225.0° */ \
    { 3161, 2925 },  /* W+NW 292.5° */ \
    { 3378, 2700 },  /* W    270.0° */ \
    { 3781, 3150 },  /* NW   315.0° */ \
}
#define VANE_ADC_SAMPLES 8           /* [C] median-of-N per read              */

/* ================= temperature / humidity =============================== */
#define SHTC3_TEMP_OFFSET_X100  0    /* [E 0x04][B] added to SHTC3 °C ×100.
                                        Calibrate against a reference
                                        thermometer inside the screen.        */
#define MCU_TEMP_OFFSET_X100    0    /* [B] trim for the internal sensor that
                                        drives the charge policy; the factory
                                        sigrow cal is ±3 °C — bench-check it  */

/* ================= battery & power policy ================================ */
#define VBAT_DIV_NUM        4030     /* [B] divider ratio ×1000. Nominal
                                        (1 M + 330 k)/330 k = 4.0303; measure
                                        your actual resistors and update.     */
#define BATT_LOW_MV         2900     /* [C] below: skip PMS7003 runs          */
#define BATT_CRIT_MV        2800     /* [C] below: hibernate — no TX, wake
                                        every 10 min to re-check. (Hardware
                                        BMS parachute cuts at ~2.40 V.)       */
#define BATT_HIBERNATE_RECHECK_S 600 /* [C]                                   */

/* Charge-inhibit policy (PA3 → 2N7002 → CN3801 MPPT). LiFePO4 must not be
 * charged below 0 °C. Fail-safe is charge-ON (100 k pulldown), so on any
 * doubt — sensor fault, mode auto with no reading — we DEASSERT.            */
#define CHG_MODE_AUTO       0
#define CHG_MODE_INHIBIT    1
#define CHG_MODE_ALLOW      2
#define CHG_POLICY_MODE     CHG_MODE_AUTO  /* [E 0x05] */
#define CHG_LOW_LIMIT_C     0        /* [E 0x05] inhibit below this °C        */
#define CHG_HYSTERESIS_C    2        /* [E 0x05] release at limit + hyst      */

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
#define SAFE_MODE_INTERVAL_S 30
#define SAFE_MODE_DURATION_S 600

/* ================= EEPROM config store =================================== */
#define CFG_MAGIC           0xF57C
#define CFG_VERSION         1        /* bump to force EEPROM re-init on flash */

#endif
