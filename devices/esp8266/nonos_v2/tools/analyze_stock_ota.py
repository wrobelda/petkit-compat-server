#!/usr/bin/env python3
"""Locate and verify ESP8266 non-OS V2 user-bin images in a flash dump."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from devices.esp8266.nonos_v2.image import parse_v2_image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("flash", type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--extract-dir", type=Path)
    args = parser.parse_args()
    with args.profile.open(encoding="utf-8") as handle:
        profile = json.load(handle)
    try:
        firmware = profile["firmware"]
        if firmware["format"] != "esp8266-nonos-v2":
            raise ValueError("profile does not describe ESP8266 non-OS V2 firmware")
        slots = firmware["slots"]
    except (KeyError, TypeError) as error:
        raise ValueError("profile is missing ESP8266 firmware layout settings") from error

    flash = args.flash.read_bytes()
    if len(flash) != firmware["flash_size"]:
        raise ValueError(
            f"flash dump is {len(flash)} bytes; profile requires {firmware['flash_size']}"
        )
    results = []
    for slot in slots:
        result = parse_v2_image(flash, slot["offset"])
        if result["length"] > slot["size"]:
            raise ValueError(f"{slot['name']} image exceeds its configured slot")
        result["name"] = slot["name"]
        results.append(result)
    print(json.dumps(results, indent=2))

    if args.extract_dir:
        args.extract_dir.mkdir(parents=True, exist_ok=True)
        for result in results:
            if not result["checksum_valid"] or not result["crc32_valid"]:
                raise ValueError(f"refusing to extract invalid slot {result['name']}")
            start = int(result["offset"])
            end = start + int(result["length"])
            (args.extract_dir / f"stock-{result['name']}.bin").write_bytes(
                flash[start:end]
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
