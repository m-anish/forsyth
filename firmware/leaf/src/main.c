/* main.c — Forsyth leaf node, ATtiny3226.
 *
 * Shape of the firmware: one flat scheduler, no RTOS, no dynamic memory.
 * The MCU sleeps in POWER-DOWN; three things wake it:
 *   - the RTC PIT (1 Hz) — drives wind bucketing and the report timer
 *   - pin edges — anemometer, rain bucket, service button, AS3935 IRQ
 *   - nothing else (both 5 V rails are off between duties)
 * ISRs only count and flag; every I2C/UART/radio action happens in the main
 * loop. If you add a sensor, follow that split or sleep math breaks.
 *
 * Time: there is no wall clock. Uptime seconds + "age" fields in the
 * protocol let the coordinator do the timestamping (PROTOCOL.md §2/§3).
 */
#include <avr/io.h>
#include <avr/interrupt.h>
#include <util/atomic.h>
#include <string.h>

#include "config.h"
#include "pins.h"
#include "hal.h"
#include "protocol.h"
#include "adc.h"
#include "twi.h"
#include "sensors.h"
#include "as3935.h"
#include "pms7003.h"
#include "e220.h"
#include "uart.h"

/* ---------------- ISR-shared state -------------------------------------- */

static volatile uint16_t v_anemo_pulses;    /* pulses this second            */
#ifdef DIAG_WIND
/* Free-running, never cleared, DIAG_WIND only. v_anemo_pulses is drained
 * every second, so it cannot answer "how many did the ISR ever credit?" —
 * which is exactly the number the bucketing has to preserve. The reject
 * counter is the other half: it separates "the ISR never fired" from "the
 * ISR fired and we threw the edge away", and those have different causes. */
static volatile uint32_t v_anemo_total;
static volatile uint32_t v_anemo_rej;
#endif
static volatile uint16_t v_rain_tips;       /* cumulative, wraps (protocol)  */
static volatile uint8_t  v_as3935_flag;
static volatile uint8_t  v_btn_wake;        /* button edge seen — wake & poll */

ISR(PORTA_PORT_vect)
{
    uint8_t flags = PORTA.INTFLAGS;
    PORTA.INTFLAGS = flags;
    uint16_t now = hal_ticks();             /* ~1 tick per ms                */

    if (flags & ANEMO_bm) {
        static uint16_t last;
        if (!(ANEMO_PORT.IN & ANEMO_bm) &&              /* falling edge only */
            (uint16_t)(now - last) >= ANEMO_MIN_EDGE_MS) {
            v_anemo_pulses++;
#ifdef DIAG_WIND
            v_anemo_total++;
#endif
            last = now;
        }
#ifdef DIAG_WIND
        /* the edge reached the ISR but was not credited: either it was the
         * rising half of the closure (expected — BOTHEDGES gives two per
         * revolution and we want one), or the debounce rejected it */
        else v_anemo_rej++;
#endif
    }
    if (flags & RAIN_bm) {
        static uint16_t last;
        static uint32_t last_s;
        /* The RTC tick counter is 16-bit at 1024 Hz, so it wraps every ~64 s.
         * (now - last) is wrap-correct only for gaps SHORTER than that: a tip
         * landing ~64 s (or 128 s, or 192 s…) after the previous one computes
         * a near-zero difference and was silently rejected as a bounce. Real
         * tips are usually minutes apart, so that is a rare but permanent
         * undercount — ~0.2 % of tips, forever, biased low.
         * The seconds counter has no such horizon: anything at least 2 s after
         * the last accepted tip is unambiguously a new one, whatever the tick
         * arithmetic says, so it short-circuits the comparison.             */
        if (!(RAIN_PORT.IN & RAIN_bm)) {
            uint32_t nows = g_uptime_s;
            if ((uint32_t)(nows - last_s) >= 2 ||
                (uint16_t)(now - last) >= RAIN_DEBOUNCE_MS) {
                v_rain_tips++;
                last = now;
                last_s = nows;
            }
        }
    }
}

/* Both-edges only to WAKE us from power-down; a bouncy tactile switch makes
 * edge-level classification here unreliable, so the ISR does nothing but ack
 * and flag. The settled level is debounced in classify_button().             */
ISR(PORTB_PORT_vect)
{
    PORTB.INTFLAGS = BTN_bm;
    v_btn_wake = 1;
}

ISR(PORTC_PORT_vect)
{
    PORTC.INTFLAGS = AS3935_IRQ_bm;
    if (AS3935_IRQ_PORT.IN & AS3935_IRQ_bm) /* rising edge = event           */
        v_as3935_flag = 1;
}

/* ---------------- wind bookkeeping -------------------------------------- */

static struct {
    uint16_t gate_pulses, gate_secs;
    uint32_t rep_pulses;  uint16_t rep_secs;
    uint16_t max_gate_pulses;
} wind;

static void wind_second_tick(void)
{
    uint16_t p;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { p = v_anemo_pulses; v_anemo_pulses = 0; }
    wind.gate_pulses += p;
    if (++wind.gate_secs >= WIND_GATE_S) {
        if (wind.gate_pulses > wind.max_gate_pulses)
            wind.max_gate_pulses = wind.gate_pulses;
        wind.rep_pulses += wind.gate_pulses;
        wind.rep_secs   += wind.gate_secs;
        wind.gate_pulses = wind.gate_secs = 0;
    }
}

/* cm/s = pulses × (m/s-per-Hz ×1000) / (10 × seconds) */
static uint16_t wind_cms(uint32_t pulses, uint16_t secs)
{
    if (!secs) return 0;
    return (uint16_t)((pulses * g_cfg.anemo_ms_per_hz_x1000) / (10UL * secs));
}

/* ---------------- lightning queue + stats -------------------------------- */

typedef struct { uint8_t distance; uint32_t energy; uint32_t at_s; } ltg_evt_t;
static ltg_evt_t ltg_q[LIGHTNING_QUEUE];
static uint8_t   ltg_n;
static uint8_t   st_strikes, st_disturbers, st_noise;   /* since last reading */

/* ---------------- charge policy ------------------------------------------ */

static uint8_t chg_inhibited;

static void charge_policy_update(void)
{
    /* Fail-safe direction is ALLOW (hardware pulldown agrees): on sensor
     * doubt, deassert. LiFePO4 hard rule: no charge below CHG_LOW_LIMIT_C.  */
    uint8_t want = 0;
    if (g_cfg.chg_mode == CHG_MODE_INHIBIT) {
        want = 1;
    } else if (g_cfg.chg_mode == CHG_MODE_AUTO) {
        int16_t t = adc_read_mcu_temp_x100();
        /* The fail-safe direction was documented but never enforced: nothing
         * asked whether the sensor was believable, so one bad calibration read
         * could refuse charging forever in bright sun. A value outside the
         * MCU's own operating range is not cold weather, it is a broken
         * measurement — treat it as doubt and ALLOW, matching the hardware
         * pulldown. This is a guard, not a calibration fix.                 */
        if (t < MCU_TEMP_SANE_MIN_X100 || t > MCU_TEMP_SANE_MAX_X100) {
            want = 0;      /* the raw value still ships in verbose readings,
                              which is where you diagnose it (mcu_temp_c) */
        } else {
            if (chg_inhibited)
                want = (t < (int16_t)(g_cfg.chg_low_c + g_cfg.chg_hyst_c) * 100);
            else
                want = (t < (int16_t)g_cfg.chg_low_c * 100);
        }
    }
    chg_inhibited = want;
    hal_chg_inhibit(want);
}

/* ---------------- radio sessions ----------------------------------------- */

static uint8_t g_seq;
static uint8_t g_flags_latch;    /* one-shot flags (BOOT, CFG_APPLIED)       */
static uint8_t safe_mode;
static uint32_t safe_mode_until;

static void apply_tlvs(const uint8_t *p, uint8_t n_tlv, uint8_t avail)
{
    uint8_t changed = 0, reboot = 0;
    while (n_tlv-- && avail >= 2) {
        uint8_t t = p[0], l = p[1];
        if (avail < (uint8_t)(2 + l)) break;
        const uint8_t *v = p + 2;
        switch (t) {
        case FLP_TLV_INTERVAL:
            if (l == 2) {
                uint16_t s = (uint16_t)(v[0] | (v[1] << 8));
                if (s < 30) s = 30;
                if (s > 3600) s = 3600;
                g_cfg.report_interval_s = s; changed = 1;
            }
            break;
        case FLP_TLV_AQI_N:
            if (l == 1) { g_cfg.aqi_every_n = v[0]; changed = 1; }
            break;
        case FLP_TLV_AS3935:
            if (l == 6) {
                g_cfg.as3935_afe_outdoor     = v[0] ? 1 : 0;
                g_cfg.as3935_noise_floor     = v[1] & 7;
                g_cfg.as3935_watchdog        = v[2] > 10 ? 10 : v[2];
                g_cfg.as3935_spike_rej       = v[3] > 11 ? 11 : v[3];
                g_cfg.as3935_min_strikes     = v[4] & 3;
                g_cfg.as3935_mask_disturbers = v[5] ? 1 : 0;
                as3935_apply_cfg();
                changed = 1;
            }
            break;
        case FLP_TLV_TEMP_OFS:
            if (l == 2) {
                g_cfg.temp_offset_x100 = (int16_t)(v[0] | (v[1] << 8));
                changed = 1;
            }
            break;
        case FLP_TLV_CHG_POLICY:
            if (l == 3) {
                g_cfg.chg_mode  = v[0] > 2 ? CHG_MODE_AUTO : v[0];
                g_cfg.chg_low_c = (int8_t)v[1];
                g_cfg.chg_hyst_c = v[2];
                changed = 1;
            }
            break;
        case FLP_TLV_ANEMO_CAL:
            if (l == 2) {
                g_cfg.anemo_ms_per_hz_x1000 = (uint16_t)(v[0] | (v[1] << 8));
                changed = 1;
            }
            break;
        case FLP_TLV_VERBOSE:
            if (l == 1) { g_cfg.verbose = v[0] ? 1 : 0; changed = 1; }
            break;
        case FLP_TLV_REBOOT:  reboot = 1; break;
        case FLP_TLV_FACTORY: cfg_factory(); changed = 0; break;
        default: break;   /* unknown type: skip by length — forward compat   */
        }
        p += 2 + l; avail -= 2 + l;
    }
    if (changed) { cfg_save(); g_flags_latch |= FLP_F_CFG_APPLIED; }
    if (reboot) { cfg_save(); while (1) {} }   /* watchdog does the reset    */
}

/* One full radio session: power up, ensure NVRAM, TX (with retries when an
 * ACK is expected), harvest the ACK's TLVs, power down. Radio is on for
 * well under ~4 s total at default settings.                                */
static uint8_t radio_session(const uint8_t *frame, uint8_t len)
{
    if (!radio_on()) return 0;
    radio_ensure_nvram();
    uint8_t ok = 0;
    for (uint8_t attempt = 0; attempt <= TX_RETRIES && !ok; attempt++) {
        if (!radio_tx(frame, len)) continue;
        uint8_t rx[FLP_MAX_FRAME];
        uint8_t n = radio_rx(rx, sizeof rx, ACK_WAIT_MS);
        if (n && flp_valid(rx, n) && rx[2] == FLP_T_ACK &&
            rx[3] == STATION_ID && rx[FLP_HDR_LEN] == frame[4]) {
            apply_tlvs(rx + FLP_HDR_LEN + 2, rx[FLP_HDR_LEN + 1],
                       (uint8_t)(n - FLP_HDR_LEN - 2 - 2));
            ok = 1;
        }
    }
    radio_off();
    return ok;
}

static uint8_t base_flags(uint16_t batt_mv)
{
    uint8_t f = g_flags_latch;
    g_flags_latch = 0;
    if (chg_inhibited)          f |= FLP_F_CHG_INHIBIT;
    if (batt_mv < BATT_LOW_MV)  f |= FLP_F_LOW_BATT;
    if (safe_mode)              f |= FLP_F_SAFE_MODE;
    return f;
}

/* ---------------- battery taper (config.h §battery) ----------------------- */

/* Multiplier the table alone asks for at this voltage. Table is in descending
 * voltage order, so the last threshold crossed wins. */
static uint8_t taper_table_mult(uint16_t mv)
{
    static const struct { uint16_t mv; uint8_t mult; } tbl[] = BATT_TAPER_TABLE;
    uint8_t m = 1;
    for (uint8_t i = 0; i < sizeof(tbl) / sizeof(tbl[0]); i++)
        if (mv < tbl[i].mv) m = tbl[i].mult;
    return m;
}

static uint8_t taper_mult = 1;

/* Called once per report with the RESTING voltage (radio off, before the PMS
 * load). Tightens immediately on the way down — a cell that just fell past a
 * threshold has no margin to spend waiting — and relaxes only once the reading
 * clears the band by BATT_TAPER_HYST_MV, so the sag under a TX burst cannot
 * rattle the step back and forth. */
static uint8_t taper_update(uint16_t mv)
{
#if BATT_TAPER_ENABLE
    uint8_t want = taper_table_mult(mv);
    if (want > taper_mult) {
        taper_mult = want;
    } else if (want < taper_mult) {
        uint16_t probe = (mv > BATT_TAPER_HYST_MV)
                       ? (uint16_t)(mv - BATT_TAPER_HYST_MV) : 0;
        if (taper_table_mult(probe) <= want) taper_mult = want;
    }
    return taper_mult;
#else
    (void)mv;
    return 1;
#endif
}

/* ---------------- vane ---------------------------------------------------- */

static const vane_entry_t vane_lut[VANE_LUT_SIZE] = VANE_LUT_DEFAULT;

/* Nearest enabled LUT center within ±VANE_WINDOW; 0xFFFF = no match (fault). */
static uint16_t vane_lookup(uint16_t adc)
{
    uint16_t best_deg = 0xFFFF, best_d = VANE_WINDOW + 1;
    for (uint8_t i = 0; i < VANE_LUT_SIZE; i++) {
        if (vane_lut[i].deg_x10 == VANE_DEG_DISABLED) continue;
        uint16_t d = (adc > vane_lut[i].adc) ? (adc - vane_lut[i].adc)
                                             : (vane_lut[i].adc - adc);
        if (d < best_d) { best_d = d; best_deg = vane_lut[i].deg_x10; }
    }
    return best_deg;
}

/* ---------------- packet builders + duties -------------------------------- */

static uint8_t report_count;
static uint8_t sensor_fault_flags;

static void do_report(void)
{
    uint8_t  frame[FLP_MAX_FRAME];
    uint8_t  payload[48];
    uint16_t mask = 0;
    size_t   po = 0;
    sensor_fault_flags = 0;

    /* Priority stack: SHTx (SHT3x/SHTC3) owns temp+RH; BMx280 owns pressure and
     * fills temp (and, on a BME280, RH) when no SHTx is present. Packed in
     * mask-bit order: TEMP(0), RH(1), PRESS(2).                              */
    int16_t  temp; uint16_t rh; uint32_t pa; int16_t temp_delta = 0;
    uint8_t  env = env_read(&temp, &rh, &pa, &temp_delta);
    if (env & ENV_TEMP)  { mask |= FLP_R_TEMP;  po = flp_put16(payload, po, (uint16_t)temp); }
    if (env & ENV_RH)    { mask |= FLP_R_RH;    po = flp_put16(payload, po, rh); }
    if (env & ENV_PRESS) { mask |= FLP_R_PRESS; po = flp_put32(payload, po, pa); }
    if (env == 0) sensor_fault_flags |= FLP_F_I2C_FAULT;

    /* wind: snapshot + reset the report accumulators; fold in the partial
     * gate so slow winds near the interval boundary aren't lost            */
    uint32_t pulses = wind.rep_pulses + wind.gate_pulses;
    uint16_t secs   = wind.rep_secs + wind.gate_secs;
    /* Gust is the fastest COMPLETED gate. The trailing partial gate only
     * compares once scaled to its own length: the old code took its raw pulse
     * count and divided by a full WIND_GATE_S, so a gust arriving in the last
     * seconds before a report was under-stated by the ratio of the two — a
     * 3 s remainder reported a third of the real speed. Guarded by
     * WIND_PARTIAL_MIN_S so a lone pulse in a 1 s remainder cannot invent a
     * gust. */
    uint16_t gust_cms = wind_cms(wind.max_gate_pulses, WIND_GATE_S);
    if (wind.gate_secs >= WIND_PARTIAL_MIN_S) {
        uint16_t partial = wind_cms(wind.gate_pulses, wind.gate_secs);
        if (partial > gust_cms) gust_cms = partial;
    }
    memset(&wind, 0, sizeof wind);
    mask |= FLP_R_WAVG | FLP_R_WGUST;
    po = flp_put16(payload, po, wind_cms(pulses, secs));
    po = flp_put16(payload, po, gust_cms);

    uint16_t vadc = adc_read_vane();
    uint16_t deg  = vane_lookup(vadc);
    if (deg != 0xFFFF) {
        mask |= FLP_R_WDIR;
        po = flp_put16(payload, po, deg);
    } else sensor_fault_flags |= FLP_F_VANE_FAULT;

    uint16_t tips;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { tips = v_rain_tips; }
    mask |= FLP_R_RAIN;
    po = flp_put16(payload, po, tips);

    /* Rested cell voltage, sampled before the PMS7003's ~100 mA load — and
     * this is the one that gets REPORTED. A time series has to measure the
     * same thing at every point; the old code re-read after the load on AQI
     * cycles only, so one reading in six was a loaded voltage. Measured on
     * this cell that put a repeating ~39 mV notch in the battery chart
     * (3.332-3.340 V rested against 3.296-3.300 V loaded, no overlap) which
     * read as the pack cycling when it was only the dust sensor drawing.
     * The loaded figure is kept for the low-battery flag, where a pessimistic
     * bias is the right one: a cell that sags under load really is weak. */
    uint16_t batt_mv = adc_read_batt_mv();
    uint16_t batt_loaded_mv = batt_mv;

    /* PMS7003 — the expensive one. Only on schedule, only on a healthy cell,
     * and finished BEFORE the radio session (shared UART).                  */
    report_count++;
    if (g_cfg.aqi_every_n &&
        (report_count % g_cfg.aqi_every_n) == 0 && batt_mv >= BATT_LOW_MV) {
        uint16_t pm1, pm25, pm10;
        if (pms7003_measure(&pm1, &pm25, &pm10) == 0) {
            mask |= FLP_R_PM1 | FLP_R_PM25 | FLP_R_PM10;
            po = flp_put16(payload, po, pm1);
            po = flp_put16(payload, po, pm25);
            po = flp_put16(payload, po, pm10);
        } else sensor_fault_flags |= FLP_F_PMS_FAULT;
        batt_loaded_mv = adc_read_batt_mv();   /* sag under the 100 mA load  */
    }

    mask |= FLP_R_BATT;
    po = flp_put16(payload, po, batt_mv);

    charge_policy_update();

    if (g_cfg.verbose) {
        mask |= FLP_R_VANEADC | FLP_R_MCUTEMP;
        po = flp_put16(payload, po, vadc);
        po = flp_put16(payload, po, (uint16_t)adc_read_mcu_temp_x100());
    }
    if (st_strikes || st_disturbers || st_noise) {
        mask |= FLP_R_LTGSTATS;
        po = flp_put8(payload, po, st_strikes);
        po = flp_put8(payload, po, st_disturbers);
        po = flp_put8(payload, po, st_noise);
        st_strikes = st_disturbers = st_noise = 0;
    }

    /* Sensor cross-check, packed LAST (highest mask bit) so a coordinator that
     * predates the bit ignores it instead of mis-parsing the fields after it.
     * Sent whenever the two temperature sources disagree beyond the threshold
     * — that presence is itself the alarm — and additionally while verbose, so
     * commissioning can watch the spread before it becomes a fault.          */
    if ((env & ENV_XCHECK) &&
        (g_cfg.verbose || temp_delta >=  ENV_TEMP_DIVERGE_X100
                       || temp_delta <= -ENV_TEMP_DIVERGE_X100)) {
        mask |= FLP_R_TEMPDELTA;
        po = flp_put16(payload, po, (uint16_t)temp_delta);
    }

    size_t o = flp_begin(frame, FLP_T_READING, STATION_ID, ++g_seq,
                         base_flags(batt_loaded_mv) | sensor_fault_flags);
    o = flp_put16(frame, o, mask);
    memcpy(frame + o, payload, po);
    o = flp_seal(frame, o + po);
    radio_session(frame, (uint8_t)o);
}

static void tx_lightning_queue(void)
{
    while (ltg_n) {
        ltg_evt_t e = ltg_q[0];
        memmove(ltg_q, ltg_q + 1, (size_t)(--ltg_n) * sizeof e);
        uint32_t age = g_uptime_s - e.at_s;
        if (age > 0xFFFF) continue;         /* too stale to be useful        */
        uint8_t frame[FLP_MAX_FRAME];
        size_t o = flp_begin(frame, FLP_T_LIGHTNING, STATION_ID, ++g_seq,
                             base_flags(adc_read_batt_mv()));
        o = flp_put8(frame, o, 1);          /* count                          */
        o = flp_put8(frame, o, e.distance);
        o = flp_put32(frame, o, e.energy);
        o = flp_put16(frame, o, (uint16_t)age);
        o = flp_seal(frame, o);
        radio_session(frame, (uint8_t)o);
    }
}

static void tx_status(uint8_t reset_cause, uint8_t nvram_ok)
{
    uint8_t frame[FLP_MAX_FRAME];
    uint16_t batt = adc_read_batt_mv();
    size_t o = flp_begin(frame, FLP_T_STATUS, STATION_ID, ++g_seq,
                         base_flags(batt) | FLP_F_BOOT);
    o = flp_put16(frame, o, FW_VERSION);
    o = flp_put8(frame, o, reset_cause);
    o = flp_put16(frame, o, cfg_crc());
    o = flp_put16(frame, o, g_cfg.boot_count);
    o = flp_put8(frame, o, nvram_ok);
    o = flp_put16(frame, o, adc_read_vane());
    o = flp_put16(frame, o, batt);
    o = flp_seal(frame, o);
    radio_session(frame, (uint8_t)o);
}

/* Debounced button read, run from the main loop after a wake. Samples the
 * settled level rather than trusting bounce-prone edges: confirms a stable
 * press, then times the hold until a stable release. Blocking, but a press is
 * a user-present event and the WDT is fed the whole way. Returns 0 (nothing /
 * too short to count), 1 (short press), 2 (long press >= BTN_LONG_PRESS_MS).  */
static uint8_t classify_button(void)
{
    if (BTN_PORT.IN & BTN_bm) return 0;         /* not low: a release-edge wake */

    for (uint8_t i = 0; i < BTN_DEBOUNCE_MS; i++) {   /* press must hold steady */
        if (BTN_PORT.IN & BTN_bm) return 0;     /* let go mid-debounce: ignore  */
        hal_delay_ms(1);
    }

    uint32_t start_s  = g_uptime_s;
    uint16_t stable_hi = 0;
    while (stable_hi < BTN_DEBOUNCE_MS) {        /* wait for a debounced release */
        hal_delay_ms(1);
        hal_wdt_reset();
        if (BTN_PORT.IN & BTN_bm) {
            stable_hi++;                        /* high — count toward release   */
        } else {
            stable_hi = 0;                      /* still held (or a bounce)      */
            if (g_uptime_s - start_s >= BTN_RESET_HOLD_S)
                hal_reset();                    /* held 5s+ -> hard reset (no return) */
        }
        if (g_uptime_s - start_s >= BTN_STUCK_MAX_S) break;  /* stuck: give up   */
    }
    return (g_uptime_s - start_s >= BTN_LONG_PRESS_MS / 1000) ? 2 : 1;
}

/* ---------------- main ---------------------------------------------------- */

int main(void)
{
    uint8_t reset_cause = RSTCTRL.RSTFR;
    RSTCTRL.RSTFR = reset_cause;            /* write-1-to-clear              */

    hal_init();

#ifdef DIAG_PULSE
    uint16_t seen_rain = 0, seen_anemo = 0;
#endif

#ifdef DIAG_BOOST
    /* Bench diagnostic (build with DIAG_BOOST=1): bring up ONLY the E220's
     * 5 V boost via the normal pre-power sequence and hold it on, so the
     * TPS61023 output can be measured on the E220 VCC rail. No radio config,
     * no sensors, no sleep. The LED gives a slow ~1 Hz heartbeat so it's
     * obvious the board is in diag mode; the WDT is fed the whole time. */
    rail_radio_on();
    for (;;) {
        hal_led_blink(1, 40);
        hal_delay_ms(900);                  /* hal_delay_ms feeds the WDT    */
        hal_wdt_reset();
    }
#endif

#ifdef DIAG_PULSE
    /* Rain / anemometer bring-up (build with DIAG_PULSE=1): no radio, no I2C,
     * no sleep, no reporting — just the two pulse ISRs and the LED. One blink
     * = one pulse the FIRMWARE ACTUALLY CREDITED, debounce and all, so what
     * you see is the counter's truth rather than the switch's:
     *   rain  (PA5): one LONG  blink (250 ms)
     *   anemo (PA4): one SHORT blink (40 ms)
     *
     * Tip the bucket by hand: one physical tip must give exactly ONE long
     * blink. Two means the bucket's mechanical rock is carrying the magnet
     * past the reed twice and RAIN_DEBOUNCE_MS is too short — raise it, there
     * is enormous headroom (see config.h). Zero means the reed, the cable or
     * the pull-up, not the firmware.
     *
     * Turn the cups slowly BY HAND to count closures per revolution. The
     * blinks are blocking, so this is a hand-speed test only: a drill-spin
     * loses counts to the LED, not to the ISR — do not read it as a fault.
     *
     * THREE fast blinks at boot say "DIAG_PULSE is running and the LED works".
     * Without them, silence is ambiguous — a dead reed and the wrong firmware
     * look identical, which is exactly the hour this costs you otherwise.
     * Three, not the normal firmware's two, so the two builds are telling
     * apart at a glance.                                                   */
    hal_led_blink(3, 80);
    for (;;) {
        uint16_t r, a;
        ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { r = v_rain_tips; a = v_anemo_pulses; }
        while (seen_rain != r) {
            seen_rain++;
            hal_led(1); hal_delay_ms(250); hal_led(0); hal_delay_ms(150);
        }
        while (seen_anemo != a) {
            seen_anemo++;
            hal_led(1); hal_delay_ms(40); hal_led(0); hal_delay_ms(60);
        }
        hal_wdt_reset();
    }
#endif

#ifdef DIAG_WIND
    /* Wind pulse diagnostic (build with DIAG_WIND=1).
     *
     * DIAG_PULSE already blinks per credited pulse, but it runs with NO SLEEP
     * and a 100 ms blocking blink, so it is a hand-speed bring-up test and it
     * cannot see a fault that only happens while the MCU is in power-down.
     * This mode keeps the REAL sleep and the REAL bucketing, because that is
     * what is under suspicion: the reported average says the cups turn a few
     * times in five minutes while they are visibly turning continuously.
     *
     * What the LED says:
     *   SHORT flash (25 ms)   one revolution credited by the ISR
     *   LONG  flash (250 ms)  a 10 s gate closed WITH revolutions in it
     *   DOUBLE (2 x 120 ms)   a 10 s gate closed having credited nothing,
     *                         though edges DID reach the ISR and were thrown
     *                         away by the level test or the debounce
     *   FLUTTER (6 x 40 ms)   pulses went missing AFTER the ISR counted them
     *   4 flashes at boot     this build is running (2 = normal, 3 = DIAG_PULSE)
     *
     * Silence between gate marks and a DOUBLE are different faults: silence
     * means no edge arrived at the pin at all (reed, cable, pull-up, or the
     * pin not waking from power-down), a DOUBLE means the edge arrived and
     * the firmware rejected it. Those are hours apart in the debugging.
     *
     * How to read it. Watch the cups and the LED together:
     *
     *  - One short flash per revolution, and roughly N short flashes between
     *    two long ones where N = revolutions in 10 s? Then the ISR and the
     *    bucketing are both fine and the fault is downstream — in the report
     *    packet, the coordinator, or the cloud. Count the flashes between two
     *    longs and multiply by 0.24 for km/h.
     *  - Flashes missing revolutions? The ISR is not seeing every closure.
     *    Cause is the reed, the cable, the pull-up, the RC, or the pin's
     *    wake-from-power-down behaviour.
     *  - FLUTTER at any point? The ISR counted them and the per-second
     *    bucketing lost them. That is a firmware bug and this mode has caught
     *    it; note roughly when it fluttered relative to the gate marks.
     *
     * No UART here on purpose: PB2/PB3 is the shared rail bus (see uart.h),
     * and powering a rail to get a console would change the very conditions
     * being measured.
     *
     * rep_secs is uint16 and wraps after ~18 h; this is a bench run, not a
     * deployment, and nothing in the invariant below depends on it.         */
    hal_led_blink(4, 80);
    {
        uint32_t seen = 0, last_s = g_uptime_s, rej_prev = 0;
        uint8_t  flutter = 0;
        for (;;) {
            hal_wdt_reset();

            /* the production bucketing, catch-up loop and all */
            while (last_s != g_uptime_s) {
                last_s++;
                uint32_t rep_before = wind.rep_pulses;
                wind_second_tick();
                /* gate_secs returns to 0 only on the tick that closes a gate */
                if (wind.gate_secs == 0) {
                    uint32_t tot, rej;
                    uint16_t pend;
                    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
                        tot  = v_anemo_total;
                        rej  = v_anemo_rej;
                        pend = v_anemo_pulses;   /* credited, not yet drained */
                    }
                    /* THE INVARIANT, and it must count the undrained
                     * remainder. v_anemo_total moves the instant the ISR
                     * credits a pulse; the buckets only catch up on the next
                     * 1 Hz tick. Comparing the two without `pend` therefore
                     * reports a loss on nearly every pulse — the first cut of
                     * this mode did exactly that, fluttered continuously, and
                     * the half-second of blocking blink it added per
                     * iteration then made the catch-up loop close whole gates
                     * empty, which manufactured the doubles as well. Both
                     * symptoms were the instrument, not the firmware.
                     *
                     * Checked only here, at a gate boundary: a gate has just
                     * drained, so this is the quiet point where the three
                     * terms must add up exactly. */
                    if (tot != wind.rep_pulses + wind.gate_pulses + pend)
                        flutter = 1;

                    if (wind.rep_pulses != rep_before) {
                        hal_led(1); hal_delay_ms(250); hal_led(0);
                    } else if (rej != rej_prev) {
                        /* nothing credited this gate, yet edges arrived and
                         * were discarded — not the same as a silent pin */
                        hal_led_blink(2, 120);
                    }
                    rej_prev = rej;

                    /* at most one flutter per gate, so a real fault cannot
                     * swamp the display the way the broken version did */
                    if (flutter) { flutter = 0; hal_led_blink(6, 40); }
                }
            }

            uint32_t tot;
            ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { tot = v_anemo_total; }

            /* one short flash per newly credited revolution. Blocking, but
             * only 70 ms per pulse: at a plausible 1-2 Hz that is well clear
             * of the next edge, and the ISR keeps counting throughout
             * regardless — a blink cannot cost a pulse. */
            while (seen != tot) {
                seen++;
                hal_led(1); hal_delay_ms(25); hal_led(0); hal_delay_ms(45);
            }

            hal_sleep_powerdown();
        }
    }
#endif

#ifdef DIAG_LORATX
    /* RF-link bring-up (build with DIAG_LORATX=1): NO E220 config at all —
     * factory-default, transparent mode. Power the radio in NORMAL mode and
     * blind-send an 8-byte test packet every ~2 s; the LED blinks once per
     * send. A coordinator also left at factory default flashes its LED on
     * receive. Isolates the pure RF + UART path from every line of config code. */
    rail_radio_on();                        /* EN high + M0=0/M1=0 = NORMAL   */
    hal_delay_ms(250);                      /* let the module boot after power */
    uart_init();                            /* USART0 @ 9600 = E220 default    */
    uint8_t seq = 0;
    for (;;) {
        uint8_t pkt[8] = { 'F','O','R','S','Y','T','H', seq++ };
        uart_tx(pkt, sizeof pkt);
        hal_led_blink(1, 60);               /* one blink per send             */
        hal_delay_ms(2000);                 /* ~0.5 Hz; feeds the WDT          */
        hal_wdt_reset();
    }
#endif

#ifdef DIAG_LORARX
    /* RF RX diagnostic (build with DIAG_LORARX=1): configure the E220 to the
     * compiled production settings (ch15, crypt, FIXED mode) via the normal
     * AUX/echo discipline, then listen for the coordinator's directed packets.
     * No console — status is on the LED:
     *   boot            2 blinks
     *   5-blink groups  radio_on() failed  (power/AUX — can't reach module)
     *   3-blink groups  radio_ensure_nvram() failed  (config echo mismatch)
     *   slow heartbeat  configured OK, listening (nothing yet)
     *   long 300ms ON   a packet arrived from the coordinator                 */
    hal_led_blink(2, 100);
    if (!radio_on()) {
        for (;;) { hal_led_blink(5, 60); hal_delay_ms(1000); hal_wdt_reset(); }
    }
    if (!radio_ensure_nvram()) {
        for (;;) { hal_led_blink(3, 60); hal_delay_ms(1000); hal_wdt_reset(); }
    }
    for (;;) {
        uint8_t rx[64];
        uint8_t n = radio_rx(rx, sizeof rx, 800);
        if (n) { hal_led(1); hal_delay_ms(600); hal_led(0); hal_delay_ms(150); }
        else   { hal_led_blink(1, 30); hal_delay_ms(900); }   /* heartbeat */
        hal_wdt_reset();
    }
#endif

#ifdef DIAG_LORATXC
    /* TX-with-config diagnostic (build with DIAG_LORATXC=1): same config path as
     * DIAG_LORARX (ch15/crypt/fixed via radio_ensure_nvram), then TRANSMIT a test
     * frame every ~2s via radio_tx (which prepends the fixed-mode header). This
     * exercises the leaf's real TX current surge — watch for brownout. LED:
     *   5/3-blink groups = radio_on / config failed (as DIAG_LORARX)
     *   600ms flash      = one packet transmitted                              */
    hal_led_blink(2, 100);
    if (!radio_on()) {
        for (;;) { hal_led_blink(5, 60); hal_delay_ms(1000); hal_wdt_reset(); }
    }
    if (!radio_ensure_nvram()) {
        for (;;) { hal_led_blink(3, 60); hal_delay_ms(1000); hal_wdt_reset(); }
    }
    uint8_t seq = 0;
    for (;;) {
        uint8_t frame[12] = { 'L','E','A','F','-','T','X','-', 0, 0, 0, seq++ };
        radio_tx(frame, sizeof frame);
        hal_led(1); hal_delay_ms(600); hal_led(0);   /* 600ms flash per TX */
        hal_delay_ms(1400);                          /* ~2s period          */
        hal_wdt_reset();
    }
#endif

    cfg_load();
    twi_init();
    hal_led_blink(2, 100);

    bme280_init();                          /* soft-fail: retried per-read   */
    uint8_t as_ok = (as3935_init() == 0);
    if (!as_ok) { hal_delay_ms(50); as_ok = (as3935_init() == 0); }

    charge_policy_update();

    /* Boot STATUS doubles as the NVRAM-programming trip (first boot).       */
    tx_status(reset_cause, g_cfg.radio_nvram_crc != 0);
    g_flags_latch |= FLP_F_BOOT;            /* also mark the first reading   */

    uint32_t last_sec = g_uptime_s;
    uint32_t next_report = g_uptime_s + g_cfg.report_interval_s;

    while (1) {
        hal_wdt_reset();

        /* per-second housekeeping (handles multi-second sleeps too) */
        while (last_sec != g_uptime_s) {
            last_sec++;
            wind_second_tick();
        }

        if (v_btn_wake) {
            v_btn_wake = 0;
            uint8_t ev = classify_button();
            if (ev == 2) {                  /* long press → safe mode        */
                safe_mode = 1;
                safe_mode_until = g_uptime_s + SAFE_MODE_DURATION_S;
                hal_led_blink(5, 60);
                next_report = g_uptime_s;   /* report now                    */
            } else if (ev == 1) {
                hal_led_blink(1, 60);
                next_report = g_uptime_s;   /* report now                    */
            }
            /* ev == 0: bounce or release-edge wake — nothing to do          */
        }
        if (safe_mode && g_uptime_s >= safe_mode_until) safe_mode = 0;

        if (v_as3935_flag && as_ok) {
            v_as3935_flag = 0;
            uint8_t reason, dist; uint32_t energy;
            if (as3935_service(&reason, &dist, &energy) == 0) {
                if (reason & AS3935_INT_LIGHTNING) {
                    if (st_strikes < 255) st_strikes++;
                    if (ltg_n < LIGHTNING_QUEUE)
                        ltg_q[ltg_n++] = (ltg_evt_t){ dist, energy, g_uptime_s };
                    if (LIGHTNING_IMMEDIATE_TX &&
                        adc_read_batt_mv() >= BATT_CRIT_MV)
                        tx_lightning_queue();
                }
                if (reason & AS3935_INT_DISTURBER && st_disturbers < 255)
                    st_disturbers++;
                if (reason & AS3935_INT_NOISE && st_noise < 255)
                    st_noise++;
            }
        }

        if (g_uptime_s >= next_report) {
            uint16_t batt = adc_read_batt_mv();
            if (batt < BATT_CRIT_MV) {
                /* Hibernate: charge management + rain counting only. The
                 * BMS parachute (~2.40 V) is below us; we get out of the
                 * way long before it has to act.                            */
                charge_policy_update();
                next_report = g_uptime_s + BATT_HIBERNATE_RECHECK_S;
            } else {
                /* resting voltage: radio is off and the PMS has not run yet */
                uint8_t mult = taper_update(batt);
                do_report();
                if (!LIGHTNING_IMMEDIATE_TX) tx_lightning_queue();
                next_report = g_uptime_s +
                    (safe_mode ? (uint32_t)SAFE_MODE_INTERVAL_S
                               : (uint32_t)g_cfg.report_interval_s * mult);
            }
        }

        hal_sleep_powerdown();
    }
}
