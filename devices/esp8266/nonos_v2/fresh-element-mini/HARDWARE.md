# Fresh Element Mini hardware

## Architecture

The feeder contains two processors:

- an ESP8266 handles Wi-Fi, Petkit API traffic, schedules, and OTA;
- a Nuvoton ISD91230 Cortex-M0 controls the motor, outlet, indicators, beeper, and
  sensors.

The processors communicate over ESP8266 UART0 at 115200 8N1. Replacing the
ESP8266 firmware leaves the ISD91230 motor-controller firmware installed.

## Stock firmware

The stock ESP8266 firmware uses Espressif's non-OS SDK. Petkit identifies the
device family as `Feedermini` in HTTP routes and `D2` in the Android app.

ESP8266 OTA changes only the Wi-Fi processor's firmware. The ISD91230
motor-controller firmware is independent of both ESP8266 application slots;
its [serial protocol and firmware analysis](https://github.com/wrobelda/petkit-element-mini-esphome/tree/main/esphome)
are documented in the feeder firmware project.

## ESP8266 flash layout

The ESP8266 has 2 MiB of flash and uses Espressif's paired non-OS SDK V2 OTA
layout. These boundaries are also encoded in [`profile.json`](profile.json):

| Region | Start | Safe extent |
|---|---:|---:|
| Bootloader | `0x000000` | to `0x001000` |
| user1 application | `0x001000` | `0x100000` bytes |
| user2 application | `0x101000` | `0x0FA000` bytes |
| PHY data, RF calibration, and SDK parameters | `0x1FB000` | to end of flash |

The user2 limit stops before PHY data at `0x1FB000`; the following sector at
`0x1FC000` contains RC-calibration data.

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

UART0 is also the link between the ESP8266 and the ISD91230 motor controller.
Disconnect the adapter's TX and RX leads after flashing,
because leaving the adapter attached can disrupt that link and cause the feeder
to reset.

GPIO15 must remain low during ESP8266 reset because it is a required boot
strap, as well as the active-low ISD91230 reset line. The board's RST
through-hole is the ESP8266 reset signal.

### Receive-only diagnostics

For receive-only stock diagnostics, connect adapter RX and GND to the board pads
labelled TX1 and GND. TX1 connects to GPIO2/UART1 TX and has no receive partner;
there is no RX1 pad.

| Output | Baud rate |
|---|---|
| ESP8266 boot ROM and second-stage bootloader | 74880 |
| Stock ESP8266 application diagnostics | 115200 |

Switch the terminal to 115200 baud after the bootloader messages to read the
stock application output.

## Backup and recovery

Follow the shared [ESP8266 non-OS V2 hardware, backup, and recovery
guide](../HARDWARE.md). Use this device's `profile.json` for its 2 MiB flash
size and slot boundaries.
