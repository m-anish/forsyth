/* e220.h — E220-900T22D driver, power-gated, lokki-disciplined.
 * Session model: radio_on() → radio_tx()/radio_rx() → radio_off().
 * The module is UNPOWERED between sessions; its NVRAM holds the register
 * config (programmed once by radio_ensure_nvram()).                          */
#ifndef FORSYTH_E220_H
#define FORSYTH_E220_H

#include <stdint.h>

uint8_t radio_on(void);        /* rail up, AUX-high wait; 1 = ready          */
void    radio_off(void);       /* full teardown, rail down                   */

/* Program-once NVRAM config. Computes the register payload from config.h,
 * compares its CRC to g_cfg.radio_nvram_crc, and (re)burns only on mismatch.
 * Call with the radio ON. Returns 1 = NVRAM verified current.               */
uint8_t radio_ensure_nvram(void);

/* Fixed-mode TX to the coordinator (dest 0x0000). Two-edge AUX wait.
 * Returns 1 when the module signalled TX complete.                          */
uint8_t radio_tx(const uint8_t *frame, uint8_t len);

/* Wait up to timeout_ms for a downlink frame; strips the module's trailing
 * RSSI byte. Returns payload length (0 = nothing).                          */
uint8_t radio_rx(uint8_t *buf, uint8_t max, uint16_t timeout_ms);

#endif
