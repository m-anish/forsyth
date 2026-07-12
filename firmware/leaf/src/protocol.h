/* protocol.h — FLP v1 wire format. Mirror of firmware/PROTOCOL.md; the .md is
 * authoritative, this file implements it. Counterpart: coordinator/src/protocol.py.
 */
#ifndef FORSYTH_PROTOCOL_H
#define FORSYTH_PROTOCOL_H

#include <stdint.h>
#include <stddef.h>

#define FLP_MAGIC        0xF5
#define FLP_VERSION      0x01

#define FLP_T_READING    0x01
#define FLP_T_LIGHTNING  0x02
#define FLP_T_STATUS     0x03
#define FLP_T_ACK        0x10

/* flags */
#define FLP_F_CHG_INHIBIT (1 << 0)
#define FLP_F_LOW_BATT    (1 << 1)
#define FLP_F_SAFE_MODE   (1 << 2)
#define FLP_F_BOOT        (1 << 3)
#define FLP_F_VANE_FAULT  (1 << 4)
#define FLP_F_I2C_FAULT   (1 << 5)
#define FLP_F_PMS_FAULT   (1 << 6)
#define FLP_F_CFG_APPLIED (1 << 7)

/* reading field-mask bits (payload packing order = bit order) */
#define FLP_R_TEMP     (1 << 0)   /* i16 °C ×100      */
#define FLP_R_RH       (1 << 1)   /* u16 % ×100       */
#define FLP_R_PRESS    (1 << 2)   /* u32 Pa           */
#define FLP_R_WAVG     (1 << 3)   /* u16 cm/s         */
#define FLP_R_WGUST    (1 << 4)   /* u16 cm/s         */
#define FLP_R_WDIR     (1 << 5)   /* u16 deg ×10      */
#define FLP_R_RAIN     (1 << 6)   /* u16 tips, cumulative, wraps */
#define FLP_R_PM1      (1 << 7)   /* u16 µg/m³        */
#define FLP_R_PM25     (1 << 8)   /* u16 µg/m³        */
#define FLP_R_PM10     (1 << 9)   /* u16 µg/m³        */
#define FLP_R_BATT     (1 << 10)  /* u16 mV           */
#define FLP_R_VANEADC  (1 << 11)  /* u16 raw          */
#define FLP_R_MCUTEMP  (1 << 12)  /* i16 °C ×100      */
#define FLP_R_LTGSTATS (1 << 13)  /* u8 strikes, u8 disturbers, u8 noise */

/* ACK TLV types */
#define FLP_TLV_INTERVAL   0x01
#define FLP_TLV_AQI_N      0x02
#define FLP_TLV_AS3935     0x03
#define FLP_TLV_TEMP_OFS   0x04
#define FLP_TLV_CHG_POLICY 0x05
#define FLP_TLV_ANEMO_CAL  0x06
#define FLP_TLV_VERBOSE    0x07
#define FLP_TLV_REBOOT     0x7E
#define FLP_TLV_FACTORY    0x7F

#define FLP_HDR_LEN   6
#define FLP_MAX_FRAME 64

/* CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflect, no xorout. */
static inline uint16_t flp_crc16(const uint8_t *d, size_t n)
{
    uint16_t crc = 0xFFFF;
    while (n--) {
        crc ^= (uint16_t)(*d++) << 8;
        for (uint8_t i = 0; i < 8; i++)
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021)
                                 : (uint16_t)(crc << 1);
    }
    return crc;
}

/* Little-endian append helpers for packet building. */
static inline size_t flp_put8(uint8_t *b, size_t o, uint8_t v)
{ b[o] = v; return o + 1; }
static inline size_t flp_put16(uint8_t *b, size_t o, uint16_t v)
{ b[o] = (uint8_t)v; b[o + 1] = (uint8_t)(v >> 8); return o + 2; }
static inline size_t flp_put32(uint8_t *b, size_t o, uint32_t v)
{ b[o] = (uint8_t)v; b[o+1] = (uint8_t)(v >> 8);
  b[o+2] = (uint8_t)(v >> 16); b[o+3] = (uint8_t)(v >> 24); return o + 4; }

/* Start a frame; returns payload offset. Finish with flp_seal(). */
static inline size_t flp_begin(uint8_t *b, uint8_t type, uint8_t station,
                               uint8_t seq, uint8_t flags)
{
    b[0] = FLP_MAGIC; b[1] = FLP_VERSION; b[2] = type;
    b[3] = station;   b[4] = seq;         b[5] = flags;
    return FLP_HDR_LEN;
}

/* Append CRC; returns total frame length. */
static inline size_t flp_seal(uint8_t *b, size_t len)
{
    uint16_t crc = flp_crc16(b, len);
    return flp_put16(b, len, crc);
}

/* Validate an incoming frame (magic/version/CRC). Returns 1 if ok. */
static inline uint8_t flp_valid(const uint8_t *b, size_t len)
{
    if (len < FLP_HDR_LEN + 2 || b[0] != FLP_MAGIC || b[1] != FLP_VERSION)
        return 0;
    uint16_t rx = (uint16_t)b[len - 2] | ((uint16_t)b[len - 1] << 8);
    return flp_crc16(b, len - 2) == rx;
}

#endif
