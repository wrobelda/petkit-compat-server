# Project rules

- Do not push to any remote unless the user explicitly asks in the current
  conversation.
- Never commit packet captures, firmware images, runtime logs, WiFi
  credentials, Petkit identities, Aliyun credentials, or account sessions.
- Keep device-specific behavior in fixtures or profiles when possible. Do not
  generalize a protocol detail until it has been verified on another model.
- Keep the default server configuration inert: it must not offer firmware.
- Write atomic commits that can be reviewed independently.
- Read the [user workflow](README.md), [contributor guide](docs/CONTRIBUTING.md),
  [Petkit API reference](docs/PETKIT-API.md), and the selected device documentation
  before changing a profile or server behavior.
- Read [Disassembly and firmware analysis](docs/DISASSEMBLY.md) before analyzing a
  firmware image or writing an analysis helper. Reuse the existing parsers,
  device research, and tests before adding tooling.
