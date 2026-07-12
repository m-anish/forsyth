"""e220.py — E220-900 transport for the always-on coordinator (MicroPython).

Direct descendant of lokki's lora_transport/lora_config pattern; the register
encoding must stay byte-identical to the leaf's e220.c build_regs(). Unlike
the leaf, the coordinator never power-gates its module, so registers are
written VOLATILE (0xC2) at every boot — config.py is the single source of
truth, module NVRAM stays untouched.

Coordinator address is 0xFFFF (Ebyte monitor mode: hears every frame on the
channel). Downlink is directed: fixed-mode header [0x00, unit_id, channel].
"""
import time
from machine import UART, Pin

import config

_CMD_WRITE_RAM = 0xC2
_CMD_RET = 0xC1

_AIR_BITS = {300: 0, 1200: 1, 2400: 2, 4800: 3,
             9600: 4, 19200: 5, 38400: 6, 62500: 7}
_PWR_BITS = {22: 0, 17: 1, 13: 2, 10: 3}


class E220:
    def __init__(self):
        p = config.LORA_PINS
        self._m0 = Pin(p["m0"], Pin.OUT, value=0)
        self._m1 = Pin(p["m1"], Pin.OUT, value=0)
        self._aux = Pin(p["aux"], Pin.IN)
        # 9600 always — PROGRAM mode requires it; constant baud means the
        # UART never needs a deinit/reinit around mode changes (lokki lesson)
        self._uart = UART(p["uart_id"], baudrate=9600,
                          tx=p["tx"], rx=p["rx"], timeout=50)

    # ---- AUX discipline ----
    def _wait_aux(self, level, timeout_ms):
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        while self._aux.value() != level:
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                return False
            time.sleep_ms(2)
        return True

    def _set_mode(self, m0, m1):
        time.sleep_ms(40)
        self._m0.value(m0)
        self._m1.value(m1)
        time.sleep_ms(40)
        self._wait_aux(1, 1000)
        time.sleep_ms(20)

    def _drain(self):
        n = self._uart.any()
        if n:
            self._uart.read(n)

    # ---- register config (volatile, every boot) ----
    def _reg_payload(self):
        c = config.LORA
        reg0 = (0b011 << 5) | (0b00 << 3) | _AIR_BITS[c["air_rate"]]  # 9600 8N1
        reg1 = (0b00 << 6) | _PWR_BITS[c["tx_power_dbm"]]             # subpkt 200
        reg3 = (1 << 7) | (1 << 6) | 0b011   # RSSI byte on, fixed mode, LBT off
        return bytes([0xFF, 0xFF, reg0, reg1, c["channel"], reg3,
                      c["crypt_h"], c["crypt_l"]])

    def configure(self):
        """Write volatile registers; returns True when the module echoes them."""
        payload = self._reg_payload()
        if not self._wait_aux(1, 2000):
            print("e220: AUX stuck low at boot — check wiring/power")
            return False
        self._set_mode(1, 1)                 # PROGRAM
        self._drain()
        self._uart.write(bytes([_CMD_WRITE_RAM, 0x00, 0x08]) + payload)
        self._wait_aux(0, 500)               # advisory low edge
        ok = self._wait_aux(1, 2000)
        time.sleep_ms(5)
        reply = self._uart.read()
        self._set_mode(0, 0)                 # NORMAL
        ok = bool(ok and reply and len(reply) >= 11 and
                  reply[0] == _CMD_RET and reply[3:11] == payload)
        print("e220: configured" if ok else
              "e220: config echo mismatch %r" % (reply,))
        return ok

    # ---- data path ----
    def recv(self):
        """Non-blocking-ish: returns (payload_bytes, rssi_dbm) or (None, None).

        Frames are delimited by UART idle gap (the module bursts a whole
        radio packet at once). The trailing byte is the module's RSSI —
        always stripped, because REG3 forces it on.
        """
        if not self._uart.any():
            return None, None
        buf = b""
        idle = 0
        while idle < 3:                      # 3 quiet 10 ms polls = end of frame
            chunk = self._uart.read()
            if chunk:
                buf += chunk
                idle = 0
            else:
                idle += 1
                time.sleep_ms(10)
        if len(buf) < 2:
            return None, None
        return buf[:-1], -(256 - buf[-1])

    def send_to(self, unit_id, payload):
        """Directed fixed-mode TX to a leaf. Two-edge AUX wait."""
        if not self._wait_aux(1, 1000):
            return False
        self._uart.write(bytes([0x00, unit_id & 0xFF,
                                config.LORA["channel"]]) + payload)
        self._wait_aux(0, 1000)              # module took the buffer
        return self._wait_aux(1, 5000)       # airtime done
