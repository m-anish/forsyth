#include <util/delay.h>
#include <string.h>

#include "sensors.h"
#include "twi.h"
#include "config.h"
#include "hal.h"

/* ============ Sensirion T/RH: SHTC3 (0x70) and SHT3x-DIS (0x44/0x45) =======
 * Same CRC (poly 0x31, init 0xFF) and the same T/RH conversion; they differ
 * only in address and command set. sht_read() tries the SHT3x addresses first,
 * then the SHTC3 — so either part (or none) works. This is the dedicated T/RH
 * owner in the priority stack.                                              */

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

/* raw counts (T first, RH second) -> centi-°C / centi-%RH, temp offset applied */
static void sht_convert(const uint8_t d[6], int16_t *temp_c_x100, uint16_t *rh_x100)
{
    uint16_t traw = ((uint16_t)d[0] << 8) | d[1];
    uint16_t hraw = ((uint16_t)d[3] << 8) | d[4];
    int32_t t = -4500 + (int32_t)(((uint64_t)traw * 17500) >> 16);
    *temp_c_x100 = (int16_t)(t + g_cfg.temp_offset_x100);
    *rh_x100 = (uint16_t)(((uint32_t)hraw * 10000UL) >> 16);
}

static uint8_t shtc3_cmd(uint16_t c)
{
    uint8_t b[2] = { (uint8_t)(c >> 8), (uint8_t)c };
    return twi_write(SHTC3_ADDR, b, 2);
}

uint8_t shtc3_read(int16_t *temp_c_x100, uint16_t *rh_x100)
{
    if (shtc3_cmd(0x3517)) return 1;                       /* wakeup */
    _delay_ms(1);
    if (shtc3_cmd(0x7866)) { shtc3_cmd(0xB098); return 1; }/* measure, T first */
    _delay_ms(15);
    uint8_t d[6];
    if (twi_read(SHTC3_ADDR, d, 6)) { shtc3_cmd(0xB098); return 1; }
    shtc3_cmd(0xB098);                                     /* sleep */
    if (sht_crc8(d, 2) != d[2] || sht_crc8(d + 3, 2) != d[5]) return 1;
    sht_convert(d, temp_c_x100, rh_x100);
    return 0;
}

uint8_t sht3x_read(uint8_t addr, int16_t *temp_c_x100, uint16_t *rh_x100)
{
    uint8_t cmd[2] = { 0x24, 0x00 };            /* single-shot, high-rep, clk-stretch off */
    if (twi_write(addr, cmd, 2)) return 1;
    _delay_ms(16);                              /* high repeatability: max 15.5 ms */
    uint8_t d[6];
    if (twi_read(addr, d, 6)) return 1;
    if (sht_crc8(d, 2) != d[2] || sht_crc8(d + 3, 2) != d[5]) return 1;
    sht_convert(d, temp_c_x100, rh_x100);
    return 0;
}

uint8_t sht_read(int16_t *temp_c_x100, uint16_t *rh_x100)
{
    if (sht3x_read(0x44, temp_c_x100, rh_x100) == 0) return 0;   /* SHT3x ADDR low  */
    if (sht3x_read(0x45, temp_c_x100, rh_x100) == 0) return 0;   /* SHT3x ADDR high */
    return shtc3_read(temp_c_x100, rh_x100);                     /* SHTC3           */
}

/* ================ BMP280 (0x58) / BME280 (0x60) ===========================
 * BMP280 = temp + pressure; BME280 adds humidity. Bosch integer compensation,
 * forced mode (one conversion per call, auto-sleep). We expose temp, pressure,
 * and — on a BME280 — humidity, so the priority stack can fall back to it.   */

static struct {
    uint16_t T1; int16_t T2, T3;
    uint16_t P1; int16_t P2, P3, P4, P5, P6, P7, P8, P9;
    uint8_t  H1; int16_t H2; uint8_t H3; int16_t H4, H5; int8_t H6;
    uint8_t  ok;
    uint8_t  has_rh;                            /* 1 = BME280 (humidity), 0 = BMP280 */
} cal;

uint8_t bme280_init(void)
{
    uint8_t id;
    if (twi_reg_read(BME280_ADDR, 0xD0, &id) || (id != 0x60 && id != 0x58))
        return 1;
    cal.has_rh = (id == 0x60);                  /* 0x60 = BME280, 0x58 = BMP280 */

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

    if (cal.has_rh) {                           /* BME280 humidity trimming (0xA1, 0xE1..0xE7) */
        uint8_t h1; if (twi_reg_read(BME280_ADDR, 0xA1, &h1)) return 1; cal.H1 = h1;
        uint8_t e[7], er = 0xE1;
        if (twi_write_read(BME280_ADDR, &er, 1, e, 7)) return 1;
        cal.H2 = (int16_t)(e[0] | (e[1] << 8));
        cal.H3 = e[2];
        cal.H4 = (int16_t)(((int16_t)(int8_t)e[3] << 4) | (e[4] & 0x0F));
        cal.H5 = (int16_t)(((int16_t)(int8_t)e[5] << 4) | (e[4] >> 4));
        cal.H6 = (int8_t)e[6];
        twi_reg_write(BME280_ADDR, 0xF2, 0x01); /* humidity osrs ×1 (must precede 0xF4) */
    } else {
        twi_reg_write(BME280_ADDR, 0xF2, 0x00);
    }
    twi_reg_write(BME280_ADDR, 0xF5, 0x00);     /* IIR filter off (readings 5 min apart) */
    cal.ok = 1;
    return 0;
}

uint8_t bmx_read(int16_t *temp_c_x100, uint16_t *rh_x100, uint32_t *pa, uint8_t *has_rh)
{
    if (!cal.ok && bme280_init()) return 1;
    if (cal.has_rh) twi_reg_write(BME280_ADDR, 0xF2, 0x01);   /* re-arm before each forced conv */
    if (twi_reg_write(BME280_ADDR, 0xF4, (0x01 << 5) | (0x01 << 2) | 0x01))
        return 1;                               /* forced mode: T ×1, P ×1 */
    _delay_ms(12);
    uint8_t st, tries = 10;
    do {
        if (twi_reg_read(BME280_ADDR, 0xF3, &st)) return 1;
        if (!(st & 0x08)) break;
        _delay_ms(2);
    } while (--tries);

    uint8_t reg = 0xF7, d[8];
    if (twi_write_read(BME280_ADDR, &reg, 1, d, 8)) return 1;  /* P[3] T[3] H[2] */
    int32_t adc_P = ((int32_t)d[0] << 12) | ((int32_t)d[1] << 4) | (d[2] >> 4);
    int32_t adc_T = ((int32_t)d[3] << 12) | ((int32_t)d[4] << 4) | (d[5] >> 4);
    int32_t adc_H = ((int32_t)d[6] << 8) | d[7];

    /* temperature — t_fine also feeds P and H (Bosch datasheet §4.2.3) */
    int32_t v1 = ((((adc_T >> 3) - ((int32_t)cal.T1 << 1))) * (int32_t)cal.T2) >> 11;
    int32_t v2 = (((((adc_T >> 4) - (int32_t)cal.T1) *
                    ((adc_T >> 4) - (int32_t)cal.T1)) >> 12) * (int32_t)cal.T3) >> 14;
    int32_t t_fine = v1 + v2;
    int32_t T = (t_fine * 5 + 128) >> 8;        /* 0.01 °C */
    *temp_c_x100 = (int16_t)(T + g_cfg.temp_offset_x100);

    /* pressure (Q24.8 -> Pa) */
    int64_t p1 = (int64_t)t_fine - 128000;
    int64_t p2 = p1 * p1 * (int64_t)cal.P6;
    p2 += (p1 * (int64_t)cal.P5) << 17;
    p2 += (int64_t)cal.P4 << 35;
    p1 = ((p1 * p1 * (int64_t)cal.P3) >> 8) + ((p1 * (int64_t)cal.P2) << 12);
    p1 = ((((int64_t)1 << 47) + p1) * (int64_t)cal.P1) >> 33;
    if (p1 == 0) return 1;
    int64_t p = 1048576 - adc_P;
    p = (((p << 31) - p2) * 3125) / p1;
    p1 = ((int64_t)cal.P9 * (p >> 13) * (p >> 13)) >> 25;
    p2 = ((int64_t)cal.P8 * p) >> 19;
    p = ((p + p1 + p2) >> 8) + ((int64_t)cal.P7 << 4);
    *pa = (uint32_t)(p >> 8);

    /* humidity (BME280 only) — Bosch integer compensation */
    *has_rh = cal.has_rh;
    if (cal.has_rh) {
        int32_t vx = t_fine - 76800;
        vx = (((((adc_H << 14) - ((int32_t)cal.H4 << 20) - ((int32_t)cal.H5 * vx))
                + 16384) >> 15) *
              (((((((vx * (int32_t)cal.H6) >> 10) *
                   (((vx * (int32_t)cal.H3) >> 11) + 32768)) >> 10)
                 + 2097152) * (int32_t)cal.H2 + 8192) >> 14));
        vx -= (((((vx >> 15) * (vx >> 15)) >> 7) * (int32_t)cal.H1) >> 4);
        if (vx < 0) vx = 0;
        if (vx > 419430400) vx = 419430400;
        uint32_t h = (uint32_t)(vx >> 12);      /* Q22.10 = %RH × 1024 */
        *rh_x100 = (uint16_t)((h * 100) >> 10); /* %RH × 100 */
    }
    return 0;
}

/* Priority stack: a dedicated SHTx owns T/RH; the BMx280 owns pressure and is
 * the T (and, on a BME280, RH) fallback when no SHTx answers. Returns a bitmask
 * of which of ENV_TEMP | ENV_RH | ENV_PRESS are valid. */
uint8_t env_read(int16_t *temp_c_x100, uint16_t *rh_x100, uint32_t *pa)
{
    uint8_t have = 0;

    int16_t st_t; uint16_t st_rh;
    uint8_t sht_ok = (sht_read(&st_t, &st_rh) == 0);

    int16_t bt; uint16_t brh; uint32_t bp; uint8_t bme_rh = 0;
    uint8_t bmx_ok = (bmx_read(&bt, &brh, &bp, &bme_rh) == 0);

    if (bmx_ok) { *pa = bp; have |= ENV_PRESS; }            /* pressure: BMx280 */

    if (sht_ok)      { *temp_c_x100 = st_t; have |= ENV_TEMP; }   /* temp: SHTx first */
    else if (bmx_ok) { *temp_c_x100 = bt;   have |= ENV_TEMP; }

    if (sht_ok)                 { *rh_x100 = st_rh; have |= ENV_RH; }  /* rh: SHTx first */
    else if (bmx_ok && bme_rh)  { *rh_x100 = brh;   have |= ENV_RH; }

    return have;
}
