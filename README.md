# Install custom firmware on Petkit devices

This project helps update supported Petkit devices with custom firmware, such
as ESPHome, without opening the device or using a serial adapter.

The stock Petkit firmware normally sends its network requests to Petkit's
cloud. This project directs those requests to two tools running on your own
computer:

- `provision_petkit_device.py` is used while the device is in setup mode and
  exposes a temporary Wi-Fi network, also called a SoftAP. Normally, you would
  connect a phone to that network and use the Petkit mobile app. With this
  project, you connect your computer to the network and run
  `provision_petkit_device.py` instead of the Petkit mobile app. The script has
  two purposes:

  1. It sends the credentials for your regular Wi-Fi network to the device,
     just as the Petkit mobile app would.
  2. More importantly, it tells the device to contact the temporary
     `serve_petkit_api.py` server on your computer instead of Petkit's cloud.

  Once provisioning finishes, the device reboots, joins your regular Wi-Fi
  network, and connects to your computer.

- `serve_petkit_api.py` mimics the communication with Petkit's cloud. It lets
  the stock firmware perform its normal over-the-air update while downloading
  your custom firmware from your computer.

## Install a supported device

### 1. Select the exact device

Open the [supported-device list](devices/README.md), select the exact model,
and read its page. Copy these three values from that page:

- `PROFILE_PATH`;
- `FIXTURE_PATH`;
- `YOUR_COMPUTER_API_URL`.

Do not select a device only because its name or enclosure looks similar.

### 2. Start the update server

Run this command while the computer is connected to the regular Wi-Fi network
that the Petkit device will use:

```sh
python3 serve_petkit_api.py --host 0.0.0.0 --port 8080 \
  --profile PROFILE_PATH \
  --fixtures FIXTURE_PATH
```

Leave this terminal running. Make sure TCP port 8080 is allowed through the
computer's firewall. If possible, test the port from another device on the
regular Wi-Fi network:

```sh
nc -vz YOUR_COMPUTER_IP 8080
```

### 3. Put the Petkit device in setup mode

Follow the button or power sequence on the selected device page. A temporary
Wi-Fi network such as `PETKIT_FEEDER_HW2_17BG1234` should appear. Connect the
computer to that network. The computer will normally lose Internet access until
provisioning finishes.

### 4. Load the saved Wi-Fi credentials

Set the target network name once, then retrieve its saved password without
putting the password itself in shell history.

On Linux with NetworkManager:

```bash
export PETKIT_WIFI_SSID='<target Wi-Fi name>'
PETKIT_WIFI_CONNECTION="$(
  while IFS= read -r uuid; do
    if [ "$(nmcli --get-values 802-11-wireless.ssid connection show uuid "$uuid" 2>/dev/null)" = "$PETKIT_WIFI_SSID" ]; then
      printf '%s\n' "$uuid"
      break
    fi
  done < <(nmcli --get-values UUID connection show)
)"
test -n "$PETKIT_WIFI_CONNECTION" || {
  echo "No saved NetworkManager connection found for $PETKIT_WIFI_SSID" >&2
  false
}
export PETKIT_WIFI_PASSWORD="$(nmcli --show-secrets \
  --get-values 802-11-wireless-security.psk \
  connection show uuid "$PETKIT_WIFI_CONNECTION")"
test -n "$PETKIT_WIFI_PASSWORD" || {
  echo "The saved NetworkManager connection has no Wi-Fi password" >&2
  false
}
```

On macOS:

```sh
export PETKIT_WIFI_SSID='<target Wi-Fi name>'
export PETKIT_WIFI_PASSWORD="$(security find-generic-password \
  -D 'AirPort network password' -a "$PETKIT_WIFI_SSID" -gw)"
```

Both commands use the saved Wi-Fi network. NetworkManager may ask for
authorization, while macOS may ask for Keychain access.

### 5. Provision the Petkit device

In the same terminal where the two variables were set, run:

```sh
python3 provision_petkit_device.py \
  --profile PROFILE_PATH \
  --ssid "$PETKIT_WIFI_SSID" \
  --server 'YOUR_COMPUTER_API_URL' \
  --timezone '<UTC offset in hours>' \
  --locale '<IANA time zone>' \
  --send
```

The Petkit device will leave its temporary network and try to join the target
network. The computer's connection to the temporary network will then close.
Remove the password from the shell environment after the provisioning command
finishes:

```sh
unset PETKIT_WIFI_PASSWORD
```

### 6. Reconnect the computer and confirm the device

Connect the computer to the target Wi-Fi network again. Once the computer and
the Petkit device are on that network, the device can contact
`serve_petkit_api.py`; its requests should appear in the server terminal. If
the server remains silent, confirm that the device can reach this computer on
TCP port 8080 before changing any firmware.

### 7. Finish the device-specific installation

Return to the selected device page and follow its firmware instructions.

## Add support for another device

The installation instructions end above. Development instructions and protocol
references are in the [contributor guide](docs/CONTRIBUTING.md).
