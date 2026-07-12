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

# Fuses: factory defaults are correct for this design (20 MHz osc, UPDI kept,
# BOD off — the firmware's soft-UVLO + the BMS parachute cover undervoltage).
# To verify what's on the part:
#   pymcuprog read -t uart -u $(PORT) -d $(MCU) -m fuses

clean:
	rm -rf $(BUILD)

.PHONY: all size flash clean
