from machine import UART, Pin
import neopixel, time
CH = 23   # common channel for both (fresh, avoids stale confusion)
def waux(aux, lvl, ms):
    e=time.ticks_add(time.ticks_ms(), ms)
    while aux.value()!=lvl:
        if time.ticks_diff(e,time.ticks_ms())<=0: return False
        time.sleep_ms(2)
    return True
def cfg(uid, tx, rx, m0p, m1p, auxp, ch, name):
    m0=Pin(m0p,Pin.OUT); m1=Pin(m1p,Pin.OUT); aux=Pin(auxp,Pin.IN)
    u=UART(uid,baudrate=9600,tx=tx,rx=rx,timeout=300)
    # ADDH ADDL REG0(9600/2400) REG1(0x03=10dBm) CHAN REG3(transparent) CRYPT
    pl=bytes([0x00,0x00,0x62,0x03,ch,0x00,0x00,0x00])
    m0.value(1); m1.value(1); time.sleep_ms(60); waux(aux,1,800)
    if u.any(): u.read()
    u.write(bytes([0xC2,0x00,0x08])+pl); time.sleep_ms(150)
    echo=u.read()
    m0.value(0); m1.value(0); time.sleep_ms(60); waux(aux,1,800); u.deinit()
    ok=bool(echo and len(echo)>=11 and echo[7]==ch)
    print('%s set ch=%d pwr=10dBm -> %s (echo chan=%s)'%(name,ch,'OK' if ok else 'FAIL', echo[7] if echo and len(echo)>=8 else '?'))
    return ok
print('=== Step3: set both to ch %d ==='%CH)
cfg(1,17,18,8,9,10,CH,'E220-1')
cfg(2,4,5,6,7,15,CH,'E220-2')
for p in (8,9,6,7): Pin(p,Pin.OUT,value=0)   # NORMAL both
time.sleep_ms(150)
u1=UART(1,baudrate=9600,tx=17,rx=18,timeout=200)
u2=UART(2,baudrate=9600,tx=4, rx=5, timeout=200)
np=neopixel.NeoPixel(Pin(48,Pin.OUT),1)
def led(c): np[0]=c; np.write()
def once(txu,rxu,tag):
    if rxu.any(): rxu.read()
    m=b'PING-'+tag+b'-0123456789'; txu.write(m); time.sleep_ms(500)
    g=rxu.read(); return (g is not None and b'PING' in g), g
print('=== Step2: loopback on ch %d ==='%CH)
a=b=0
for n in range(1,6):
    o12,g12=once(u1,u2,b'1to2'); time.sleep_ms(150)
    o21,g21=once(u2,u1,b'2to1'); a+=o12; b+=o21
    print('#%d 1->2 %s %r  2->1 %s %r'%(n,'OK' if o12 else '..',g12,'OK' if o21 else '..',g21))
    led((0,60,0) if(o12 and o21)else(60,0,0)); time.sleep_ms(250); led((0,0,0)); time.sleep_ms(500)
print('SUMMARY 1->2 %d/5  2->1 %d/5'%(a,b))
