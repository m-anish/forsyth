/* pins.h — Board A REV0 pin map, verbatim from hardware/boards/board-a-core.md §2.
 *
 * If a hardware revision moves a signal, change it HERE and nowhere else.
 * Every driver takes its pins from these macros. Format: port letter + bit.
 *
 * Hardware facts a future maintainer must not rediscover the hard way:
 *  - PB2/PB3 (USART0 default pins) are a SHARED UART: E220 radio and PMS7003
 *    both sit on it, each behind its own gated 5 V boost. Only one rail may be
 *    up at a time — this is a hardware invariant, enforced by power.c-style
 *    helpers in hal.c, not by hope.
 *  - PB3 must have its internal pull-up enabled while BOTH rails are down
 *    (the 10 k series clamp R2 leaves it floating otherwise), and UART_TX must
 *    be driven low before dropping either EN (else we back-power the gated
 *    module through its RX pin). Both rules from board-a-core.md §6 item 4.
 *  - PB5 STATUS LED is ACTIVE-LOW.
 *  - PB4 button shorts to GND; silk says RST but it is a GPIO (PA0 stays UPDI).
 *  - PA3 CHG_INHIBIT has a 100 k pulldown: MCU dead/reset ⇒ charging allowed.
 *    Driving it HIGH blocks charging (2N7002 grounds the CN3801 MPPT pin).
 */
#ifndef FORSYTH_PINS_H
#define FORSYTH_PINS_H

#include <avr/io.h>

/* -------- PORTA -------- */
#define EN_RADIO_PORT     PORTA   /* TPS61023 #1 EN — 5 V rail for E220      */
#define EN_RADIO_bm       PIN1_bm
#define EN_AQI_PORT       PORTA   /* TPS61023 #2 EN — 5 V rail for PMS7003   */
#define EN_AQI_bm         PIN2_bm
#define CHG_INHIBIT_PORT  PORTA   /* high = inhibit charging (fail-safe low) */
#define CHG_INHIBIT_bm    PIN3_bm
#define ANEMO_PORT        PORTA   /* reed pulse, internal pull-up, RC on board */
#define ANEMO_bm          PIN4_bm
#define ANEMO_CTRL        PIN4CTRL
#define RAIN_PORT         PORTA   /* tipping-bucket reed, internal pull-up   */
#define RAIN_bm           PIN5_bm
#define RAIN_CTRL         PIN5CTRL
#define VANE_AIN          ADC_MUXPOS_AIN6_gc   /* PA6 — ladder, ratiometric  */
#define VBAT_AIN          ADC_MUXPOS_AIN7_gc   /* PA7 — 1 M / 330 k divider  */

/* -------- PORTB -------- */
/* PB0 SCL / PB1 SDA: TWI0 default pins — Board B + Qwiic, pullups on Board B */
/* PB2 TXD / PB3 RXD: USART0 default pins — shared bus, see header comment    */
#define UART_TX_PORT      PORTB
#define UART_TX_bm        PIN2_bm
#define UART_RX_PORT      PORTB
#define UART_RX_bm        PIN3_bm
#define UART_RX_CTRL      PIN3CTRL
#define BTN_PORT          PORTB   /* service button to GND, active low       */
#define BTN_bm            PIN4_bm
#define BTN_CTRL          PIN4CTRL
#define LED_PORT          PORTB   /* status LED, ACTIVE-LOW                  */
#define LED_bm            PIN5_bm

/* -------- PORTC -------- */
#define AS3935_IRQ_PORT   PORTC   /* from Board B; AS3935 IRQ idles low,     */
#define AS3935_IRQ_bm     PIN0_bm /* pulses HIGH on event                    */
#define AS3935_IRQ_CTRL   PIN0CTRL
#define E220_M0_PORT      PORTC   /* mode pins: DRIVEN at all times the      */
#define E220_M0_bm        PIN1_bm /* module is powered — never floated       */
#define E220_M1_PORT      PORTC   /* (floating = weak pull-ups = deep sleep  */
#define E220_M1_bm        PIN2_bm /*  = the lokki 100-second bug)            */
#define E220_AUX_PORT     PORTC   /* module ready/busy; input, no pull-up    */
#define E220_AUX_bm       PIN3_bm /* while module is unpowered (leakage)     */
#define E220_AUX_CTRL     PIN3CTRL

#endif
