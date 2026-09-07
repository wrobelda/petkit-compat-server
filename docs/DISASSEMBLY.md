# Disassembly and firmware analysis

This guide is for developers adding a device profile or verifying a firmware
format. Start with [CONTRIBUTING.md](CONTRIBUTING.md), and keep all firmware
images, flash dumps, captures, credentials, and generated disassembly outside
Git.

## Reuse the existing analysis

Before opening a disassembler, inspect the nearest existing device and layout:

- [Petkit API reference](PETKIT-API.md) records behavior already considered
  common across profiles;
- [Fresh Element Mini hardware](../devices/esp8266/nonos_v2/fresh-element-mini/HARDWARE.md)
  separates board facts from network behavior;
- [Fresh Element Mini OTA research](../devices/esp8266/nonos_v2/fresh-element-mini/OTA-RESEARCH.md)
  records verified update behavior, corrected addresses, and unresolved claims;
- [`devices/esp8266/nonos_v2/image.py`](../devices/esp8266/nonos_v2/image.py)
  parses the known V2 container;
- [`devices/esp8266/nonos_v2/tools/analyze_stock_ota.py`](../devices/esp8266/nonos_v2/tools/analyze_stock_ota.py)
  locates and validates V2 user-bin slots in a full flash dump;
- [`devices/esp8266/nonos_v2/tools/disassemble.py`](../devices/esp8266/nonos_v2/tools/disassemble.py)
  maps an extracted V2 file offset to its Xtensa VMA and annotates literal
  loads;
- [tests](../tests/) contain sanitized request evidence and executable format
  expectations.

Do not recreate one of these helpers under a new name. If a new device differs,
first identify whether the difference belongs to the platform, firmware layout,
device profile, or one firmware release.

## Preserve the analysis source

A downloaded OTA image is not a substitute for a full-flash backup. The backup
can establish:

- the bootloader and flash-mode settings;
- every physical application slot and the selected OTA layout;
- protected RF-calibration and SDK-parameter sectors;
- older firmware retained in an inactive slot;
- persisted configuration and device-specific structures;
- whether an extracted update matches the bytes installed in flash.

For an ESP8266 non-OS V2 device, follow the [backup and recovery
guide](../devices/esp8266/nonos_v2/HARDWARE.md). Read the flash twice and compare
the files before using either copy as evidence.

## Useful tools

Use tools appropriate to the processor and container instead of treating the
whole flash as one flat executable:

- `esptool` communicates with the ROM bootloader on supported Espressif chips,
  reads and writes flash, and reports chip and flash properties;
- `xtensa-linux-gnu-objcopy` and `xtensa-linux-gnu-objdump` convert and
  disassemble Xtensa LX106 regions;
- an ESP8266 PlatformIO toolchain supplies `xtensa-lx106-elf-*` when the system
  toolchain is unavailable;
- `arm-none-eabi-objdump` or Capstone with `CS_ARCH_ARM` and `CS_MODE_THUMB`
  disassembles Cortex-M0 firmware;
- Ghidra, Rizin, or radare2 supports cross-reference exploration and manual
  function annotation;
- `tshark` and Wireshark correlate firmware code with authorized network
  captures;
- `binwalk`, `strings`, `xxd`, and `hexdump` help inventory an unknown image,
  but their output is a lead rather than proof.

Python Capstone is also sufficient for the small Cortex-M0 checks used by the
Petkit ESPHome research.

## Establish address mappings first

Derive mappings from the container header before naming functions. For the
known ESP8266 V2 user-bin, irom data starts at file offset `0x10` and maps to
VMA `0x40200000`:

```text
VMA = 0x40200000 + (file_offset - 0x10)
file_offset = (VMA - 0x40200000) + 0x10
```

An absolute irom pointer embedded by the linker can use a different conversion
from the file offset of the instruction that loads it. Use the existing
`disassemble.py` mappings, and record both the VMA and file offset for every
claim. A previous Fresh Element Mini analysis mixed these bases and falsely
identified a motor-control function as the user2 OTA handler.

Parse RAM segments separately. Confirm their load addresses, lengths, checksum,
and overlap rules before disassembling them at their declared addresses.

## Distinguish firmware and flash layouts

Firmware and flash layouts vary by processor, SDK, bootloader, vendor, and
sometimes product revision. Image headers, physical offsets, mapped addresses,
protected parameter regions, and update-slot selection are part of a firmware
format; matching the processor alone does not establish compatibility.

For example, an ESP8266 may use a single E9 image, paired non-OS SDK V2 user-bin
slots, an Arduino eboot layout, or a vendor-specific variation. ESP32 devices
use partition tables and image rules that differ again. Devices based on other
processors have their own executable formats, boot metadata, and update rules.

Determine both the source and destination layouts before offering an update.
An ordinary replacement image may not be valid for the source firmware's OTA
client, even when both images run on the same chip. As one concrete example,
[`wrobelda/petkit-element-mini-esphome`](https://github.com/wrobelda/petkit-element-mini-esphome#installation)
uses a stock-compatible non-OS V2 transition image from a tested
[ESPHome Kickstart fork](https://github.com/wrobelda/esphome-kickstart) to
install ESPHome on the [Fresh Element
Mini](../devices/esp8266/nonos_v2/fresh-element-mini/). The generic transition
changes are intended for the canonical
[ESPHome Kickstart](https://github.com/libretiny-eu/esphome-kickstart) project.
The transition image then replaces the Petkit bootloader with ESPHome's eboot
V1 layout. Separate staged-migration precedents include
[Tuya-Convert](https://github.com/ct-Open-Source/tuya-convert) and
[SonOTA](https://github.com/mirko/SonOTA), but their containers, offsets, and
trust assumptions are not interchangeable.

When a transition is required, document and test each boundary separately:

- the vendor OTA client accepts and writes the transition container;
- the vendor bootloader loads the transition image from every supported source
  slot;
- the transition image relocates itself when overwriting its running region
  would be unsafe;
- the transition image validates the complete destination image before
  replacing the bootloader;
- the destination bootloader and application boot after the layout change;
- the recovery procedure preserves every region outside the intended write.

## Build evidence from independent paths

Use at least two independent forms of evidence for a load-bearing conclusion
when possible:

- a static call path and a controlled runtime trace;
- disassembly from both sides of a serial protocol;
- a parsed image and bytes read back from flash;
- a packet capture and the code that constructs or consumes the message;
- a hardware measurement and the corresponding GPIO configuration.

Classify findings as hardware-verified, runtime-proven, disassembly-proven,
trace-derived, inferred, or unresolved. A nearby log string does not name a
function, a function prologue does not prove two functions have the same role,
and a valid checksum does not prove that an image will boot.

Keep corrections beside the superseded claim or remove the bad claim when it
has no continuing research value. Do not let an old address or hypothesis
survive as user-facing installation advice.

## Direct coding agents precisely

Give an agent a bounded question and the exact artifacts it may inspect. A good
task names:

- the processor, firmware file, container, and expected address space;
- the known function, route, string, packet, or hardware event to trace;
- the existing project scripts and research that must be checked first;
- the output format: exact VMAs and file offsets, callers and callees, evidence
  level, contradictions, and unresolved branches;
- the prohibition on changing files when the task is an independent review.

For important conclusions, ask a second agent to reproduce the result without
being told the first agent's conclusion. Then give both agents the conflicting
claims and require adjudication from primary source: source code, instructions,
binary structure, hardware measurements, or runtime traces. Do not resolve a
conflict by counting votes.

Avoid broad prompts such as “understand this firmware.” Split the work into
container parsing, boot flow, one protocol handler, one state machine, or one
hardware signal. Require the agent to distinguish the Petkit Android app, stock
device firmware, motor-controller firmware, OTA client, and compatibility
server by name.

## Record reusable results

Put device facts in `HARDWARE.md`, device update analysis in `OTA-RESEARCH.md`,
shared Petkit behavior in [PETKIT-API.md](PETKIT-API.md), and executable format
rules in the nearest parser and tests. Keep exploratory notes out of the normal
installation workflow. A regular user should not need to understand
disassembly to install a supported profile.
