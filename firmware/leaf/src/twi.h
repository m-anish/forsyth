/* twi.h — blocking TWI0 master, 100 kHz. Bus pull-ups live on Board B and
 * are powered whenever the leaf is (VBAT rail) — no gating dance needed.
 * All ops return 0 on success, nonzero on NACK/timeout; callers set the
 * I2C-fault flag rather than retrying forever.                              */
#ifndef FORSYTH_TWI_H
#define FORSYTH_TWI_H

#include <stdint.h>

void    twi_init(void);
uint8_t twi_write(uint8_t addr, const uint8_t *data, uint8_t len);
uint8_t twi_read(uint8_t addr, uint8_t *data, uint8_t len);
uint8_t twi_write_read(uint8_t addr, const uint8_t *w, uint8_t wlen,
                       uint8_t *r, uint8_t rlen);   /* repeated-start */
uint8_t twi_reg_write(uint8_t addr, uint8_t reg, uint8_t val);
uint8_t twi_reg_read(uint8_t addr, uint8_t reg, uint8_t *val);

#endif
