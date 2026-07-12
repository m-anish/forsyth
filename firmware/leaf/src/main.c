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

/* ---------------- ISR-shared state -------------------------------------- */

static volatile uint16_t v_anemo_pulses;    /* pulses this second            */
static volatile uint16_t v_rain_tips;       /* cumulative, wraps (protocol)  */
static volatile uint8_t  v_as3935_flag;
static volatile uint8_t  v_btn_event;       /* 0 none, 1 short, 2 long       */

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
            last = now;
        }
    }
    if (flags & RAIN_bm) {
        static uint16_t last;
        if (!(RAIN_PORT.IN & RAIN_bm) &&
            (uint16_t)(now - last) >= RAIN_DEBOUNCE_MS) {
            v_rain_tips++;
            last = now;
        }
    }
}

ISR(PORTB_PORT_vect)
{
    PORTB.INTFLAGS = BTN_bm;
    static uint16_t pressed_at;
    static uint32_t pressed_s;
    uint16_t now = hal_ticks();
    if (!(BTN_PORT.IN & BTN_bm)) {          /* press                         */
        pressed_at = now;
        pressed_s  = g_uptime_s;
    } else {                                /* release — classify            */
        uint32_t held_s = g_uptime_s - pressed_s;
        uint16_t held_t = (uint16_t)(now - pressed_at);
        if (held_s >= (BTN_LONG_PRESS_MS / 1000) + 1 ||
            (held_s <= 3 && held_t >= BTN_LONG_PRESS_MS))
            v_btn_event = 2;
        else if (held_t >= BTN_DEBOUNCE_MS || held_s > 0)
            v_btn_event = 1;
    }
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
        if (chg_inhibited)
            want = (t < (int16_t)(g_cfg.chg_low_c + g_cfg.chg_hyst_c) * 100);
        else
            want = (t < (int16_t)g_cfg.chg_low_c * 100);
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

    int16_t  temp; uint16_t rh;
    if (shtc3_read(&temp, &rh) == 0) {
        mask |= FLP_R_TEMP | FLP_R_RH;
        po = flp_put16(payload, po, (uint16_t)temp);
        po = flp_put16(payload, po, rh);
    } else sensor_fault_flags |= FLP_F_I2C_FAULT;

    uint32_t pa;
    if (bme280_read_pressure(&pa) == 0) {
        mask |= FLP_R_PRESS;
        po = flp_put32(payload, po, pa);
    } else sensor_fault_flags |= FLP_F_I2C_FAULT;

    /* wind: snapshot + reset the report accumulators; fold in the partial
     * gate so slow winds near the interval boundary aren't lost            */
    uint32_t pulses = wind.rep_pulses + wind.gate_pulses;
    uint16_t secs   = wind.rep_secs + wind.gate_secs;
    uint16_t maxg   = wind.max_gate_pulses;
    if (wind.gate_pulses > maxg) maxg = wind.gate_pulses;
    memset(&wind, 0, sizeof wind);
    mask |= FLP_R_WAVG | FLP_R_WGUST;
    po = flp_put16(payload, po, wind_cms(pulses, secs));
    po = flp_put16(payload, po, wind_cms(maxg, WIND_GATE_S));

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

    uint16_t batt_mv = adc_read_batt_mv();

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
        batt_mv = adc_read_batt_mv();   /* re-read after the 100 mA load     */
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

    size_t o = flp_begin(frame, FLP_T_READING, STATION_ID, ++g_seq,
                         base_flags(batt_mv) | sensor_fault_flags);
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

/* ---------------- main ---------------------------------------------------- */

int main(void)
{
    uint8_t reset_cause = RSTCTRL.RSTFR;
    RSTCTRL.RSTFR = reset_cause;            /* write-1-to-clear              */

    hal_init();
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

        if (v_btn_event) {
            uint8_t ev = v_btn_event; v_btn_event = 0;
            if (ev == 2) {                  /* long press → safe mode        */
                safe_mode = 1;
                safe_mode_until = g_uptime_s + SAFE_MODE_DURATION_S;
                hal_led_blink(5, 60);
            } else {
                hal_led_blink(1, 60);
            }
            next_report = g_uptime_s;       /* either way: report now        */
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
                do_report();
                if (!LIGHTNING_IMMEDIATE_TX) tx_lightning_queue();
                next_report = g_uptime_s +
                    (safe_mode ? SAFE_MODE_INTERVAL_S
                               : g_cfg.report_interval_s);
            }
        }

        hal_sleep_powerdown();
    }
}
