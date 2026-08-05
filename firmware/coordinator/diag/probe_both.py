from machine import UART, Pin
import time
def probe(uart_id, orients, m0p, m1p, aux_p, name):
    m0=Pin(m0p,Pin.OUT); m1=Pin(m1p,Pin.OUT); aux=Pin(aux_p,Pin.IN)
    m0.value(1); m1.value(1); time.sleep_ms(120)   # PROGRAM
    print('%s AUX=%d'%(name, aux.value()))
    for tx,rx in orients:
        u=UART(uart_id,baudrate=9600,tx=tx,rx=rx,timeout=300); time.sleep_ms(30)
        if u.any(): u.read()
        u.write(bytes([0xC1,0x00,0x08])); time.sleep_ms(300)
        r=u.read(); u.deinit()
        tag=''
        if r and len(r)>=11 and r[0] in (0xC1,0xC2):
            tag=' -> CHAN=%d REG0=0x%02x CRYPT=%02x%02x  <<<WORKS'%(r[7],r[5],r[9],r[10])
        print('  tx=%d rx=%d reply=%r%s'%(tx,rx,r,tag))
    m0.value(0); m1.value(0)
probe(1, [(18,17),(17,18)], 8, 9, 10, 'E220-1')
time.sleep_ms(200)
probe(2, [(4,5),(5,4)], 6, 7, 15, 'E220-2')
