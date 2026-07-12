#include <avr/io.h>
#include "twi.h"
#include "hal.h"

/* 100 kHz from 5 MHz: MBAUD = F_CPU/(2*f_scl) - 5 = 20. Slow and boring on
 * purpose — the bus runs down a harness to Board B.                          */
#define TWI_MBAUD 20
#define TWI_TIMEOUT 5000   /* loop iterations ≈ few ms at 5 MHz */

void twi_init(void)
{
    TWI0.MBAUD  = TWI_MBAUD;
    TWI0.MCTRLA = TWI_ENABLE_bm;
    TWI0.MSTATUS = TWI_BUSSTATE_IDLE_gc;
}

static uint8_t wait_wif(void)
{
    uint16_t n = TWI_TIMEOUT;
    while (!(TWI0.MSTATUS & (TWI_WIF_bm | TWI_RIF_bm)))
        if (!--n) return 1;
    if (TWI0.MSTATUS & (TWI_ARBLOST_bm | TWI_BUSERR_bm)) return 1;
    return 0;
}

static void stop(void) { TWI0.MCTRLB = TWI_MCMD_STOP_gc; }

static uint8_t start(uint8_t addr_rw)
{
    TWI0.MADDR = addr_rw;
    if (wait_wif()) { stop(); return 1; }
    if (TWI0.MSTATUS & TWI_RXACK_bm) { stop(); return 1; }  /* NACKed */
    return 0;
}

uint8_t twi_write(uint8_t addr, const uint8_t *data, uint8_t len)
{
    if (start((uint8_t)(addr << 1))) return 1;
    while (len--) {
        TWI0.MDATA = *data++;
        if (wait_wif() || (TWI0.MSTATUS & TWI_RXACK_bm)) { stop(); return 1; }
    }
    stop();
    return 0;
}

static uint8_t read_into(uint8_t *data, uint8_t len)
{
    while (len--) {
        uint16_t n = TWI_TIMEOUT;
        while (!(TWI0.MSTATUS & TWI_RIF_bm))
            if (!--n) { stop(); return 1; }
        *data++ = TWI0.MDATA;
        TWI0.MCTRLB = len ? TWI_MCMD_RECVTRANS_gc
                          : (TWI_ACKACT_bm | TWI_MCMD_STOP_gc);
    }
    return 0;
}

uint8_t twi_read(uint8_t addr, uint8_t *data, uint8_t len)
{
    if (start((uint8_t)((addr << 1) | 1))) return 1;
    return read_into(data, len);
}

uint8_t twi_write_read(uint8_t addr, const uint8_t *w, uint8_t wlen,
                       uint8_t *r, uint8_t rlen)
{
    if (start((uint8_t)(addr << 1))) return 1;
    while (wlen--) {
        TWI0.MDATA = *w++;
        if (wait_wif() || (TWI0.MSTATUS & TWI_RXACK_bm)) { stop(); return 1; }
    }
    /* repeated start into read */
    TWI0.MADDR = (uint8_t)((addr << 1) | 1);
    if (wait_wif()) { stop(); return 1; }
    if (TWI0.MSTATUS & TWI_RXACK_bm) { stop(); return 1; }
    return read_into(r, rlen);
}

uint8_t twi_reg_write(uint8_t addr, uint8_t reg, uint8_t val)
{
    uint8_t b[2] = { reg, val };
    return twi_write(addr, b, 2);
}

uint8_t twi_reg_read(uint8_t addr, uint8_t reg, uint8_t *val)
{
    return twi_write_read(addr, &reg, 1, val, 1);
}
