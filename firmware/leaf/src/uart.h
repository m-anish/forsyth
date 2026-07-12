/* uart.h — USART0 on PB2/PB3, 9600 8N1, blocking TX, ring-buffered RX.
 * The SHARED bus: exactly one of {E220, PMS7003} is powered when this is
 * active (hal.c rails enforce it). 9600 everywhere — the E220's PROGRAM
 * mode requires it, and never changing baud means never re-initializing the
 * peripheral around module mode changes (lokki lesson).                     */
#ifndef FORSYTH_UART_H
#define FORSYTH_UART_H

#include <stdint.h>

void    uart_init(void);            /* enable + hand PB2 to the USART        */
void    uart_deinit(void);          /* disable + PB2 back to GPIO-low        */
void    uart_tx(const uint8_t *d, uint16_t len);
void    uart_rx_flush(void);
/* Read up to max bytes, giving up after gap_ms of silence once at least one
 * byte has arrived, or timeout_ms with nothing. Returns count.              */
uint16_t uart_rx_collect(uint8_t *buf, uint16_t max,
                         uint16_t timeout_ms, uint16_t gap_ms);

#endif
