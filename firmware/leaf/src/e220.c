#include <avr/io.h>
#include <util/delay.h>
#include <string.h>

#include "e220.h"
#include "config.h"
#include "pins.h"
#include "hal.h"
#include "uart.h"
#include "protocol.h"

/* Register payload encoding — must match lokki's lora_config.py tables and
 * the coordinator's e220.py byte-for-byte (same silicon, same datasheet).   */
#define CMD_WRITE_NVRAM 0xC0
#define CMD_READ_REGS   0xC1
#define REG_ADDR_CFG    0x00
#define PL_CONFIG       0x08

#define BAUD_9600_BITS  0b011
#define PARITY_8N1_BITS 0b00

static uint8_t air_bits(void)
{
    switch (LORA_AIR_RATE) {
        case 300:   return 0b000;
        case 1200:  return 0b001;
        case 2400:  return 0b010;
        case 4800:  return 0b011;
        case 9600:  return 0b100;
        case 19200: return 0b101;
        case 38400: return 0b110;
        default:    return 0b111;  /* 62500 */
    }
}

static uint8_t pwr_bits(void)
{
    switch (LORA_TX_POWER_DBM) {
        case 22: return 0b00;
        case 17: return 0b01;
        case 13: return 0b10;
        default: return 0b11;      /* 10 dBm */
    }
}

static void build_regs(uint8_t out[8])
{
    out[0] = 0x00;                 /* ADDH */
    out[1] = STATION_ID;           /* ADDL — leaf address                    */
    out[2] = (uint8_t)((BAUD_9600_BITS << 5) | (PARITY_8N1_BITS << 3) | air_bits());
    out[3] = (uint8_t)((0b00 << 6) | pwr_bits());   /* subpkt 200, RSSI amb off */
    out[4] = LORA_CHANNEL;
    /* RSSI byte ON | fixed mode ON | LBT off | WOR 2000 ms (unused)         */
    out[5] = (uint8_t)((1 << 7) | (1 << 6) | 0b011);
    out[6] = LORA_CRYPT_H;
    out[7] = LORA_CRYPT_L;
}

/* ---- AUX waits: the two-edge discipline --------------------------------- */

static uint8_t aux_high(void) { return (E220_AUX_PORT.IN & E220_AUX_bm) != 0; }

static uint8_t wait_aux_high(uint16_t timeout_ms)
{
    while (timeout_ms--) {
        if (aux_high()) return 1;
        _delay_ms(1);
        hal_wdt_reset();
    }
    return 0;
}

static uint8_t wait_aux_low(uint16_t timeout_ms)
{
    /* Advisory: on a fast MCU the LOW pulse can be missed entirely —
     * a miss is NOT an error, the HIGH wait after it is the real gate.      */
    while (timeout_ms--) {
        if (!aux_high()) return 1;
        _delay_ms(1);
    }
    return 0;
}

static void set_mode(uint8_t m0, uint8_t m1)
{
    _delay_ms(40);   /* pre/post guard per datasheet + xreef timing */
    if (m0) E220_M0_PORT.OUTSET = E220_M0_bm; else E220_M0_PORT.OUTCLR = E220_M0_bm;
    if (m1) E220_M1_PORT.OUTSET = E220_M1_bm; else E220_M1_PORT.OUTCLR = E220_M1_bm;
    _delay_ms(40);
    wait_aux_high(1000);
    _delay_ms(20);
}

/* ---- public -------------------------------------------------------------- */

uint8_t radio_on(void)
{
    rail_radio_on();               /* M0/M1 already driven low = NORMAL      */
    uart_init();
    /* Boost soft-start + module boot. AUX goes high when the module is
     * ready; +2 ms guard before first UART byte (the lokki law).            */
    if (!wait_aux_high(1200)) { radio_off(); return 0; }
    _delay_ms(2);
    uart_rx_flush();
    return 1;
}

void radio_off(void)
{
    uart_deinit();
    rail_radio_off();
}

uint8_t radio_ensure_nvram(void)
{
    uint8_t regs[8];
    build_regs(regs);
    uint16_t crc = flp_crc16(regs, 8);
    if (g_cfg.radio_nvram_crc == crc) return 1;   /* already burned          */

    set_mode(1, 1);                                /* PROGRAM                */
    uart_rx_flush();
    uint8_t cmd[3 + 8] = { CMD_WRITE_NVRAM, REG_ADDR_CFG, PL_CONFIG };
    memcpy(cmd + 3, regs, 8);
    uart_tx(cmd, sizeof cmd);
    wait_aux_low(500);
    if (!wait_aux_high(2000)) { set_mode(0, 0); return 0; }
    _delay_ms(5);

    uint8_t reply[16];
    uint16_t n = uart_rx_collect(reply, sizeof reply, 200, 20);
    set_mode(0, 0);                                /* back to NORMAL         */
    if (n < 11 || reply[0] != CMD_READ_REGS || memcmp(reply + 3, regs, 8) != 0)
        return 0;                                  /* echo mismatch          */

    g_cfg.radio_nvram_crc = crc;
    cfg_save();
    return 1;
}

uint8_t radio_tx(const uint8_t *frame, uint8_t len)
{
    if (!wait_aux_high(1000)) return 0;
    /* Fixed-mode header: dest 0x0000 (only the monitor-mode coordinator
     * receives it) + channel.                                               */
    uint8_t hdr[3] = { 0x00, 0x00, LORA_CHANNEL };
    uart_tx(hdr, 3);
    uart_tx(frame, len);
    wait_aux_low(1000);            /* module took the buffer                 */
    if (!wait_aux_high(5000)) return 0;   /* airtime at 2400 bps air rate    */
    return 1;
}

uint8_t radio_rx(uint8_t *buf, uint8_t max, uint16_t timeout_ms)
{
    uint16_t n = uart_rx_collect(buf, max, timeout_ms, 20);
    if (n < 2) return 0;
    return (uint8_t)(n - 1);       /* strip the module's appended RSSI byte  */
}
