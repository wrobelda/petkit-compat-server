# ESP8266 non-OS V2 backup and recovery

This procedure applies to [supported device profiles](../../README.md) whose profile declares
`firmware.format` as `esp8266-nonos-v2`. Read the device's `HARDWARE.md` first
for its serial pads, boot-mode controls, power requirements, flash size, and
any shared-UART constraints.

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

The files must match the profile's `firmware.flash_size`, `cmp` must produce no
output, and both hashes must match. Store one copy away from the development
machine. A stock dump can contain network, device, and account credentials, so
never commit or publish it.

Validate and optionally extract the V2 applications using the selected device
profile:

```sh
python3 devices/esp8266/nonos_v2/tools/analyze_stock_ota.py stock-a.bin \
  --profile devices/esp8266/DEVICE/profile.json

python3 devices/esp8266/nonos_v2/tools/analyze_stock_ota.py stock-a.bin \
  --profile devices/esp8266/DEVICE/profile.json \
  --extract-dir stock-slots
```

Every application must report valid segment and SDK CRC32 checksums.

## Restore one application slot

The non-OS OTA layout has two physical application slots. The bootloader runs
one while an OTA update normally writes the other. A slot-only restore leaves
the other application and all system data unchanged.

Use this method only when the affected slot is known and every other region is
known to be intact. Identify the slot from the OTA target, boot log, or flash
map; firmware age does not identify its physical location. Write the extracted
image at the matching `firmware.slots[].offset` from the profile:

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
  --flash-size FLASH_SIZE 0x0 stock-a.bin
esptool --chip esp8266 --port PORT verify-flash 0x0 stock-a.bin
```

If the adapter or wiring is unreliable at 460800 baud, omit `--baud 460800`.
After verification, release the boot strap and power-cycle the device.
