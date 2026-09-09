# ESP8266 non-OS V2 layout, backup, and recovery

Espressif's non-OS SDK V2 OTA format uses a bootloader and two application
slots. The bootloader runs one slot while an OTA update normally writes the
other. Slot offsets and protected flash regions depend on the flash map, so use
the values from the selected device profile instead of assuming that every V2
device has the same addresses.

Read the device's `HARDWARE.md` before connecting a serial adapter. That file
defines its serial pads, boot-mode controls, power requirements, and any UART
shared with another processor.

## ESP8266 flash layout

The V2 format stores each application as an outer V2 header followed by mapped
IROM data, an inner V1 image with its RAM segments, an XOR checksum, and the
SDK CRC32 trailer. The format does not determine the flash size or slot
addresses.

Each device's `profile.json` defines its real flash size, application slots,
and safe extents. A safe extent may end before the next application offset
because RF calibration, SDK parameters, or vendor data can occupy the tail of
flash. Derive those boundaries from a complete stock dump before adding a
profile; never infer them only from the size of an application image.

## Back up the complete stock flash

The full flash contains the bootloader, both OTA application slots, RF and SDK
parameters, device identity, credentials, and saved configuration. Read it
twice before changing firmware so an unreliable serial transfer is detected.

Replace `PORT`, `FLASH_SIZE`, and the output names with values appropriate for
the device:

```sh
esptool --chip esp8266 --port PORT read-flash 0x0 FLASH_SIZE stock-a.bin
esptool --chip esp8266 --port PORT read-flash 0x0 FLASH_SIZE stock-b.bin
cmp stock-a.bin stock-b.bin
sha256sum stock-a.bin stock-b.bin
```

On macOS, use `shasum -a 256 stock-a.bin stock-b.bin` instead of `sha256sum`.

The files must match the profile's `firmware.flash_size`, `cmp` must produce no
output, and both hashes must match. Store one copy away from the development
machine. A stock dump can contain network, device, and account credentials, so
never commit or publish it.

Validate and optionally extract the V2 applications using the selected device
profile:

```sh
python3 devices/esp8266/nonos_v2/tools/analyze_stock_ota.py stock-a.bin \
  --profile devices/esp8266/nonos_v2/DEVICE/profile.json

python3 devices/esp8266/nonos_v2/tools/analyze_stock_ota.py stock-a.bin \
  --profile devices/esp8266/nonos_v2/DEVICE/profile.json \
  --extract-dir stock-slots
```

Every application must report valid segment and SDK CRC32 checksums.

## Restore one application slot

A slot-only restore leaves the other application and all system data
unchanged. Use it only when the affected slot is known and every other region
is known to be intact. Identify the slot from the OTA target, boot log, or
flash map; firmware age does not identify its physical location.

Write the extracted image at the matching `firmware.slots[].offset` from the
profile:

```sh
esptool --chip esp8266 --port PORT --baud 460800 write-flash \
  SLOT_OFFSET stock-slots/stock-SLOT_NAME.bin
```

Writing an application does not change the selected boot slot. If the selected
slot is unknown, establish it first or restore the complete flash.

## Restore the complete stock flash

Use the full backup when the affected regions are unknown or extend beyond one
application slot:

```sh
esptool --chip esp8266 --port PORT --baud 460800 write-flash \
  0x0 stock-a.bin
```

If the adapter or wiring is unreliable at 460800 baud, omit `--baud 460800`.
After the write succeeds, release the boot strap and power-cycle the device.
