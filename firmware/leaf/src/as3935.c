#include <util/delay.h>

#include "as3935.h"
#include "twi.h"
#include "config.h"
#include "hal.h"

#define ADDR AS3935_I2C_ADDR

/* Register map (datasheet §8.9):
 * 0x00  [5:1] AFE_GB gain          [0] PWD
 * 0x01  [6:4] NF_LEV noise floor   [3:0] WDTH watchdog
 * 0x02  [6] CL_STAT  [5:4] MIN_NUM_LIGH  [3:0] SREJ spike rejection
 * 0x03  [7:6] LCO_FDIV  [5] MASK_DIST  [3:0] INT (read 2 ms after IRQ)
 * 0x04..0x06  energy LSB/MSB/MMSB(4:0)
 * 0x07  [5:0] distance km (1 = overhead, 0x3F = out of range)
 * 0x08  [7] DISP_LCO [6] DISP_SRCO [5] DISP_TRCO  [3:0] TUN_CAP (×8 pF)
 * Direct commands: write 0x96 to 0x3C (PRESET_DEFAULT) or 0x3D (CALIB_RCO). */

#define AFE_INDOOR  0b10010
#define AFE_OUTDOOR 0b01110

static uint8_t rmw(uint8_t reg, uint8_t mask, uint8_t val)
{
    uint8_t v;
    if (twi_reg_read(ADDR, reg, &v)) return 1;
    v = (uint8_t)((v & ~mask) | (val & mask));
    return twi_reg_write(ADDR, reg, v);
}

uint8_t as3935_apply_cfg(void)
{
    uint8_t afe = g_cfg.as3935_afe_outdoor ? AFE_OUTDOOR : AFE_INDOOR;
    uint8_t e = 0;
    e |= rmw(0x00, 0x3E, (uint8_t)(afe << 1));
    e |= rmw(0x01, 0x70, (uint8_t)((g_cfg.as3935_noise_floor & 7) << 4));
    e |= rmw(0x01, 0x0F, g_cfg.as3935_watchdog & 0x0F);
    e |= rmw(0x02, 0x0F, g_cfg.as3935_spike_rej & 0x0F);
    e |= rmw(0x02, 0x30, (uint8_t)((g_cfg.as3935_min_strikes & 3) << 4));
    e |= rmw(0x03, 0x20, g_cfg.as3935_mask_disturbers ? 0x20 : 0x00);
    return e;
}

uint8_t as3935_init(void)
{
    if (twi_reg_write(ADDR, 0x3C, 0x96)) return 1;   /* PRESET_DEFAULT       */
    _delay_ms(2);
    twi_reg_write(ADDR, 0x3D, 0x96);                 /* CALIB_RCO            */
    _delay_ms(2);
    /* Datasheet RCO-cal sequence: display TRCO on IRQ briefly, then clear.  */
    rmw(0x08, 0x20, 0x20);
    _delay_ms(2);
    rmw(0x08, 0x20, 0x00);
    /* Antenna tuning cap — the bench-derived value (config.h [B] knob).
     * Resonance must land on 500 kHz ±3.5 %; the bring-up procedure in
     * leaf/README.md shows how to measure it via DISP_LCO.                  */
    rmw(0x08, 0x0F, AS3935_TUNING_CAP & 0x0F);
    return as3935_apply_cfg();
}

uint8_t as3935_service(uint8_t *reason, uint8_t *distance, uint32_t *energy)
{
    _delay_ms(2);                    /* datasheet: wait 2 ms before reading INT */
    uint8_t r;
    if (twi_reg_read(ADDR, 0x03, &r)) return 1;
    *reason = r & 0x0F;
    *distance = 0;
    *energy = 0;
    if (*reason & AS3935_INT_LIGHTNING) {
        uint8_t d, e0, e1, e2;
        if (twi_reg_read(ADDR, 0x07, &d) ||
            twi_reg_read(ADDR, 0x04, &e0) ||
            twi_reg_read(ADDR, 0x05, &e1) ||
            twi_reg_read(ADDR, 0x06, &e2)) return 1;
        *distance = d & 0x3F;
        *energy = (uint32_t)e0 | ((uint32_t)e1 << 8) |
                  ((uint32_t)(e2 & 0x1F) << 16);
    }
    return 0;
}
