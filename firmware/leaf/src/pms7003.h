/* pms7003.h — Plantower PMS7003 on the SHARED UART (see uart.h).
 * The sensor is hard power-gated (EN_AQI rail); SET/RESET pins are NC by
 * design — power is the on/off switch. One call = one full duty cycle.      */
#ifndef FORSYTH_PMS7003_H
#define FORSYTH_PMS7003_H

#include <stdint.h>

/* Rail up → warm-up (PMS_WARMUP_S, sleeping between seconds) → average
 * PMS_SAMPLES frames of the ATMOSPHERIC values → rail down.
 * Returns 0 on success. On any failure the rail still comes down.           */
uint8_t pms7003_measure(uint16_t *pm1, uint16_t *pm25, uint16_t *pm10);

#endif
