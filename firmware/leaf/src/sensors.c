#include <util/delay.h>
#include <string.h>

#include "sensors.h"
#include "twi.h"
#include "config.h"
#include "hal.h"

/* ================= SHTC3 ==================================================
 * Wake → measure (T-first, normal power, clock-stretch off) → sleep.
 * The part sleeps at <1 µA between reads; we re-sleep it explicitly so a
 * botched cycle can't leave it awake burning 100× that.                     */

static uint8_t sht_cmd(uint16_t c)
{
    uint8_t b[2] = { (uint8_t)(c >> 8), (uint8_t)c };
    return twi_write(SHTC3_ADDR, b, 2);
}

static uint8_t sht_crc8(const uint8_t *d, uint8_t n)   /* poly 0x31, init 0xFF */
{
    uint8_t crc = 0xFF;
    while (n--) {
        crc ^= *d++;
        for (uint8_t i = 0; i < 8; i++)
            crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x31) : (uint8_t)(crc << 1);
    }
    return crc;
}

uint8_t shtc3_read(int16_t *temp_c_x100, uint16_t *rh_x100)
{
    if (sht_cmd(0x3517)) return 1;          /* wakeup */
    _delay_ms(1);
    if (sht_cmd(0x7866)) { sht_cmd(0xB098); return 1; }  /* measure, T first */
    _delay_ms(15);                          /* normal-mode max 12.1 ms */
    uint8_t d[6];
    if (twi_read(SHTC3_ADDR, d, 6)) { sht_cmd(0xB098); return 1; }
    sht_cmd(0xB098);                        /* sleep */
    if (sht_crc8(d, 2) != d[2] || sht_crc8(d + 3, 2) != d[5]) return 1;

    uint16_t traw = ((uint16_t)d[0] << 8) | d[1];
    uint16_t hraw = ((uint16_t)d[3] << 8) | d[4];
    /* T = -45 + 175*raw/65536 ; RH = 100*raw/65536 — integer, ×100 */
    int32_t t = -4500 + (int32_t)(((uint64_t)traw * 17500) >> 16);
    *temp_c_x100 = (int16_t)(t + g_cfg.temp_offset_x100);
    *rh_x100 = (uint16_t)(((uint32_t)hraw * 10000UL) >> 16);
    return 0;
}

/* ================= BME280 =================================================
 * Bosch reference compensation, pressure path only. dig_T* still needed —
 * t_fine feeds the pressure formula. Forced mode: one conversion per call,
 * auto-sleep after — the part idles at ~0.1 µA.                             */

static struct {
    uint16_t T1; int16_t T2, T3;
    uint16_t P1; int16_t P2, P3, P4, P5, P6, P7, P8, P9;
    uint8_t  ok;
} cal;

uint8_t bme280_init(void)
{
    uint8_t id;
    if (twi_reg_read(BME280_ADDR, 0xD0, &id) || (id != 0x60 && id != 0x58))
        return 1;                            /* 0x58 = BMP280 — also fine    */
    uint8_t reg = 0x88, buf[24];
    if (twi_write_read(BME280_ADDR, &reg, 1, buf, 24)) return 1;
    cal.T1 = (uint16_t)(buf[0]  | (buf[1]  << 8));
    cal.T2 = (int16_t) (buf[2]  | (buf[3]  << 8));
    cal.T3 = (int16_t) (buf[4]  | (buf[5]  << 8));
    cal.P1 = (uint16_t)(buf[6]  | (buf[7]  << 8));
    cal.P2 = (int16_t) (buf[8]  | (buf[9]  << 8));
    cal.P3 = (int16_t) (buf[10] | (buf[11] << 8));
    cal.P4 = (int16_t) (buf[12] | (buf[13] << 8));
    cal.P5 = (int16_t) (buf[14] | (buf[15] << 8));
    cal.P6 = (int16_t) (buf[16] | (buf[17] << 8));
    cal.P7 = (int16_t) (buf[18] | (buf[19] << 8));
    cal.P8 = (int16_t) (buf[20] | (buf[21] << 8));
    cal.P9 = (int16_t) (buf[22] | (buf[23] << 8));
    /* config: standby irrelevant in forced mode; IIR filter off (one-shot
     * readings 5 min apart — filtering across them is meaningless)          */
    twi_reg_write(BME280_ADDR, 0xF5, 0x00);
    twi_reg_write(BME280_ADDR, 0xF2, 0x00);  /* humidity skipped (policy)    */
    cal.ok = 1;
    return 0;
}

uint8_t bme280_read_pressure(uint32_t *pa)
{
    if (!cal.ok && bme280_init()) return 1;
    /* forced mode, T ×1, P ×1 */
    if (twi_reg_write(BME280_ADDR, 0xF4, (0x01 << 5) | (0x01 << 2) | 0x01))
        return 1;
    _delay_ms(12);
    uint8_t st, tries = 10;
    do {
        if (twi_reg_read(BME280_ADDR, 0xF3, &st)) return 1;
        if (!(st & 0x08)) break;
        _delay_ms(2);
    } while (--tries);

    uint8_t reg = 0xF7, d[6];
    if (twi_write_read(BME280_ADDR, &reg, 1, d, 6)) return 1;
    int32_t adc_P = ((int32_t)d[0] << 12) | ((int32_t)d[1] << 4) | (d[2] >> 4);
    int32_t adc_T = ((int32_t)d[3] << 12) | ((int32_t)d[4] << 4) | (d[5] >> 4);

    /* Bosch datasheet §4.2.3 integer compensation, verbatim math */
    int32_t var1 = ((((adc_T >> 3) - ((int32_t)cal.T1 << 1))) *
                    (int32_t)cal.T2) >> 11;
    int32_t var2 = (((((adc_T >> 4) - (int32_t)cal.T1) *
                      ((adc_T >> 4) - (int32_t)cal.T1)) >> 12) *
                    (int32_t)cal.T3) >> 14;
    int32_t t_fine = var1 + var2;

    int64_t v1 = (int64_t)t_fine - 128000;
    int64_t v2 = v1 * v1 * (int64_t)cal.P6;
    v2 += (v1 * (int64_t)cal.P5) << 17;
    v2 += (int64_t)cal.P4 << 35;
    v1 = ((v1 * v1 * (int64_t)cal.P3) >> 8) + ((v1 * (int64_t)cal.P2) << 12);
    v1 = ((((int64_t)1 << 47) + v1) * (int64_t)cal.P1) >> 33;
    if (v1 == 0) return 1;
    int64_t p = 1048576 - adc_P;
    p = (((p << 31) - v2) * 3125) / v1;
    v1 = ((int64_t)cal.P9 * (p >> 13) * (p >> 13)) >> 25;
    v2 = ((int64_t)cal.P8 * p) >> 19;
    p = ((p + v1 + v2) >> 8) + ((int64_t)cal.P7 << 4);
    *pa = (uint32_t)(p >> 8);               /* Q24.8 → Pa */
    return 0;
}
