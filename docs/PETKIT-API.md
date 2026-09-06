# Petkit API reference

This document records protocol behavior shared by the local compatibility
tools. A route is not assumed to work for every Petkit product;
device-specific routes and fields belong in that device's profile.

The current evidence comes from the Fresh Element Mini. The working assumption
is that other Petkit devices use the same API family, or a product-specific
subset and version of it, because the route structure separates the API
version from the device-family name. This document will be revised as
contributors validate other devices; until then, only the Fresh Element Mini
profile is confirmed.

## Device HTTP API

Stock device routes begin with an API version and a device-family name, such as
`/6/feedermini/dev_signup`. Requests use
`application/x-www-form-urlencoded`. Structured fields such as `state` and
`firmwareDetails` contain JSON encoded as one form value.

Observed requests carry:

- `X-Api-Version`, which identifies the device API revision;
- `X-Device`, whose value contains the device ID, device type, nonce,
  timestamp, and request signature;
- a device-family-specific form body.

The compatibility server does not validate the signature because it runs on a
network controlled by the device owner and returns configured local fixtures.
It never logs authentication-header values, form values, or query values.

Successful responses use a top-level `result` object. Stock callbacks can be
sensitive to wire framing in addition to JSON. The newer Fresh Element Mini
firmware accepted Python's ordinary HTTP/1.0 response, while the older Fresh
Element Mini firmware rejected every response before its endpoint callback saw
the body. Reproducing Petkit's
HTTP/1.1 status line with an empty reason phrase, omitting the `Server` header,
and sending each short response in one socket write made the older firmware
process the same fixtures. The server uses this compatible framing for every
profile.

## Transport selection

SoftAP provisioning writes the compatibility-server address into the device
configuration, so local installation does not need DNS or router interception.

## Device route families

The current [Fresh Element Mini
profile](../devices/esp8266/nonos_v2/fresh-element-mini/profile.json) defines these
route families. Other products may use another API-version prefix or
device-family segment.

| Route | Purpose and request fields |
|---|---|
| `dev_signup` | device configuration; chip ID, firmware, hardware, numeric ID, locale, MAC addresses, serial number, and timezone |
| `dev_iot_device_info` | Aliyun IoT identity, requested by serial number |
| `dev_state_report` | JSON device state; response includes report interval and server time |
| `dev_device_info` | additional device configuration |
| `dev_serverinfo` | service endpoint information |
| `dev_synctime` | server time |
| `dev_feed_get` | feeding schedule and related state |
| `poll/feedermini/heartbeat` | HTTP polling-session heartbeat |

Signup responses can contain device settings, notification preferences,
timezone and locale data, the device secret, and the associated user ID. IoT
device-info responses can contain the Aliyun product key, device name, device
secret, region, MQTT host, and instance identifier. These are live credentials
and must exist only in an ignored local fixture.

The Fresh Element Mini's stock ESP8266 firmware stores and evaluates feeding
schedules. Its feed-list data uses fields including `items`, `repeats`,
`nextTick`, `timestamp`, and `amount`; the Fresh Element Mini's motor-controller
MCU receives immediate dispense commands rather than a schedule table.

## OTA lifecycle

The device-driven OTA sequence uses four routes:

1. `dev_ota_check` reports the current hardware, firmware, module versions,
   force flag, and wait state.
2. `dev_ota_start` reports the accepted firmware ID before download.
3. `dev_ota_heartbeat` reports progress while the update is active.
4. `dev_ota_complete` reports `success` and optionally an error message.

An OTA offer uses this response shape:

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

`{"result":{}}` means that no update is available. The Fresh Element Mini's
stock OTA client downloads an accepted image with HTTP byte-range requests,
writes its inactive ESP8266 non-OS SDK slot, verifies the flashed image, reports
completion, changes the selected slot, and reboots. Image format and slot
behavior are profile-specific; an ESP32 Petkit device should not be assumed to
use this layout.

The Fresh Element Mini's stock firmware also keeps a persistent OTA-failure
counter. Three failed starts prevent another offer from reaching
`dev_ota_start`, even after a power cycle. This counter is separate from the
transient in-progress flag and from firmware version comparison. The Petkit
mobile-app `ota_reset` route described below clears the persistent counter.
Device-specific image validation and disassembly are documented in the [Fresh Element Mini OTA
research](../devices/esp8266/nonos_v2/fresh-element-mini/OTA-RESEARCH.md).

## SoftAP provisioning

The observed provisioning implementation exposes a TCP/JSON service while the
device's setup access point is active. Each message is a four-byte big-endian
length followed by a JSON object. Request keys, destination, and payload-field
names are device profile data.

The configuration payload supplies the target Wi-Fi credentials, hidden
network flag, device API server URL, timezone, and locale. After the commit
message, the feeder leaves its SoftAP, joins the target Wi-Fi network, and
contacts the configured server. Runtime credentials are redacted from the
provisioning helper's logs.

## Aliyun MQTT handoff

HTTP signup and IoT device-info responses configure a persistent outbound
Aliyun MQTT connection. The Fresh Element Mini uses topics derived from its
product key and device name, including update, get, and shadow paths. The Petkit app
normally sends a command to Petkit's cloud, which publishes it over this
existing connection; the feeder does not require an inbound LAN port.

The inbound command parser recognizes at least `ota`, where zero clears the
persistent OTA-failure counter, and `devreboot`, where a value of at least one
enters the restart path. These are MQTT command fields, not local HTTP routes.
The reboot path was identified statically but has not been exercised through a
local MQTT replacement.

## Petkit mobile-app API: reset OTA failures

The observed Petkit mobile-app route `POST /6/feedermini/ota_reset` accepts the
numeric Petkit device ID in the `id` form field. A successful request caused
the cloud command path to clear the Fresh Element Mini firmware's persistent
OTA failure counter. It did not reboot the device. Other device-family routes must be
confirmed before this helper is generalized beyond `feedermini`.

`petkit_app_ota_reset.py` implements this request. It is a dry run unless
`--send` is supplied. It accepts an existing `PETKIT_SESSION` or logs in using
`PETKIT_USERNAME` and `PETKIT_PASSWORD`; credentials and the temporary session
remain in memory and are not printed.

```sh
PETKIT_USERNAME='<account email>' PETKIT_PASSWORD='<account password>' \
  python3 tools/petkit_app_ota_reset.py --device-id DEVICE_ID --send
```

This helper contacts Petkit's live service. It is separate from the local
provisioning and compatibility-server workflow.
