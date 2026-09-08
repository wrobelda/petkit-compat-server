# Adding support for another Petkit device

This guide is for developers who are analyzing a new device. People installing
an already supported device should use the [main installation
workflow](../README.md#install-a-supported-device).

## Start with existing project work

Read these documents before collecting new data or writing a new helper:

- [Petkit API reference](PETKIT-API.md) for behavior already separated from a
  particular device;
- [supported-device index](../devices/README.md) for existing profiles;
- each related device's `HARDWARE.md` and `OTA-RESEARCH.md`;
- the nearest platform and layout implementation, such as the [ESP8266 non-OS
  V2 image parser](../devices/esp8266/nonos_v2/image.py), [analysis
  tools](../devices/esp8266/nonos_v2/tools/), and [recovery
  guide](../devices/esp8266/nonos_v2/HARDWARE.md);
- the existing tests, which define accepted wire formats and redaction rules.

Reuse those implementations when the new evidence proves that the format is
the same. Extend a shared implementation only for behavior that belongs to the
shared format; keep unverified or device-specific behavior in the new profile.
Follow [Disassembly and firmware analysis](DISASSEMBLY.md) when static analysis
is required.

## Start with evidence

Before changing code, determine which parts of the existing protocol the new
device actually shares. Record evidence from hardware you own or are authorized
to test, and keep all credentials, packet captures, flash dumps, firmware
images, and runtime logs outside Git.

Read the complete flash twice before changing it. A verified backup is both the
recovery image and the analysis source: unlike a downloaded update, it preserves
the bootloader, every application slot, RF and SDK parameters, saved settings,
and device-specific data. Follow the nearest platform recovery guide, then store
one copy away from the development machine.

Confirm at least:

- the hardware platform and SDK or bootloader family;
- the flash size, application layout, and protected parameter regions;
- the setup-access-point name and provisioning transport;
- the provisioning request sequence and JSON field names;
- the API version, route family, and required startup requests;
- the exact firmware container and integrity checks, if OTA will be supported;
- a tested backup and recovery procedure.

Do not infer compatibility from a product name or enclosure.

## Directory layout

Place format-wide code and documentation under the platform and firmware-layout
directory:

```text
devices/
  PLATFORM/
    FIRMWARE_LAYOUT/
      HARDWARE.md
      image.py
      tools/
```

Place device-specific material below that directory:

```text
devices/PLATFORM/FIRMWARE_LAYOUT/DEVICE/
  README.md
  HARDWARE.md
  OTA-RESEARCH.md
  profile.json
  fixtures.json
  tools/
```

### Fixture inheritance

The server discovers `fixtures.json` files along the selected profile's
directory path, loading them in this order:

1. Repository root: routes shared by all profiles.
2. Platform directory: routes shared by that processor platform.
3. Firmware-layout directory: routes shared by that layout.
4. Device directory: routes specific to the selected device.

A nearer definition overrides an earlier route, so the device profile does
not need to list fixture files. Place each route at the narrowest level that
matches the available evidence; repository-wide fixtures live in
[`fixtures.json`](../fixtures.json).

Only add a shared helper after at least one device needs it and its boundary is
clear. Device-specific constants belong in `profile.json` or the device's
tools, not in the server core.

## Build the profile

Start with a synthetic fixture containing no live values. Add only the routes
required for a cold boot or another documented workflow. Configure the safe
request-field allowlist so logs expose field names and bounded operational
state, never credential values.

Document each profile value in the device README. A normal user must be able to
copy the profile path into the numbered workflow without understanding the
profile schema. Fixture files are discovered automatically from the selected
profile's directory and its parent directories.

If the device uses a new provisioning protocol or image format, add that as a
separate, testable implementation. Do not weaken an existing image validator to
accept an unverified variant.

## Test the support

Add sanitized request fixtures derived from the authorized capture. Tests must
cover:

- profile loading and validation;
- the minimum startup responses;
- safe request logging and redaction;
- provisioning-message encoding and response parsing;
- image parsing and rejection of malformed images, when OTA is supported;
- the device-specific OTA offer generator, when present.

Run the full suite from the repository root:

```sh
python3 -m unittest discover -s tests -v
```

Finally, exercise backup, provisioning, inert startup, OTA, and recovery on the
physical device. Update [the supported-device index](../devices/README.md) only
after those checks pass.
