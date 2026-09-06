# Remaining work

- Add a device profile only after its request schema, SoftAP behavior, OTA
  format, flash layout, and protected regions have been independently verified.
- Review unsupported Fresh Element Mini endpoints and add fixtures only when a
  cold-boot or installation trace proves they are required.
- Replace optional private-flash test dependencies with generated format-valid
  images where the test does not require bytes from stock firmware.
