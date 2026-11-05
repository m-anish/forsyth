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
#   BODCFG = 0x44  (was 0x00, BOD fully off)
#       LVL      bits 7:5 = 0b010 -> 2.6 V  (only 1.8 / 2.6 / 4.2 exist; 4.2 is
#                                            above the cell, 1.8 is the MCU's
#                                            own floor and so catches nothing
#                                            until the part is already lost)
#       ACTIVE   bits 3:2 = 0b01  -> enabled, continuous
#       SLEEP    bits 1:0 = 0b00  -> disabled
#
#   Why: BOD off was a deliberate call — the firmware's soft-UVLO
#   (BATT_CRIT_MV) plus the BMS parachute cover *slow* undervoltage. They do
#   not cover a FAST sag under the E220's TX surge, and with BOD off the
#   datasheet gives no behaviour at all below the operating envelope: the part
#   simply hangs, leaving no trace, until the rail recovers. That is the
#   unexplained "button stops responding" symptom. BOD turns it into a clean
#   reset that reports itself as BORF (0x02) in the STATUS packet's
#   reset_cause. 2.6 V sits between the 2.8 V soft-UVLO and the ~2.4 V BMS cut,
#   so normal operation never reaches it.
#
#   Cost: BOD draws current only in ACTIVE mode, and the leaf is asleep for
#   ~99 % of its duty cycle, so the sleep floor is untouched. SLEEP=disabled
#   makes that explicit rather than relying on it.
#
#   Set it (once per chip):
#     pymcuprog write -t uart -u $(PORT) -d $(MCU) -m fuses -o 1 -l 0x44
#   Revert to no BOD:
#     pymcuprog write -t uart -u $(PORT) -d $(MCU) -m fuses -o 1 -l 0x00
#   Verify what's on the part:
#     pymcuprog read -t uart -u $(PORT) -d $(MCU) -m fuses

clean:
	rm -rf $(BUILD)

.PHONY: all size flash clean
