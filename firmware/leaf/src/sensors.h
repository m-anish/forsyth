/* sensors.h — Board B I2C environmental sensors. Priority stack (env_read):
 *   temp: a dedicated SHTx (SHT3x-DIS / SHTC3) if present, else the BMx280
 *   rh:   a dedicated SHTx if present, else a BME280 (BMP280 has no humidity)
 *   pressure: the BMx280 (BME280 0x60 / BMP280 0x58)
 * All read fns return 0 on success.                                          */
#ifndef FORSYTH_SENSORS_H
#define FORSYTH_SENSORS_H

#include <stdint.h>

#define SHTC3_ADDR  0x70
#define BME280_ADDR 0x76   /* SmartElex breakout default; 0x77 alt — if the
                              I2C scan at bring-up finds 0x77, change here    */
/* SHT3x-DIS lives at 0x44 (ADDR low) or 0x45 (ADDR high); sht_read tries both */

/* env_read result bits */
#define ENV_TEMP   0x01
#define ENV_RH     0x02
#define ENV_PRESS  0x04

uint8_t shtc3_read(int16_t *temp_c_x100, uint16_t *rh_x100);
uint8_t sht3x_read(uint8_t addr, int16_t *temp_c_x100, uint16_t *rh_x100);
uint8_t sht_read(int16_t *temp_c_x100, uint16_t *rh_x100);   /* SHT3x then SHTC3 */

uint8_t bme280_init(void);                                    /* trimming + config */
uint8_t bmx_read(int16_t *temp_c_x100, uint16_t *rh_x100,
                 uint32_t *pa, uint8_t *has_rh);              /* BMP280/BME280 */

/* combined read with the priority stack; returns ENV_* bitmask of valid fields */
uint8_t env_read(int16_t *temp_c_x100, uint16_t *rh_x100, uint32_t *pa);

#endif
