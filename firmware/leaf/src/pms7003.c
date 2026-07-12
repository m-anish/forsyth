#include <string.h>

#include "pms7003.h"
#include "config.h"
#include "hal.h"
#include "uart.h"

/* Active-mode frame: 0x42 0x4D, u16 length (=28), 13×u16 data, u16 checksum
 * (sum of all bytes before it). Big-endian per Plantower manual V2.5.
 * Data words 3..5 (index from 0) are the "atmospheric environment" PM1/2.5/10
 * — the outdoor-correct set (words 0..2 are the CF=1 factory values).       */

static uint16_t be16(const uint8_t *p) { return (uint16_t)((p[0] << 8) | p[1]); }

static uint8_t read_frame(uint16_t *pm1, uint16_t *pm25, uint16_t *pm10)
{
    uint8_t buf[64];
    uint16_t n = uart_rx_collect(buf, sizeof buf, PMS_FRAME_TIMEOUT_MS, 50);
    /* Scan for header — the collector may start mid-frame. */
    for (uint16_t i = 0; i + 32 <= n; i++) {
        if (buf[i] != 0x42 || buf[i + 1] != 0x4D) continue;
        const uint8_t *f = buf + i;
        if (be16(f + 2) != 28) continue;
        uint16_t sum = 0;
        for (uint8_t j = 0; j < 30; j++) sum += f[j];
        if (sum != be16(f + 30)) continue;
        *pm1  = be16(f + 10);   /* atmospheric PM1.0  */
        *pm25 = be16(f + 12);   /* atmospheric PM2.5  */
        *pm10 = be16(f + 14);   /* atmospheric PM10   */
        return 0;
    }
    return 1;
}

uint8_t pms7003_measure(uint16_t *pm1, uint16_t *pm25, uint16_t *pm10)
{
    rail_aqi_on();
    uart_init();

    /* Warm-up: the fan needs PMS_WARMUP_S before numbers mean anything.
     * Sleep through it in 1 s PIT slices — the MCU has nothing to do but
     * keep the watchdog fed. The UART RX ring just discards the stream.     */
    uint32_t until = g_uptime_s + PMS_WARMUP_S;
    while (g_uptime_s < until) {
        hal_wdt_reset();
        hal_sleep_powerdown();
    }
    uart_rx_flush();

    uint32_t a1 = 0, a25 = 0, a10 = 0;
    uint8_t got = 0;
    for (uint8_t i = 0; i < PMS_SAMPLES + 2 && got < PMS_SAMPLES; i++) {
        uint16_t v1, v25, v10;
        hal_wdt_reset();
        if (read_frame(&v1, &v25, &v10) == 0) {
            a1 += v1; a25 += v25; a10 += v10; got++;
        }
    }

    uart_deinit();
    rail_aqi_off();

    if (got == 0) return 1;
    *pm1  = (uint16_t)(a1  / got);
    *pm25 = (uint16_t)(a25 / got);
    *pm10 = (uint16_t)(a10 / got);
    return 0;
}
