"""protocol.py — FLP v1 codec, coordinator side.

Mirror of firmware/PROTOCOL.md (authoritative) and leaf/src/protocol.h.
Change all three together or not at all.
"""
import struct

MAGIC = 0xF5
VERSION = 0x01

T_READING = 0x01
T_LIGHTNING = 0x02
T_STATUS = 0x03
T_ACK = 0x10

# flags
F_CHG_INHIBIT = 1 << 0
F_LOW_BATT = 1 << 1
F_SAFE_MODE = 1 << 2
F_BOOT = 1 << 3
F_VANE_FAULT = 1 << 4
F_I2C_FAULT = 1 << 5
F_PMS_FAULT = 1 << 6
F_CFG_APPLIED = 1 << 7

# reading mask bits -> (name, struct fmt, scale). Order == bit order == packing order.
_READING_FIELDS = (
    ("temp_c", "<h", 0.01),
    ("rh", "<H", 0.01),
    ("pressure_pa", "<I", 1),
    ("wind_avg_ms", "<H", 0.01),      # cm/s on the wire
    ("wind_gust_ms", "<H", 0.01),
    ("wind_dir_deg", "<H", 0.1),
    ("rain_tips", "<H", 1),           # cumulative; main.py converts to mm
    ("pm1", "<H", 1),
    ("pm25", "<H", 1),
    ("pm10", "<H", 1),
    ("batt_v", "<H", 0.001),          # mV on the wire
    ("vane_adc", "<H", 1),
    ("mcu_temp_c", "<h", 0.01),
    ("ltg_stats", "3B", 1),
)

# ACK TLV types (encode side)
TLV_INTERVAL = 0x01
TLV_AQI_N = 0x02
TLV_AS3935 = 0x03
TLV_TEMP_OFS = 0x04
TLV_CHG_POLICY = 0x05
TLV_ANEMO_CAL = 0x06
TLV_VERBOSE = 0x07
TLV_REBOOT = 0x7E
TLV_FACTORY = 0x7F


def crc16(data):
    """CRC-16/CCITT-FALSE — must match flp_crc16 in leaf/src/protocol.h."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def parse(frame):
    """Validate and decode one frame. Returns a dict or None (bad frame).

    Result always has: type, station_id, seq, flags. Payload fields per type:
      READING   -> the _READING_FIELDS present in the mask
      LIGHTNING -> count, distance (None if out-of-range 0x3F), energy, age_s
      STATUS    -> fw_version, reset_cause, cfg_crc, boot_count,
                   radio_nvram_ok, vane_adc, batt_v
    """
    if len(frame) < 8 or frame[0] != MAGIC or frame[1] != VERSION:
        return None
    if crc16(frame[:-2]) != struct.unpack("<H", frame[-2:])[0]:
        return None
    out = {"type": frame[2], "station_id": frame[3],
           "seq": frame[4], "flags": frame[5]}
    body = frame[6:-2]

    if out["type"] == T_READING:
        if len(body) < 2:
            return None
        mask = struct.unpack("<H", body[:2])[0]
        o = 2
        for bit, (name, fmt, scale) in enumerate(_READING_FIELDS):
            if not (mask & (1 << bit)):
                continue
            size = struct.calcsize(fmt)
            if o + size > len(body):
                return None
            vals = struct.unpack(fmt, body[o:o + size])
            o += size
            out[name] = vals if len(vals) > 1 else (
                vals[0] * scale if scale != 1 else vals[0])
        # tidy floats
        for k in ("temp_c", "rh", "wind_avg_ms", "wind_gust_ms",
                  "wind_dir_deg", "batt_v", "mcu_temp_c"):
            if k in out:
                out[k] = round(out[k], 3)
    elif out["type"] == T_LIGHTNING:
        if len(body) != 8:
            return None
        count, dist, energy, age = struct.unpack("<BBIH", body)
        out.update(count=count, energy=energy, age_s=age,
                   distance=None if dist >= 0x3F else dist)
    elif out["type"] == T_STATUS:
        if len(body) != 12:
            return None
        (out["fw_version"], out["reset_cause"], out["cfg_crc"],
         out["boot_count"], out["radio_nvram_ok"], out["vane_adc"],
         batt_mv) = struct.unpack("<HBHHBHH", body)
        out["batt_v"] = round(batt_mv * 0.001, 3)
    else:
        return None
    return out


def build_ack(station_id, acked_seq, tlvs=b""):
    """ACK frame for a leaf. tlvs = pre-encoded bytes; n_tlv counted here."""
    n = 0
    o = 0
    while o + 2 <= len(tlvs):
        o += 2 + tlvs[o + 1]
        n += 1
    frame = bytes([MAGIC, VERSION, T_ACK, station_id, 0, 0, acked_seq, n]) + tlvs
    return frame + struct.pack("<H", crc16(frame))


def tlv(t, payload=b""):
    return bytes([t, len(payload)]) + payload


def tlvs_from_cmd(cmd):
    """Translate a forsyth/<slug>/cmd JSON dict into TLV bytes.

    Accepted keys (see PROTOCOL.md §2 ACK table):
      report_interval_s, aqi_every_n, temp_offset_c, anemo_ms_per_hz,
      verbose, reboot, factory_reset,
      chg_policy: {mode, low_c, hyst_c},
      as3935: {afe_outdoor, noise_floor, watchdog, spike_rej,
               min_strikes, mask_disturbers}
    Unknown keys are ignored (with a console note) rather than erroring.
    """
    out = b""
    for key, val in cmd.items():
        if key == "report_interval_s":
            out += tlv(TLV_INTERVAL, struct.pack("<H", int(val)))
        elif key == "aqi_every_n":
            out += tlv(TLV_AQI_N, bytes([int(val) & 0xFF]))
        elif key == "temp_offset_c":
            out += tlv(TLV_TEMP_OFS, struct.pack("<h", int(round(val * 100))))
        elif key == "anemo_ms_per_hz":
            out += tlv(TLV_ANEMO_CAL, struct.pack("<H", int(round(val * 1000))))
        elif key == "verbose":
            out += tlv(TLV_VERBOSE, bytes([1 if val else 0]))
        elif key == "chg_policy":
            out += tlv(TLV_CHG_POLICY, struct.pack(
                "<BbB", int(val.get("mode", 0)),
                int(val.get("low_c", 0)), int(val.get("hyst_c", 2))))
        elif key == "as3935":
            out += tlv(TLV_AS3935, bytes([
                1 if val.get("afe_outdoor", 1) else 0,
                int(val.get("noise_floor", 2)) & 7,
                min(int(val.get("watchdog", 2)), 10),
                min(int(val.get("spike_rej", 2)), 11),
                int(val.get("min_strikes", 0)) & 3,
                1 if val.get("mask_disturbers", 1) else 0]))
        elif key == "reboot" and val:
            out += tlv(TLV_REBOOT)
        elif key == "factory_reset" and val:
            out += tlv(TLV_FACTORY)
        else:
            print("cmd: ignoring unknown key %r" % key)
    return out
