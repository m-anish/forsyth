/* sensors.h — Board B I2C sensors: SHTC3 (temp/RH owner) and BME280
 * (pressure only, by policy — its temp is used solely for compensation).
 * All return 0 on success.                                                  */
#ifndef FORSYTH_SENSORS_H
#define FORSYTH_SENSORS_H

#include <stdint.h>

#define SHTC3_ADDR  0x70
#define BME280_ADDR 0x76   /* SmartElex breakout default; 0x77 alt — if the
                              I2C scan at bring-up finds 0x77, change here    */

uint8_t shtc3_read(int16_t *temp_c_x100, uint16_t *rh_x100);

uint8_t bme280_init(void);                      /* reads trimming, configures */
uint8_t bme280_read_pressure(uint32_t *pa);     /* forced-mode one-shot       */

#endif
