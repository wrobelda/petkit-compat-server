#!/usr/bin/env python3
"""Create a Petkit OTA fixture from a validated ESP8266 V2 user-bin."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

from devices.esp8266.nonos_v2.image import load_v2_image


def positive_int(value: str) -> int:
    parsed = int(value, 0)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def make_fixture(
    image: bytes,
    *,
    firmware_id: int,
    version: str,
    module_version: int,
) -> dict[str, object]:
    digest = f"{struct.unpack_from('<I', image, len(image) - 4)[0]:08x}"
    empty_result = {"status": 200, "body": {"result": {}}}
    return {
        "/6/feedermini/dev_ota_check": {
            "status": 200,
            "body": {
                "result": {
                    "firmwareId": firmware_id,
                    "version": version,
                    "details": [
                        {
                            "module": "userbin",
                            "version": module_version,
                            "file": {
                                "size": len(image),
                                "digest": digest,
                                "url": "${OTA_IMAGE_URL}",
                            },
                        }
                    ],
                }
            },
        },
        "/6/feedermini/dev_ota_start": empty_result,
        "/6/feedermini/dev_ota_complete": empty_result,
        "/6/feedermini/dev_ota_heartbeat": empty_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--firmware-id", type=positive_int, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--module-version", type=positive_int, required=True)
    args = parser.parse_args()

    image = load_v2_image(args.image)
    fixture = make_fixture(
        image,
        firmware_id=args.firmware_id,
        version=args.version,
        module_version=args.module_version,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    digest = f"{struct.unpack_from('<I', image, len(image) - 4)[0]:08x}"
    print(
        json.dumps(
            {
                "output": str(args.output),
                "image_bytes": len(image),
                "digest": digest,
                "url": "${OTA_IMAGE_URL}",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
