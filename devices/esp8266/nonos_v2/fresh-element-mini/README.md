# Petkit Fresh Element Mini

This profile provisions a stock Petkit Fresh Element Mini and reproduces the
Petkit HTTP API needed to start it on a controlled local network. Petkit calls
this device `Feedermini` in its API routes, while the Petkit Android app calls
it `D2`.

The verified workflow can:

- configure the feeder's Wi-Fi network and API server through its SoftAP;
- answer the stock firmware's startup requests with local fixtures;
- offer a validated ESP8266 non-OS SDK V2 user-bin image;
- serve the image with the byte-range behavior expected by the stock updater;
- record request metadata without logging credentials or device secrets.

The profile was tested with the ESP8266 Fresh Element Mini. Do not use its
flash layout or OTA constraints for another Petkit model without independent
verification.

## Files

- [`profile.json`](profile.json) defines HTTP routes, log-safe fields, and the
  SoftAP protocol.
- [`fixtures/safe-bootstrap.json`](fixtures/safe-bootstrap.json) is a synthetic
  startup fixture that offers no firmware update.
- [Stock OTA research](OTA-RESEARCH.md) documents the update protocol and image
  format.
- [Hardware](HARDWARE.md) documents the board, flash layout, and serial pads;
  the shared [V2 recovery guide](../RECOVERY.md) covers backup and restore.

Private fixtures, firmware images, packet captures, and logs belong in ignored
paths. Never replace the synthetic fixture values with live credentials in a
tracked file.

## Values for the installation workflow

Use the numbered workflow in the [main README](../../../../README.md) with:

| Placeholder | Value |
|---|---|
| `PROFILE_PATH` | `devices/esp8266/nonos_v2/fresh-element-mini/profile.json` |
| `YOUR_COMPUTER_API_URL` | `http://YOUR_COMPUTER_IP:8080/6/` |

The committed fixture lets the stock firmware start and contact the local
compatibility server, but it does not offer an update. Installing replacement
firmware also requires the image described under [Offer an OTA
image](#offer-an-ota-image). Its placeholder device and Aliyun values are not
usable for continued stock cloud operation.

To enter setup mode, hold the feeder's Wi-Fi/reset button for about five
seconds until it gives the long confirmation beep. Connect the computer to the
`PETKIT_FEEDER_...` access point, then run step 4 from the main workflow. The
target network must use 2.4 GHz Wi-Fi.

If the goal is to keep the stock firmware operating against the local server,
copy the synthetic fixture to the ignored `fixtures/local-device.json`, set
permissions to `0600`, and replace its placeholder signup and Aliyun fields
with values from the owner's private capture. This is not required for the
ESPHome migration.

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
the selected slot only after validation. The complete transition from Petkit's
paired non-OS slots to a normal ESPHome eboot layout is documented by
[`wrobelda/petkit-esphome`](https://github.com/wrobelda/petkit-esphome) and
[ESPHome Kickstart](https://github.com/libretiny-eu/esphome-kickstart); it is
not encoded in this device profile.

## Logging and failure behavior

Request logs contain the HTTP method, route, content type, body size, known
form-field names, and selected bounded operational fields. They omit header
values, query values, form values, fixture responses, and OTA contents.

Unknown API routes return HTTP 404. Malformed image routes and invalid images
are rejected at startup. The server never contacts Petkit or Aliyun during the
local provisioning and OTA workflow.
