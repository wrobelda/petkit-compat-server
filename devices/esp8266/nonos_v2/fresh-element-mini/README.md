# Petkit Fresh Element Mini

This profile provisions a stock Petkit Fresh Element Mini and reproduces the
Petkit HTTP API needed to start it on a controlled local network. Petkit calls
this device `Feedermini` in its API routes, while the Petkit Android app calls
it `D2`.

With this profile, the tools can:

- configure the feeder's Wi-Fi network and API server through its SoftAP;
- answer the stock firmware's startup requests with local fixtures;
- offer a validated ESP8266 non-OS SDK V2 user-bin image;
- serve the image with the byte-range behavior expected by the stock updater;
- record request metadata without logging credentials or device secrets.

The profile targets the ESP8266 Fresh Element Mini P530. Do not use its
flash layout or OTA constraints for another Petkit model without independent
verification.

## Files

- [`profile.json`](profile.json) defines HTTP routes, log-safe fields, and the
  SoftAP protocol.
- [`fixtures.json`](fixtures.json) defines the synthetic responses used by this
  device profile when no OTA image is supplied.
- [Stock OTA research](OTA-RESEARCH.md) documents the update protocol and image
  format.
- [Hardware](HARDWARE.md) documents the board and serial pads; the shared
  [V2 hardware and recovery guide](../HARDWARE.md) covers the flash layout,
  backup, and restore.

Private fixtures, firmware images, packet captures, and logs belong in ignored
paths. Never replace the synthetic fixture values with live credentials in a
tracked file.

## Values for the installation workflow

Use these values in the [main installation workflow](../../../../README.md#install-a-supported-device):

| Setting | Value |
|---|---|
| `PROFILE_PATH` | `devices/esp8266/nonos_v2/fresh-element-mini/profile.json` |
| Target network | 2.4 GHz Wi-Fi |
| Setup mode | Hold the Wi-Fi/reset button for about five seconds, until the long confirmation beep |
| Setup network | `PETKIT_FEEDER_...` |

The profile supplies the `/6/` API path, so pass only the computer's address
through `--server-host`.

The committed fixture lets the stock firmware start and contact the local
compatibility server, but it does not offer an update. Installing replacement
firmware also requires the image described under [Offer an OTA
image](#offer-an-ota-image). Its placeholder device and Aliyun values are not
usable for continued stock cloud operation.

## Offer an OTA image

Read [HARDWARE.md](HARDWARE.md) before changing firmware. The
server accepts only complete ESP8266 V2 user-bin images with a valid segment
checksum, appended SDK CRC32, and no trailing data.

The profile selects its synthetic base fixture and the stable metadata fields
expected by this stock firmware. When `--ota-image` is present, the server
validates the image and calculates its size, digest, and reachable download URL
at startup. Validate the complete update configuration without opening a
socket:

```sh
python3 serve_petkit_api.py \
  --host 0.0.0.0 \
  --port 8080 \
  --profile devices/esp8266/nonos_v2/fresh-element-mini/profile.json \
  --ota-image IMAGE.bin \
  --check
```

Then run the same command without `--check` and reboot the feeder. After the
feeder reports a successful OTA completion, that server process stops offering
the image and returns an empty OTA result on later checks.

The stock firmware downloads an OTA into its inactive user-bin slot and changes
the selected slot only after validation. Do not offer a normal ESPHome image
directly: the stock bootloader expects a V2 user-bin and cannot boot ESPHome's
eboot V1 layout. Install the device-specific ESPHome Kickstart transition image
first; that image allows the final ESPHome factory image to be installed with
a safe layout migration. Follow the complete procedure in
[`wrobelda/petkit-element-mini-esphome`](https://github.com/wrobelda/petkit-element-mini-esphome#installation).
The generic migration implementation lives in the
[`wrobelda/esphome-kickstart`](https://github.com/wrobelda/esphome-kickstart)
fork of [ESPHome Kickstart](https://github.com/libretiny-eu/esphome-kickstart).
This profile handles the stock API and OTA offer; Kickstart handles the
non-OS V2 to eboot V1 layout transition.

## Using private stock-service fixtures

ESPHome migration does not require live signup or Aliyun credentials. To
configure the stock firmware with those identities instead, copy the synthetic
fixture to the ignored `local/fixtures/device.json`, set permissions to `0600`,
and replace its placeholder signup and Aliyun fields with values from the
owner's private capture. Keep the modified fixture outside Git.

## Logging and failure behavior

Request logs contain the HTTP method, route, content type, body size, known
form-field names, and selected bounded operational fields. They omit header
values, query values, form values, fixture responses, and OTA contents.

Unknown API routes return HTTP 404. Malformed image routes and invalid images
are rejected at startup. The server never contacts Petkit or Aliyun during the
local provisioning and OTA workflow.
