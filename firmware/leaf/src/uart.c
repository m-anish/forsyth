#include <avr/io.h>
#include <avr/interrupt.h>
#include <util/delay.h>

#include "uart.h"
#include "pins.h"

#define RXBUF_SIZE 128   /* power of two; PMS frame is 32 B, E220 replies ≤64 */

static volatile uint8_t rxbuf[RXBUF_SIZE];
static volatile uint8_t rx_head, rx_tail;

ISR(USART0_RXC_vect)
{
    uint8_t b = USART0.RXDATAL;
    uint8_t next = (uint8_t)((rx_head + 1) & (RXBUF_SIZE - 1));
    if (next != rx_tail) { rxbuf[rx_head] = b; rx_head = next; }
    /* overflow: drop newest — collectors resync on framing anyway */
}

void uart_init(void)
{
    rx_head = rx_tail = 0;
    /* 9600 @ F_CPU 5 MHz, normal mode: BAUD = 64*F_CPU/(16*baud) = 2083     */
    USART0.BAUD  = (uint16_t)((64UL * F_CPU) / (16UL * 9600UL));
    USART0.CTRLC = USART_CHSIZE_8BIT_gc;   /* 8N1 */
    USART0.CTRLA = USART_RXCIE_bm;
    USART0.CTRLB = USART_RXEN_bm | USART_TXEN_bm;
    UART_TX_PORT.DIRSET = UART_TX_bm;      /* USART takes the pad over       */
}

void uart_deinit(void)
{
    USART0.CTRLB = 0;
    USART0.CTRLA = 0;
    UART_TX_PORT.OUTCLR = UART_TX_bm;      /* park low (no back-powering)    */
    UART_TX_PORT.DIRSET = UART_TX_bm;
}

void uart_tx(const uint8_t *d, uint16_t len)
{
    while (len--) {
        while (!(USART0.STATUS & USART_DREIF_bm)) {}
        USART0.TXDATAL = *d++;
    }
    while (!(USART0.STATUS & USART_TXCIF_bm)) {}
    USART0.STATUS = USART_TXCIF_bm;        /* write-1-to-clear */
}

void uart_rx_flush(void) { rx_tail = rx_head; }

static int16_t rx_pop(void)
{
    if (rx_tail == rx_head) return -1;
    uint8_t b = rxbuf[rx_tail];
    rx_tail = (uint8_t)((rx_tail + 1) & (RXBUF_SIZE - 1));
    return b;
}

uint16_t uart_rx_collect(uint8_t *buf, uint16_t max,
                         uint16_t timeout_ms, uint16_t gap_ms)
{
    uint16_t n = 0, idle = 0, waited = 0;
    while (n < max) {
        int16_t b = rx_pop();
        if (b >= 0) { buf[n++] = (uint8_t)b; idle = 0; continue; }
        _delay_ms(1);
        if (n == 0) { if (++waited >= timeout_ms) break; }
        else        { if (++idle   >= gap_ms)     break; }
    }
    return n;
}
