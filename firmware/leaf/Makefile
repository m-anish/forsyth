# Forsyth leaf firmware — ATtiny3226, bare-metal avr-gcc.
#
# Prerequisites (macOS) — verified working 2026-07-13 with avr-gcc 14.3.0:
#   brew tap osx-cross/avr && brew trust osx-cross/avr
#   brew install osx-cross/avr/avr-gcc@14      # bundles iotn3226.h — no DFP needed
#   pip install pymcuprog
#   The kegs are keg-only; put them on PATH for this shell:
#     export PATH="/usr/local/opt/avr-gcc@14/bin:/usr/local/opt/avr-binutils/bin:$PATH"
#   (Apple-silicon default brew prefix would be /opt/homebrew instead.)
#   If your avr-gcc is older and io.h complains about attiny3226, supply
#   Microchip's ATtiny_DFP from packs.download.microchip.com:
#     make ATPACK=$$HOME/toolchains/Atmel.ATtiny_DFP.2.0.368
#
# Flashing: SerialUPDI — any USB-serial adapter, TX→(1 k)→UPDI pad, RX→UPDI.
#   make flash PORT=/dev/tty.usbserial-XXXX
#
# Per-leaf identity: STATION_ID lives in src/config.h. Flash each leaf with
# its own id:  make clean && make STATION_ID=2 && make flash PORT=...

MCU     = attiny3226
F_CPU   = 5000000UL
TARGET  = forsyth-leaf
BUILD   = build

SRC = $(wildcard src/*.c)
OBJ = $(SRC:src/%.c=$(BUILD)/%.o)

CC      = avr-gcc
OBJCOPY = avr-objcopy
SIZE    = avr-size

CFLAGS  = -mmcu=$(MCU) -DF_CPU=$(F_CPU) -Os -std=gnu11 \
          -Wall -Wextra -Werror=implicit-function-declaration \
          -ffunction-sections -fdata-sections -g
LDFLAGS = -mmcu=$(MCU) -Wl,--gc-sections

ifdef ATPACK
CFLAGS  += -B $(ATPACK)/gcc/dev/$(MCU) -I $(ATPACK)/include
LDFLAGS += -B $(ATPACK)/gcc/dev/$(MCU)
endif

ifdef STATION_ID
CFLAGS += -DSTATION_ID_OVERRIDE=$(STATION_ID)
endif

# Bench diagnostic: hold the E220 5 V boost on so its rail can be measured.
#   make clean && make DIAG_BOOST=1 && make flash PORT=...
ifdef DIAG_BOOST
CFLAGS += -DDIAG_BOOST
endif

# Rain/anemometer diagnostic: LED blinks once per COUNTED pulse (rain = long,
# anemo = short). Hand-tip the bucket / hand-turn the cups and count blinks.
#   make clean && make DIAG_PULSE=1 && make flash PORT=...
ifdef DIAG_PULSE
CFLAGS += -DDIAG_PULSE
endif

# Sleep-floor measurement: no boost ever energised, so a uA range survives.
# Take two readings WITHOUT MOVING THE VANE and subtract — the vane divider
# alone is 26-403 uA depending on heading and will swamp the absolute number.
#   make clean && make DIAG_IDLE=1                   # production sleep
#   make clean && make DIAG_IDLE=1 DIAG_IDLE_PD=1    # pre-2026-11-06 baseline
ifdef DIAG_IDLE
CFLAGS += -DDIAG_IDLE
endif
ifdef DIAG_IDLE_PD
CFLAGS += -DDIAG_IDLE_PD
endif

# Wind pulse diagnostic: keeps the REAL sleep and bucketing, unlike DIAG_PULSE.
# LED: short = one revolution credited, long = a 10 s gate closed, flutter =
# pulses lost between the ISR and the bucket. Boot signature is 4 flashes.
#   make clean && make DIAG_WIND=1 && make flash PORT=...
ifdef DIAG_WIND
CFLAGS += -DDIAG_WIND
endif

# RF-link diagnostic: unconfigured (factory-default) E220, blind-send test
# packets. Pair with the coordinator debug listener.
#   make clean && make DIAG_LORATX=1 && make flash PORT=...
ifdef DIAG_LORATX
CFLAGS += -DDIAG_LORATX
endif

# RF RX diagnostic: real config (ch15/crypt/fixed) + listen; LED status codes.
#   make clean && make DIAG_LORARX=1 && make flash PORT=...
ifdef DIAG_LORARX
CFLAGS += -DDIAG_LORARX
endif

# RF TX diagnostic: real config + transmit every ~2s (exercises TX surge).
#   make clean && make DIAG_LORATXC=1 && make flash PORT=...
ifdef DIAG_LORATXC
CFLAGS += -DDIAG_LORATXC
endif

all: $(BUILD)/$(TARGET).hex size

$(BUILD)/%.o: src/%.c $(wildcard src/*.h) | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/$(TARGET).elf: $(OBJ)
	$(CC) $(LDFLAGS) $^ -o $@

$(BUILD)/$(TARGET).hex: $(BUILD)/$(TARGET).elf
	$(OBJCOPY) -O ihex -R .eeprom $< $@

$(BUILD):
	mkdir -p $(BUILD)

size: $(BUILD)/$(TARGET).elf
	$(SIZE) $<

flash: $(BUILD)/$(TARGET).hex
	pymcuprog write -t uart -u $(PORT) -d $(MCU) -f $< --erase --verify

# Fuses: factory defaults are right except BODCFG, which we now set.
#
#   BODCFG = 0x24  (was 0x44 = 2.6 V; before that 0x00, BOD fully off)
#       LVL      bits 7:5 = 0b001 -> 2.15 V
#       ACTIVE   bits 3:2 = 0b01  -> enabled, continuous
#       SLEEP    bits 1:0 = 0b00  -> disabled
#
#   EIGHT levels exist, not three. This comment used to say "only 1.8 / 2.6 /
#   4.2 exist", which is wrong and cost real debugging: datasheet 7.8.2.2
#   lists 1.8 / 2.15 / 2.60 / 2.95 / 3.30 / 3.70 / 4.00 / 4.30 V at LVL 0..7.
#   2.15 V was there the whole time and is the level this design wanted.
#
#   Why: BOD off was a deliberate call — the firmware's soft-UVLO
#   (BATT_CRIT_MV) plus the BMS parachute cover *slow* undervoltage. They do
#   not cover a FAST sag under the E220's TX surge, and with BOD off the
#   datasheet gives no behaviour at all below the operating envelope: the part
#   simply hangs, leaving no trace, until the rail recovers. That is the
#   unexplained "button stops responding" symptom. BOD turns it into a clean
#   reset that reports itself as BORF (0x02) in the STATUS packet's
#   reset_cause.
#
#   Why 2.15 and not 2.6: the original reasoning — sit between the 2.8 V
#   soft-UVLO and the ~2.4 V BMS cut so normal operation never reaches it —
#   is right, and 2.15 V still satisfies it by being below the BMS cut. What
#   2.6 V did NOT survive is the TRANSIENT: the boost inrush plus the E220 TX
#   pulse drag VDD through 2.6 V momentarily even on a healthy cell, and the
#   BOD then resets into the same sequence, forever (observed 2026-11-06,
#   ~0.7 s loop period). 2.15 V buys 0.45 V of sag headroom while keeping
#   0.35 V above the MCU's 1.8 V floor, so it still fires before the part is
#   out of spec — which was the real objection to 1.8 V, and remains valid.
#   If a loop survives 2.15 V, 1.8 V (0x04) is the next step and the core is
#   still in spec there at 5 MHz (see hal.c clock_init).
#
#   Cost: BOD draws current only in ACTIVE mode, and the leaf is asleep for
#   ~99 % of its duty cycle, so the sleep floor is untouched. SLEEP=disabled
#   makes that explicit rather than relying on it.
#
#   Set it (once per chip):
#     pymcuprog write -t uart -u $(PORT) -d $(MCU) -m fuses -o 1 -l 0x24
#   Revert to no BOD:
#     pymcuprog write -t uart -u $(PORT) -d $(MCU) -m fuses -o 1 -l 0x00
#   Verify what's on the part:
#     pymcuprog read -t uart -u $(PORT) -d $(MCU) -m fuses

clean:
	rm -rf $(BUILD)

.PHONY: all size flash clean
