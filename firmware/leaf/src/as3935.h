/* as3935.h — AMS AS3935 lightning sensor (DFRobot SEN0290 on Board B).
 * Always powered (VBAT, 60–80 µA listening — the design accepts this).
 * IRQ line → PC0, idles low, pulses high on event.                          */
#ifndef FORSYTH_AS3935_H
#define FORSYTH_AS3935_H

#include <stdint.h>

/* IRQ reasons, as read from REG 0x03 low nibble */
#define AS3935_INT_NOISE     0x01
#define AS3935_INT_DISTURBER 0x04
#define AS3935_INT_LIGHTNING 0x08

uint8_t as3935_init(void);      /* preset, RCO cal, apply g_cfg tuning        */
uint8_t as3935_apply_cfg(void); /* re-push AFE/NF/WDTH/SREJ/etc from g_cfg    */
/* Service an IRQ: waits the datasheet-mandated 2 ms, reads the reason.
 * On lightning also fills distance (raw 6-bit) and energy (21-bit).         */
uint8_t as3935_service(uint8_t *reason, uint8_t *distance, uint32_t *energy);

#endif
