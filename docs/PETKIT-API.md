# Petkit API reference

This document records protocol behavior shared by the local compatibility
tools. A route is not assumed to work for every Petkit product;
device-specific routes and fields belong in that device's profile.

The evidence comes from the Fresh Element Mini. Other Petkit devices may use
the same API family or a versioned subset, but their behavior must be verified
before reusing a profile. The route structure separates the API version from
the device-family name.

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
Logs omit authentication headers and query values. Only explicitly allowed,
bounded operational form fields may appear; credentials remain redacted.

Successful responses use a top-level `result` object. HTTP framing also matters:
older Fresh Element Mini firmware rejects ordinary Python HTTP/1.0 responses
before the endpoint callback receives the body, while newer firmware accepts
them.

The compatibility server uses the following framing for all profiles to support
both firmware generations:

- HTTP/1.1 with an empty reason phrase in the status line;
- no `Server` header;
- each short response sent in one socket write.

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

For example, the Fresh Element Mini's feed-list data contains `items`,
`repeats`, `nextTick`, `timestamp`, and `amount`. Its [feeder firmware
documentation](https://github.com/wrobelda/petkit-element-mini-esphome/tree/main/esphome#feeding-schedule)
explains which processor stores and evaluates the schedule.

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

### OTA eligibility and failure state

The Fresh Element Mini has two separate OTA state values:

| State | Lifetime and effect |
|---|---|
| Failure counter | Persists across power cycles; a value of three blocks the path to `dev_ota_start` |
| In-progress flag | Transient state that distinguishes idle, started, and finished updates |

The state-report `ota` field represents the failure counter, not the
in-progress flag. The Petkit mobile-app `ota_reset` route described below clears
the counter. Device-specific image checks and handler analysis are in the
[Fresh Element Mini OTA research][mini-ota].

## SoftAP provisioning

The observed provisioning implementation exposes a TCP/JSON service while the
device's setup access point is active. Each message is a four-byte big-endian
length followed by a JSON object. Request keys, destination, and payload-field
names are device profile data.

The configuration payload supplies the target Wi-Fi credentials, hidden
network flag, device API server URL, timezone, and locale. After the commit
message, the device leaves its SoftAP, joins the target Wi-Fi network, and
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

The Petkit mobile-app route `POST /6/feedermini/ota_reset` accepts the numeric
Petkit device ID in the `deviceId` form field. The cloud command clears the
Fresh Element Mini's persistent OTA-failure counter without rebooting it.
Other device-family routes require verification before this helper can be
generalized beyond `feedermini`.

[`tools/petkit_app_ota_reset.py`](../tools/petkit_app_ota_reset.py) implements
this request. It is a dry run unless
`--send` is supplied. It accepts an existing `PETKIT_SESSION` or logs in using
`PETKIT_USERNAME` and `PETKIT_PASSWORD`; credentials and the temporary session
remain in memory and are not printed.

```bash
export PETKIT_REGION='<account region>'
read -r -p 'Petkit account: ' PETKIT_USERNAME
read -r -s -p 'Petkit password: ' PETKIT_PASSWORD
printf '\n'
export PETKIT_USERNAME PETKIT_PASSWORD
python3 tools/petkit_app_ota_reset.py --device-id DEVICE_ID --send
unset PETKIT_USERNAME PETKIT_PASSWORD
```

This helper contacts Petkit's live service. It is separate from the local
provisioning and compatibility-server workflow.

[mini-ota]: ../devices/esp8266/nonos_v2/fresh-element-mini/OTA-RESEARCH.md
