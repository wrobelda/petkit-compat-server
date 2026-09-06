# Fresh Element Mini hardware

## Architecture

The feeder contains two processors:

- an ESP8266 handles Wi-Fi, Petkit API traffic, schedules, and OTA;
- an ISD91230 Cortex-M0 controls the motor, outlet, indicators, beeper, and
  sensors.

The processors communicate over ESP8266 UART0 at 115200 8N1. Replacing the
ESP8266 firmware does not replace the M0 firmware.

## Stock firmware

The stock ESP8266 firmware is built with Espressif's non-OS SDK. Petkit
identifies the device family as `Feedermini` in HTTP routes, while the Petkit
Android app identifies it as `D2`. The stock ESP8266 firmware owns Wi-Fi
provisioning, cloud communication, feeding schedules, and the paired-slot OTA
client. The stock ESP8266 firmware delegates physical feeding and sensing to
the M0 over UART0.

The M0 firmware remains installed independently of either ESP8266 user-bin
slot. The M0 serial protocol and firmware analysis belong to
[`wrobelda/petkit-esphome`](https://github.com/wrobelda/petkit-esphome), because
the compatibility server only reproduces the stock network and update services.

## ESP8266 flash layout

The ESP8266 has 2 MiB of flash and uses Espressif's paired non-OS SDK V2 OTA
layout:

| Region | Start | Safe extent |
|---|---:|---:|
| Bootloader | `0x000000` | to `0x001000` |
| user1 application | `0x001000` | `0x100000` bytes |
| user2 application | `0x101000` | `0x0FA000` bytes |
| RF calibration and SDK parameters | `0x1FB000` | to end of flash |

The user2 limit stops before the RF-calibration sector at `0x1FB000`.

## ESP8266 connections

| GPIO | Board connection |
|---:|---|
| 0 | Wi-Fi/reset button and ESP8266 boot strap |
| 1 | UART0 TX to M0; board TX0 pad |
| 2 | UART1 TX diagnostics; board TX1 pad |
| 3 | UART0 RX from M0; board RX0 pad |
| 5 / 14 | I2C to the battery-backed PCF8563 RTC |
| 13 | Manual-feed button |
| 15 | Active-low M0 reset and ESP8266 boot strap |
| 16 | Deep-sleep wake |

## Serial pads and boot mode

Use a 3.3 V logic-level serial adapter on the ESP8266 UART0 header:

- adapter RX to TX0/GPIO1;
- adapter TX to RX0/GPIO3;
- adapter GND to feeder GND;
- adapter VCC disconnected, while the feeder uses its normal power supply.

Hold the feeder's Wi-Fi button while applying power, wait one or two seconds,
then release it. The button pulls GPIO0 low during reset and selects the
ESP8266 ROM loader. Confirm the connection before reading or writing flash:

```sh
esptool --chip esp8266 --port PORT chip-id
```

This procedure was verified on a Fresh Element Mini: esptool loaded its stub
and completed a slot write. UART0 is also the link between the ESP8266 and the
motor-controller MCU. Disconnect the adapter's TX and RX leads after flashing,
because leaving the adapter attached can disrupt that link and cause the feeder
to reset.

For receive-only stock diagnostics, connect adapter RX and GND to the board pads
labelled TX1 and GND. The ESP8266 boot ROM and second-stage bootloader use
74880 baud, while the stock ESP8266 firmware changes its diagnostic output to
115200 baud after startup. Reopen the terminal at 115200 after the bootloader
messages if application output is required. An unpowered continuity test
confirmed that TX1 connects only to GPIO2/UART1 TX. TX0 connects only to
GPIO1/UART0 TX, RX0 connects only to GPIO3/UART0 RX, and there is no RX1 pad.

The board's RST through-hole is the ESP8266 reset signal. The Wi-Fi/reset
button is also connected to GPIO0, so holding it while applying power selects
the ROM loader. The adapter does not need to power the feeder. Pin 6 and the
3V3 through-hole were measured at 3.3 V, but normal feeder power was used for
all verified reads and writes.

## Backup and recovery

Follow the shared [ESP8266 non-OS V2 backup and recovery
procedure](../RECOVERY.md). Use this device's `profile.json` for its
2 MiB
flash size and slot boundaries. The complete procedure, a user1 slot restore,
and flash verification were exercised on the feeder.
