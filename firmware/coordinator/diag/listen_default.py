# main.py — dead-simple factory-default LoRa listener.
# NO config writes: the E220 runs on whatever it powered up with (factory
# default after a power-cycle), NORMAL/transparent mode. Blinks the RGB LED
# green on any received bytes. E220-1 on UART1, orientation tx=17 rx=18.
from machine import UART, Pin
import neopixel, time

Pin(8, Pin.OUT, value=0)     # M0 low
Pin(9, Pin.OUT, value=0)     # M1 low  -> NORMAL / transparent
time.sleep_ms(150)
u = UART(1, baudrate=9600, tx=17, rx=18, timeout=100)
np = neopixel.NeoPixel(Pin(48, Pin.OUT), 1)
def led(c): np[0] = c; np.write()

led((0, 0, 8))               # dim blue = listening, nothing yet
print('LISTEN: factory default, NORMAL, 9600, tx=17 rx=18')
n = 0
while True:
    if u.any():
        d = u.read()
        n += 1
        print('RX #%d (%d bytes): %r' % (n, len(d) if d else 0, d))
        led((0, 60, 0)); time.sleep_ms(200); led((0, 0, 8))
    time.sleep_ms(20)
