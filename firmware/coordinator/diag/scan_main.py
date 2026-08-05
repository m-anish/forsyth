# main.py — channel scanner. Sweeps the coordinator's E220 (E220-1, UART1,
# tx=17 rx=18) across all channels listening for the leaf's DIAG_LORATX
# 'FORSYTH' packets (transparent, 2400 air, no crypt). When it finds bytes it
# PARKS on that channel and keeps blinking so you can watch the LED:
#   green = clean FORSYTH,  amber = bytes but garbled (right ch, wrong crypt).
from machine import UART, Pin
import time, neopixel

TX, RX, M0P, M1P, AUXP = 17, 18, 8, 9, 10
m0 = Pin(M0P, Pin.OUT); m1 = Pin(M1P, Pin.OUT); aux = Pin(AUXP, Pin.IN)
u = UART(1, baudrate=9600, tx=TX, rx=RX, timeout=100)
np = neopixel.NeoPixel(Pin(48, Pin.OUT), 1)
def led(c): np[0] = c; np.write()

def waux(lvl, ms):
    e = time.ticks_add(time.ticks_ms(), ms)
    while aux.value() != lvl:
        if time.ticks_diff(e, time.ticks_ms()) <= 0: return False
        time.sleep_ms(2)
    return True

def set_ch(ch):
    pl = bytes([0x00, 0x00, 0x62, 0x00, ch, 0x00, 0x00, 0x00])  # 9600/2400, transparent, no crypt
    m0.value(1); m1.value(1); time.sleep_ms(60); waux(1, 700)
    if u.any(): u.read()
    u.write(bytes([0xC2, 0x00, 0x08]) + pl); time.sleep_ms(120)
    e = u.read()
    m0.value(0); m1.value(0); time.sleep_ms(60); waux(1, 700)
    return bool(e and len(e) >= 8 and e[7] == ch)

def listen(ms):
    end = time.ticks_add(time.ticks_ms(), ms); b = b''
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        if u.any(): b += u.read()
        time.sleep_ms(10)
    return b

print('SCANNER: sweeping 0-80 for the leaf; parks + blinks when found')
led((0, 0, 8))
found = None
while found is None:
    for ch in range(0, 81):
        set_ch(ch)
        if u.any(): u.read()
        b = listen(2300)
        if b and len(b) >= 4:                 # real packet, not a stray byte
            clean = b'FORS' in b
            print('FOUND ch %d  rx=%r  %s' % (ch, b, 'CLEAN' if clean else 'garbled(crypt?)'))
            led((0, 60, 0) if clean else (60, 30, 0)); time.sleep_ms(200)
            found = ch
            break
    if found is None:
        print('...nothing this sweep, repeating (is the leaf powered + blinking?)')

print('PARKED on channel %d — watch the LED' % found)
while True:                                    # stay here, blink on each packet
    b = listen(300)
    if b and len(b) >= 4:
        clean = b'FORS' in b
        print('ch %d rx=%r' % (found, b))
        led((0, 60, 0) if clean else (60, 30, 0)); time.sleep_ms(200); led((0, 0, 8))
