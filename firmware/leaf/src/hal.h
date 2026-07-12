/* hal.h — clock, sleep, time base, rails, LED, EEPROM-backed runtime config. */
#ifndef FORSYTH_HAL_H
#define FORSYTH_HAL_H

#include <stdint.h>
#include "config.h"

/* F_CPU is set in the Makefile (5 MHz — see hal.c clock_init for why). */

void hal_init(void);                 /* clock, WDT, GPIO safe states, RTC+PIT */
void hal_sleep_powerdown(void);      /* returns on any enabled interrupt      */
void hal_wdt_reset(void);

/* Time base: PIT gives a 1 Hz uptime; the RTC counter gives ~1024 Hz ticks
 * for debounce math (16-bit, wraps every 64 s — compare with wraparound-safe
 * subtraction only). Both run from the internal 32.768 kHz ULP oscillator
 * and keep running in power-down.                                            */
extern volatile uint32_t g_uptime_s;
uint16_t hal_ticks(void);            /* ~1024 Hz, wraps */
void     hal_delay_ms(uint16_t ms);  /* busy-ish wait, WDT-safe */

/* Status LED (active-low). Blink is blocking — boot/service feedback only.   */
void hal_led(uint8_t on);
void hal_led_blink(uint8_t times, uint16_t ms);

/* Gated 5 V rails. The shared-UART invariant lives here: turning one rail on
 * asserts the other is off, handles UART_TX-low-before-EN-drop and the PB3
 * pull-up rule (board-a-core.md §6 item 4).                                  */
void rail_radio_on(void);
void rail_radio_off(void);
void rail_aqi_on(void);
void rail_aqi_off(void);

/* Charge-inhibit output (PA3). high = inhibit. */
void hal_chg_inhibit(uint8_t inhibit);

/* ---- runtime config: compiled defaults, EEPROM persistence, TLV updates ---- */
typedef struct {
    uint16_t magic;
    uint16_t version;
    uint16_t report_interval_s;
    uint8_t  aqi_every_n;
    uint8_t  verbose;
    int16_t  temp_offset_x100;
    uint16_t anemo_ms_per_hz_x1000;
    uint8_t  chg_mode;
    int8_t   chg_low_c;
    uint8_t  chg_hyst_c;
    uint8_t  as3935_afe_outdoor;
    uint8_t  as3935_noise_floor;
    uint8_t  as3935_watchdog;
    uint8_t  as3935_spike_rej;
    uint8_t  as3935_min_strikes;
    uint8_t  as3935_mask_disturbers;
    uint16_t boot_count;
    uint16_t radio_nvram_crc;   /* CRC of the E220 register payload last
                                   burned to module NVRAM; 0 = never          */
    uint16_t crc;
} leaf_cfg_t;

extern leaf_cfg_t g_cfg;

void cfg_load(void);     /* EEPROM → g_cfg; falls back to defaults on
                            magic/version/CRC mismatch (and saves them)       */
void cfg_save(void);
void cfg_factory(void);
uint16_t cfg_crc(void);  /* current g_cfg CRC, for STATUS packets */

#endif
