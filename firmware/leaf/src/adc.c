#include <avr/io.h>
#include <string.h>

#include "adc.h"
#include "config.h"
#include "pins.h"
#include "hal.h"

/* tinyAVR 2-series 12-bit ADC. The ADC is enabled per-read and shut off
 * after — it draws real current and every read here is seconds apart.       */

/* CTRLC.TIMEBASE must hold the number of CLK_PER cycles in 1 µs,
 * rounded up: 5 at F_CPU = 5 MHz. Field starts at bit 3.                    */
#define ADC_TIMEBASE_VALUE ((((F_CPU + 999999UL) / 1000000UL) << 3) & ADC_TIMEBASE_gm)

static void adc_on(uint8_t refsel)
{
    ADC0.CTRLA = ADC_ENABLE_bm;
    /* CLK_ADC = 5 MHz / 4 = 1.25 MHz — inside the 300 kHz–6 MHz spec.       */
    ADC0.CTRLB = ADC_PRESC_DIV4_gc;
    ADC0.CTRLC = refsel | ADC_TIMEBASE_VALUE;
    /* Long sample duration: the battery divider's Thevenin source is ~250 k,
     * far above the datasheet's recommended source impedance — C20 (100 nF)
     * holds the node, the long SAMPDUR lets the S/H settle from it. Costs
     * nothing for the low-impedance vane ladder, so use it for both.        */
    ADC0.CTRLE = 128;
}

static void adc_off(void) { ADC0.CTRLA = 0; }

static uint16_t adc_single(uint8_t muxpos)
{
    ADC0.MUXPOS  = muxpos;
    ADC0.COMMAND = ADC_MODE_SINGLE_12BIT_gc | ADC_START_IMMEDIATE_gc;
    while (!(ADC0.INTFLAGS & ADC_RESRDY_bm)) {}
    return ADC0.RESULT;   /* reading RESULT clears RESRDY */
}

uint16_t adc_read_vane(void)
{
    /* Ratiometric: ladder excitation is the VBAT rail, which IS the MCU's
     * VDD — with VDD as the reference the cell voltage cancels exactly.
     * Median-of-N kills the odd reed-bounce or EMI sample.                  */
    uint16_t s[VANE_ADC_SAMPLES];
    adc_on(ADC_REFSEL_VDD_gc);
    /* PA6 input buffer stays disabled (gpio_init) — fine for analog.        */
    for (uint8_t i = 0; i < VANE_ADC_SAMPLES; i++)
        s[i] = adc_single(VANE_AIN);
    adc_off();
    /* insertion sort; N is tiny */
    for (uint8_t i = 1; i < VANE_ADC_SAMPLES; i++) {
        uint16_t v = s[i]; int8_t j = i - 1;
        while (j >= 0 && s[j] > v) { s[j + 1] = s[j]; j--; }
        s[j + 1] = v;
    }
    return s[VANE_ADC_SAMPLES / 2];
}

uint16_t adc_read_batt_mv(void)
{
    /* 1 M / 330 k divider → VBAT/4.03 lands under the 1.024 V internal
     * reference for any legal cell voltage (3.65/4.03 = 0.906 V).           */
    adc_on(ADC_REFSEL_1024MV_gc);
    uint32_t acc = 0;
    for (uint8_t i = 0; i < 4; i++) acc += adc_single(VBAT_AIN);
    adc_off();
    uint32_t raw = acc / 4;                        /* 0..4095 of 1024 mV     */
    uint32_t node_mv = (raw * 1024UL) / 4096UL;
    return (uint16_t)((node_mv * VBAT_DIV_NUM) / 1000UL);
}

int16_t adc_read_mcu_temp_x100(void)
{
    /* 2-series internal sensor, per datasheet "Temperature Measurement":
     * 12-bit read against the 1.024 V reference, then the SIGROW slope/offset
     * words give Kelvin. Factory cal is ±3 °C — MCU_TEMP_OFFSET_X100 in
     * config.h is the bench trim. This value gates LiFePO4 charging, so
     * bench-verify it near 0 °C (freezer + reference thermometer).          */
    adc_on(ADC_REFSEL_1024MV_gc);
    ADC0.CTRLE = 128;
    uint16_t raw = adc_single(ADC_MUXPOS_TEMPSENSE_gc);
    adc_off();

    uint16_t sigrow_offset = SIGROW.TEMPSENSE1;
    uint16_t sigrow_slope  = SIGROW.TEMPSENSE0;
    int32_t t = (int32_t)raw - (int32_t)sigrow_offset;
    t *= (int32_t)sigrow_slope;          /* result in K, <<12               */
    t += 0x0800;                         /* round to nearest                */
    t >>= 12;                            /* Kelvin */
    int32_t c_x100 = (t - 273) * 100;
    return (int16_t)(c_x100 + MCU_TEMP_OFFSET_X100);
}
