#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/sleep.h>
#include <avr/wdt.h>
#include <avr/eeprom.h>
#include <util/delay.h>
#include <string.h>

#include "hal.h"
#include "pins.h"
#include "protocol.h"   /* flp_crc16 doubles as the config CRC */

volatile uint32_t g_uptime_s;
leaf_cfg_t g_cfg;

ISR(RTC_PIT_vect)
{
    RTC.PITINTFLAGS = RTC_PI_bm;
    g_uptime_s++;
}

static void clock_init(void)
{
    /* 20 MHz internal osc ÷ 4 = 5 MHz. 5 MHz is inside the datasheet's
     * safe-operating envelope all the way down to 1.8 V — the cell can sit
     * anywhere between the BMS parachute (~2.4 V) and 3.65 V and the core
     * never runs out of spec. (10 MHz would need ≥2.7 V guaranteed.)        */
    _PROTECTED_WRITE(CLKCTRL.MCLKCTRLB, CLKCTRL_PDIV_4X_gc | CLKCTRL_PEN_bm);
}

static void wdt_init(void)
{
    /* 8 s watchdog. Longest legitimate stall is the PMS warm-up, which
     * sleeps in 1 s PIT slices with a wdt kick per slice.                    */
    _PROTECTED_WRITE(WDT.CTRLA, WDT_PERIOD_8KCLK_gc);
}

static void rtc_init(void)
{
    while (RTC.STATUS & (RTC_CTRLABUSY_bm | RTC_PERBUSY_bm)) {}
    RTC.CLKSEL  = RTC_CLKSEL_INT32K_gc;
    RTC.PER     = 0xFFFF;
    /* counter at 32768/32 = 1024 Hz for debounce timestamps */
    RTC.CTRLA   = RTC_PRESCALER_DIV32_gc | RTC_RTCEN_bm | RTC_RUNSTDBY_bm;
    /* PIT: one interrupt per 32768 cycles = 1 Hz uptime tick */
    while (RTC.PITSTATUS & RTC_CTRLBUSY_bm) {}
    RTC.PITCTRLA   = RTC_PERIOD_CYC32768_gc | RTC_PITEN_bm;
    RTC.PITINTCTRL = RTC_PI_bm;
}

static void gpio_init(void)
{
    /* Outputs, all in their safe/off state first, then direction. */
    EN_RADIO_PORT.OUTCLR    = EN_RADIO_bm;
    EN_AQI_PORT.OUTCLR      = EN_AQI_bm;
    CHG_INHIBIT_PORT.OUTCLR = CHG_INHIBIT_bm;   /* charging allowed */
    E220_M0_PORT.OUTCLR     = E220_M0_bm;
    E220_M1_PORT.OUTCLR     = E220_M1_bm;
    UART_TX_PORT.OUTCLR     = UART_TX_bm;       /* low while rails are down */
    LED_PORT.OUTSET         = LED_bm;           /* active-low → off */

    PORTA.DIRSET = EN_RADIO_bm | EN_AQI_bm | CHG_INHIBIT_bm;
    PORTB.DIRSET = UART_TX_bm | LED_bm;
    PORTC.DIRSET = E220_M0_bm | E220_M1_bm;

    /* Pulse inputs: pull-ups + both-edge interrupts. PA4/PA5 are PARTIALLY
     * asynchronous, and datasheet table 17-3 is worth reading before
     * touching any of this. BOTHEDGES really is the only sense that wakes
     * with CLK_PER stopped — that part of the original comment was right.
     * What it missed is the row underneath: with CLK_PER stopped "the pin
     * value must be kept until CLK_PER has restarted", so a reed closure
     * that ends first is missed ENTIRELY, not just misclassified. That is
     * why wind counting failed in power-down for as long as it did, and why
     * the leaf now sleeps in STANDBY with TCB0 counting the edges instead.
     * A fully asynchronous pin would need none of this (same table, right
     * column); PORTA has no free one today.                                 */
#if defined(DIAG_PULSE) || defined(DIAG_WIND)
    /* the diag builds count in the ISR, so they still need the interrupt */
    ANEMO_PORT.ANEMO_CTRL = PORT_PULLUPEN_bm | PORT_ISC_BOTHEDGES_gc;
#else
    /* Production counts in hardware (hal_wind_counter_init), so the CPU does
     * not need waking per edge — which it was not reliably doing anyway. The
     * input buffer stays on because the Event System reads the pin through
     * it; only the interrupt is off. At 5 m/s that is ~30 wakes a second this
     * no longer pays for. */
    ANEMO_PORT.ANEMO_CTRL = PORT_PULLUPEN_bm | PORT_ISC_INTDISABLE_gc;
#endif
    RAIN_PORT.RAIN_CTRL   = PORT_PULLUPEN_bm | PORT_ISC_BOTHEDGES_gc;
    BTN_PORT.BTN_CTRL     = PORT_PULLUPEN_bm | PORT_ISC_BOTHEDGES_gc;
    /* AS3935 IRQ idles low, pulses high; SEN0290 drives it — no pull-up.     */
    AS3935_IRQ_PORT.AS3935_IRQ_CTRL = PORT_ISC_BOTHEDGES_gc;
    /* Shared-UART RX: pulled up while both peripherals are gated off
     * (10 k clamp R2 leaves it floating otherwise).                          */
    UART_RX_PORT.UART_RX_CTRL = PORT_PULLUPEN_bm;
    /* E220 AUX: plain input; pull-up only while the module is powered
     * (rail_radio_on) so we don't leak into an unpowered module.             */
    E220_AUX_PORT.E220_AUX_CTRL = 0;

    /* Everything unused: disable input buffers to kill floating-pin drain.   */
    PORTA.PIN0CTRL = PORT_ISC_INPUT_DISABLE_gc;  /* UPDI pad as GPIO-off      */
    PORTA.PIN6CTRL = PORT_ISC_INPUT_DISABLE_gc;  /* analog: vane              */
    PORTA.PIN7CTRL = PORT_ISC_INPUT_DISABLE_gc;  /* analog: vbat              */
}

void hal_init(void)
{
    clock_init();
    wdt_init();
    gpio_init();
    rtc_init();
    hal_wind_counter_init();
    /* STANDBY, and the reason is specific. TCB_CLKSEL_EVENT does NOT clock
     * the counter asynchronously from the event — it still needs CLK_PER to
     * sample it, which POWER_DOWN stops. Measured 2026-11-06: asleep in
     * power-down the counter reported max_events_s=1 while the cups turned
     * at ~10 edges/s, i.e. it was aliasing the pin once per PIT wake rather
     * than counting; the one window that read 13 contained a radio session,
     * the only stretch with the clock running.
     *
     * STANDBY keeps CLK_PER alive for peripherals that ask, and TCB0 asks
     * (TCB_RUNSTDBY_bm in hal_wind_counter_init). The CPU still sleeps.
     *
     * OPEN: what this costs. Running the 5 MHz domain continuously is worth
     * hundreds of µA against an 80-100 µA sleep floor, so this is a working
     * solution of unknown price, not a finished one. Measure it on the bench
     * before trusting it to solar. If it is too dear, the alternative is a
     * fully asynchronous pin for the anemometer so the edge wakes the CPU
     * directly — PORTA is fully allocated today, so that is a wiring change
     * and not a line of code. */
    set_sleep_mode(SLEEP_MODE_STANDBY);
    sei();
}

void hal_wind_counter_init(void)
{
    /* PA4 -> event channel 0 -> TCB0's COUNT input (Event in B), and TCB0
     * clocked by that event instead of CLK_PER. CLKSEL_EVENT is the whole
     * trick: the counter advances on the pin edge with no system clock, so
     * it works in POWER_DOWN. RUNSTDBY keeps it alive in standby too.
     *
     * CNTMODE_INT with CCMP at full scale is just "free-running 16-bit
     * up-counter"; nothing wants the interrupt, the firmware polls CNT once
     * a second and subtracts. At the 250 events/s ceiling a 16-bit counter
     * needs 262 s to wrap, so a once-a-second read cannot miss a lap. */
    EVSYS.CHANNEL0      = EVSYS_CHANNEL0_PORTA_PIN4_gc;
    EVSYS.USERTCB0COUNT = EVSYS_USER_CHANNEL0_gc;

    TCB0.CTRLA   = 0;                       /* configure while disabled      */
    TCB0.CNT     = 0;
    TCB0.CCMP    = 0xFFFF;
    TCB0.CTRLB   = TCB_CNTMODE_INT_gc;
    TCB0.EVCTRL  = 0;                       /* COUNT input, not capture      */
    TCB0.INTCTRL = 0;                       /* polled, never interrupts      */
    TCB0.CTRLA   = TCB_CLKSEL_EVENT_gc | TCB_RUNSTDBY_bm | TCB_ENABLE_bm;
}

uint16_t hal_wind_count(void) { return TCB0.CNT; }

void hal_sleep_powerdown(void)
{
    /* Slow the main clock right down while asleep, and put it back before
     * anything notices.
     *
     * STANDBY has to keep CLK_PER running because TCB0 is a SYNCHRONOUS
     * event user and cannot sample its event without it (datasheet, Event
     * System sleep-mode operation). That is the whole cost of counting wind
     * in hardware. But a synchronous user needs its clock RUNNING, not
     * FAST: 20 MHz/64 = 312.5 kHz still samples the pin every 3.2 us,
     * against reed closures lasting milliseconds — about a thousandfold
     * margin — and the interrupt dead-time of three cycles is 9.6 us
     * against a 4 ms floor between edges.
     *
     * MEASURED 2026-11-06, no rails energised, vane untouched:
     *     470 uA  POWER_DOWN, TCB0 off  (cannot count wind at all)
     *    1000 uA  STANDBY at 5 MHz      -> costs 530 uA
     *     708 uA  STANDBY at 312.5 kHz  -> costs 238 uA
     * So the drop is worth 292 uA. I predicted 16x on the theory that
     * standby current tracks frequency; it is 2.2x, because PDIV only
     * DIVIDES the oscillator's output and does not stop the oscillator.
     * OSC20M runs at 20 MHz either way and its own draw is a floor the
     * prescaler cannot touch — only the clock tree and TCB0 scale. Keep the
     * two writes regardless: 292 uA is more than the whole feature costs.
     *
     * Restored IMMEDIATELY on wake, before the main loop can reach anything
     * that cares: both the USART baud divisor and _delay_ms() are derived
     * from F_CPU at compile time, so at 312.5 kHz every delay would run 16x
     * long and 9600 baud would be 600. An ISR landing while slow simply
     * runs slower, which the PIT handler does not mind.
     *
     * The RTC/PIT and the WDT have their own oscillators and are untouched. */
#ifndef DIAG_IDLE_FAST
    _PROTECTED_WRITE(CLKCTRL.MCLKCTRLB, CLKCTRL_PDIV_64X_gc | CLKCTRL_PEN_bm);
#endif
    sleep_enable();
    sleep_cpu();
    sleep_disable();
#ifndef DIAG_IDLE_FAST
    _PROTECTED_WRITE(CLKCTRL.MCLKCTRLB, CLKCTRL_PDIV_4X_gc | CLKCTRL_PEN_bm);
#endif
}

void hal_wdt_reset(void) { wdt_reset(); }

void hal_reset(void) { _PROTECTED_WRITE(RSTCTRL.SWRR, RSTCTRL_SWRE_bm); }

uint16_t hal_ticks(void)
{
    /* RTC.CNT needs a synchronized read; two reads until stable is the
     * cheap-and-correct idiom for a free-running async counter.              */
    uint16_t a, b;
    do { a = RTC.CNT; b = RTC.CNT; } while (a != b);
    return a;
}

void hal_delay_ms(uint16_t ms)
{
    while (ms >= 10) { _delay_ms(10); wdt_reset(); ms -= 10; }
    while (ms--) _delay_ms(1);
}

void hal_led(uint8_t on)
{
    if (on) LED_PORT.OUTCLR = LED_bm;   /* active-low */
    else    LED_PORT.OUTSET = LED_bm;
}

void hal_led_blink(uint8_t times, uint16_t ms)
{
    while (times--) {
        hal_led(1); hal_delay_ms(ms);
        hal_led(0); hal_delay_ms(ms);
    }
}

/* ---- rails -------------------------------------------------------------- */
/* Invariant: E220 and PMS7003 share USART0 — exactly one rail up at a time.
 * Off-sequence per board-a-core.md §6: TX low first, then EN down, then the
 * PB3 pull-up back on. M0/M1 are driven low before the radio rail rises so
 * the module never sees floating mode pins (the lokki bug).                  */

void rail_radio_on(void)
{
    rail_aqi_off();
    E220_M0_PORT.OUTCLR = E220_M0_bm;      /* NORMAL mode, driven, pre-power  */
    E220_M1_PORT.OUTCLR = E220_M1_bm;
    UART_RX_PORT.UART_RX_CTRL = 0;         /* module drives RX now            */
    E220_AUX_PORT.E220_AUX_CTRL = PORT_PULLUPEN_bm;
    EN_RADIO_PORT.OUTSET = EN_RADIO_bm;
}

void rail_radio_off(void)
{
    UART_TX_PORT.OUTCLR = UART_TX_bm;
    E220_M0_PORT.OUTCLR = E220_M0_bm;
    E220_M1_PORT.OUTCLR = E220_M1_bm;
    E220_AUX_PORT.E220_AUX_CTRL = 0;       /* no pull-up into a dead module   */
    EN_RADIO_PORT.OUTCLR = EN_RADIO_bm;
    UART_RX_PORT.UART_RX_CTRL = PORT_PULLUPEN_bm;
}

void rail_aqi_on(void)
{
    rail_radio_off();
    UART_RX_PORT.UART_RX_CTRL = 0;
    EN_AQI_PORT.OUTSET = EN_AQI_bm;
}

void rail_aqi_off(void)
{
    UART_TX_PORT.OUTCLR = UART_TX_bm;
    EN_AQI_PORT.OUTCLR = EN_AQI_bm;
    UART_RX_PORT.UART_RX_CTRL = PORT_PULLUPEN_bm;
}

void hal_chg_inhibit(uint8_t inhibit)
{
    if (inhibit) CHG_INHIBIT_PORT.OUTSET = CHG_INHIBIT_bm;
    else         CHG_INHIBIT_PORT.OUTCLR = CHG_INHIBIT_bm;
}

/* ---- EEPROM config store ------------------------------------------------ */

static leaf_cfg_t EEMEM ee_cfg;

static void cfg_defaults(void)
{
    memset(&g_cfg, 0, sizeof g_cfg);
    g_cfg.magic   = CFG_MAGIC;
    g_cfg.version = CFG_VERSION;
    g_cfg.report_interval_s      = REPORT_INTERVAL_S;
    g_cfg.aqi_every_n            = AQI_EVERY_N_REPORTS;
    g_cfg.verbose                = VERBOSE_DEFAULT;
    g_cfg.temp_offset_x100       = SHTC3_TEMP_OFFSET_X100;
    g_cfg.anemo_ms_per_hz_x1000  = ANEMO_MS_PER_HZ_X1000;
    g_cfg.chg_mode               = CHG_POLICY_MODE;
    g_cfg.chg_low_c              = CHG_LOW_LIMIT_C;
    g_cfg.chg_hyst_c             = CHG_HYSTERESIS_C;
    g_cfg.as3935_afe_outdoor     = AS3935_AFE_OUTDOOR;
    g_cfg.as3935_noise_floor     = AS3935_NOISE_FLOOR;
    g_cfg.as3935_watchdog        = AS3935_WATCHDOG;
    g_cfg.as3935_spike_rej       = AS3935_SPIKE_REJ;
    g_cfg.as3935_min_strikes     = AS3935_MIN_STRIKES;
    g_cfg.as3935_mask_disturbers = AS3935_MASK_DISTURBERS;
}

uint16_t cfg_crc(void)
{
    return flp_crc16((const uint8_t *)&g_cfg,
                     sizeof g_cfg - sizeof g_cfg.crc);
}

void cfg_load(void)
{
    eeprom_read_block(&g_cfg, &ee_cfg, sizeof g_cfg);
    if (g_cfg.magic != CFG_MAGIC || g_cfg.version != CFG_VERSION ||
        g_cfg.crc != cfg_crc()) {
        uint16_t boots = (g_cfg.magic == CFG_MAGIC) ? g_cfg.boot_count : 0;
        cfg_defaults();
        g_cfg.boot_count = boots;
        cfg_save();
    }
    g_cfg.boot_count++;
    cfg_save();
}

void cfg_save(void)
{
    g_cfg.crc = cfg_crc();
    eeprom_update_block(&g_cfg, &ee_cfg, sizeof g_cfg);
}

void cfg_factory(void)
{
    uint16_t boots = g_cfg.boot_count;
    cfg_defaults();
    g_cfg.boot_count = boots;
    cfg_save();
}
