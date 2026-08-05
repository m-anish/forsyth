# main.py — coordinator RX for Step 5. Configures E220-1 to MATCH the leaf
# (ch15, air2400, crypt 0x0F57, FIXED mode, RSSI byte on) with monitor address
# 0xFFFF so it hears every packet on the channel. Flashes the RGB LED GREEN
# (600ms) on any received bytes; prints them.
from machine import UART, Pin
import neopixel, time

m0 = Pin(8, Pin.OUT); m1 = Pin(9, Pin.OUT); aux = Pin(10, Pin.IN)
u = UART(1, baudrate=9600, tx=17, rx=18, timeout=100)
np = neopixel.NeoPixel(Pin(48, Pin.OUT), 1)
def led(c): np[0] = c; np.write()
def waux(lvl, ms):
    e = time.ticks_add(time.ticks_ms(), ms)
    while aux.value() != lvl:
        if time.ticks_diff(e, time.ticks_ms()) <= 0: return False
        time.sleep_ms(2)
    return True

# monitor addr 0xFFFF, 9600/2400, 10dBm, ch15, RSSI+fixed, crypt 0F57
pl = bytes([0xFF, 0xFF, 0x62, 0x03, 15, 0xC3, 0x0F, 0x57])
m0.value(1); m1.value(1); time.sleep_ms(60); waux(1, 800)
if u.any(): u.read()
u.write(bytes([0xC2, 0x00, 0x08]) + pl); time.sleep_ms(150)
echo = u.read()
m0.value(0); m1.value(0); time.sleep_ms(60); waux(1, 800)
print('coord RX config ch15/crypt0F57/fixed/monitor ->',
      'OK' if (echo and len(echo) >= 8 and echo[7] == 15) else 'FAIL', echo)

led((0, 0, 8))          # dim blue = listening
n = 0
while True:
    if u.any():
        d = u.read()
        n += 1
        print('RX #%d (%d bytes): %r' % (n, len(d) if d else 0, d))
        led((0, 60, 0)); time.sleep_ms(600); led((0, 0, 8))   # 600ms green on RX
    time.sleep_ms(20)
