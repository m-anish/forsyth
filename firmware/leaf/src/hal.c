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

    /* Pulse inputs: pull-ups + both-edge interrupts. PA4/PA5 are not fully
     * asynchronous pins, so BOTHEDGES is the only edge sense that wakes from
     * power-down — the ISRs sort out which edge by reading the level.        */
    ANEMO_PORT.ANEMO_CTRL = PORT_PULLUPEN_bm | PORT_ISC_BOTHEDGES_gc;
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
    set_sleep_mode(SLEEP_MODE_PWR_DOWN);
    sei();
}

void hal_sleep_powerdown(void)
{
    sleep_enable();
    sleep_cpu();
    sleep_disable();
}

void hal_wdt_reset(void) { wdt_reset(); }

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
