/* adc.h — vane (ratiometric, VDD ref), battery (1.024 V ref), MCU temp. */
#ifndef FORSYTH_ADC_H
#define FORSYTH_ADC_H

#include <stdint.h>

uint16_t adc_read_vane(void);      /* median-of-N raw 12-bit counts          */
uint16_t adc_read_batt_mv(void);   /* millivolts at the cell, divider-corrected */
int16_t  adc_read_mcu_temp_x100(void); /* °C ×100, sigrow-calibrated + offset */

#endif
