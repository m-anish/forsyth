# main.py — coordinator downlink TX for Step 4. Configures E220-1 to MATCH the
# leaf (ch15, air2400, crypt 0x0F57, FIXED mode, RSSI byte on), then sends a
# fixed-mode packet to the leaf (addr 0x0001, ch15) every ~1s. Coordinator LED
# blinks PURPLE per transmit. Leaf (DIAG_LORARX) should long-flash on receive.
from machine import UART, Pin
import neopixel, time

m0 = Pin(8, Pin.OUT); m1 = Pin(9, Pin.OUT); aux = Pin(10, Pin.IN)  # E220-1 ctrl
u = UART(1, baudrate=9600, tx=17, rx=18, timeout=200)              # E220-1, tx=17 rx=18
np = neopixel.NeoPixel(Pin(48, Pin.OUT), 1)
def led(c): np[0] = c; np.write()
def waux(lvl, ms):
    e = time.ticks_add(time.ticks_ms(), ms)
    while aux.value() != lvl:
        if time.ticks_diff(e, time.ticks_ms()) <= 0: return False
        time.sleep_ms(2)
    return True

# [ADDH ADDL REG0(9600/2400) REG1(0x03=10dBm) CHAN=15 REG3(0xC3 RSSI+fixed) CRYPT 0F57]
pl = bytes([0xFF, 0xFF, 0x62, 0x03, 15, 0xC3, 0x0F, 0x57])
m0.value(1); m1.value(1); time.sleep_ms(60); waux(1, 800)
if u.any(): u.read()
u.write(bytes([0xC2, 0x00, 0x08]) + pl); time.sleep_ms(150)
echo = u.read()
m0.value(0); m1.value(0); time.sleep_ms(60); waux(1, 800)
ok = bool(echo and len(echo) >= 8 and echo[7] == 15)
print('coord E220 config ch15/crypt0F57/fixed ->', 'OK' if ok else 'FAIL', echo)

led((0, 0, 8))
n = 0
while True:
    n = (n + 1) & 0xFF
    # fixed-mode header: dest ADDH=0x00 ADDL=0x01 (leaf STATION_ID), CHAN=15
    u.write(bytes([0x00, 0x01, 15]) + b'DL-TEST-' + bytes([n]))
    waux(1, 600)                       # wait for TX complete (AUX high)
    led((40, 0, 40)); time.sleep_ms(120); led((0, 0, 8))   # purple = transmitted
    time.sleep_ms(1000)
