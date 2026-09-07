# Fresh Element Mini stock OTA

This document records device-specific evidence from the stock 2 MiB ESP8266
flash, stock-firmware disassembly, private packet captures, UART logs, and
controlled updates on the feeder. General behavior is in the [Petkit API
reference](../../../../docs/PETKIT-API.md), while serial access and the physical
flash map are in [Hardware](HARDWARE.md).

## Verified update sequence

The stock firmware uses these HTTP routes:

1. `POST /6/feedermini/dev_ota_check` requests update metadata.
2. `POST /6/feedermini/dev_ota_start` reports that an offer was accepted.
3. The feeder downloads the image with HTTP `Range` requests.
4. `POST /6/feedermini/dev_ota_heartbeat` reports update progress.
5. `POST /6/feedermini/dev_ota_complete` reports success or an OTA error.

An empty `result` object means that no update is available:

```json
{"result":{}}
```

An accepted offer has this shape:

```json
{
  "result": {
    "firmwareId": 123,
    "version": "VERSION",
    "details": [{
      "module": "userbin",
      "version": 123,
      "file": {
        "size": 123,
        "digest": "DIGEST",
        "url": "http://server/path/image.bin"
      }
    }]
  }
}
```

The older Fresh Element Mini stock firmware's OTA-check callback selects
`result`, not the alternative `payload` wrapper. The callback requires a
details array and usable URL. `firmwareId`, the top-level version, and the
module version are distinct fields; the user1 callback does not compare them
before accepting an otherwise eligible offer.

The Fresh Element Mini stock firmware's OTA client parses `Content-Length` and
`Content-Range`, requests bounded byte ranges, writes the inactive physical
slot, compares an image CRC with a CRC read back from flash, reports
completion, changes the selected slot, and reboots. A controlled stock
user2-to-user1 downgrade and user1-to-user2 upgrade both completed. After each
reboot, the stock firmware reported the version stored in the newly selected
slot. The same OTA client subsequently installed the Kickstart V2 bridge and
completed the full migration to ESPHome.

## HTTP response compatibility

Stock user2 accepted Python's normal HTTP/1.0 response. Older user1 rejected
the response before its endpoint callback received a body and printed null
response diagnostics for OTA, state, server-info, and time requests.

Petkit's response used:

- HTTP/1.1;
- status `200` with an empty reason phrase;
- no `Server` header;
- `Access-Control-Allow-Origin: *`;
- headers and each short JSON body sent in one socket write.

Reproducing that framing made user1 process the same fixtures. The
compatibility server therefore uses it for every profile so both tested
firmware generations follow the same route handlers.

## Flash layout and images

The full flash contains two Espressif non-OS SDK V2 user-bin images:

| Slot | Flash offset | Safe capacity | Stock image length | ESP checksum | SDK CRC32 |
|---|---:|---:|---:|---:|---:|
| user1 | `0x001000` | `0x100000` | `0x09B974` | `0x85` | `0x6D192564` |
| user2 | `0x101000` | `0x0FA000` | `0x0A17D4` | `0x5C` | `0x03DC5920` |

Both images begin with V2 magic `EA 04` and contain an inner E9 image. Their
headers declare QIO, 40 MHz, and the 2 MiB `1024 KiB + 1024 KiB` size map. The
user2 capacity ends at `0x1FB000`, where RF-calibration and SDK parameter data
begin; treating the entire remainder of flash as user2 would overwrite that
data.

The [V2 image analyzer](../tools/analyze_stock_ota.py) validates and extracts
these images using layout values from [`profile.json`](profile.json). The
tested V2 bridge builder is part of the
[`wrobelda/esphome-kickstart`](https://github.com/wrobelda/esphome-kickstart)
fork rather than this server project; the generic changes are intended for
the canonical [ESPHome
Kickstart](https://github.com/libretiny-eu/esphome-kickstart) project.

The metadata `digest` is the four-byte SDK CRC32 stored after the padded E9
image, encoded as eight hexadecimal characters for the tested images. No
public-key signature field or separate firmware-signing key was identified.
That absence alone would not prove that every image accepted by the container
parser is bootable.

## Persistent failure counter

The user1 HTTP caller at VMA `0x40250841` reads the persisted configuration
field at offset `0x1C8` and skips its OTA handler when the value is at least
three. Download failure code increments the same field up to that limit, so a
power cycle does not restore OTA eligibility.

The Petkit mobile-app route `/6/feedermini/ota_reset` clears the counter through
the stock command path. The next state report then exposes `ota:0`. This counter is
different from the transient ESP8266 SDK upgrade flag, whose values are idle,
start, and finish; state-report `ota` does not report that transient flag.

The exact user2 HTTP handler remains unlocated. An earlier analysis incorrectly
identified VMA `0x40268634`; that address belongs to motor and door telemetry.
User2's upgrade-state getter is at `0x4020D900`, but a getter reference alone
does not identify the surrounding handler.

## Device command fields

The inbound MQTT command parser recognizes top-level `ota`; value zero clears
the failure counter and persists the change. It also recognizes `devreboot`
and enters the restart path for a value of at least one. No standalone device
HTTP reboot route was found, and the MQTT reboot command was not exercised
through a local broker.

## Remaining questions

- Locate and document the exact user2 HTTP OTA handler only if future firmware
  comparison requires it; the complete user2 update path is already verified
  dynamically.
- Determine whether other Petkit device families use the same digest encoding,
  failure threshold, response-framing sensitivity, and command fields.
- Treat every new flash layout, protected tail region, and stock hardware
  identifier as device evidence rather than inheriting this profile by name.
