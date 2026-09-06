"""Create a small valid ESP8266 non-OS V2 image for host-side tests."""

from __future__ import annotations

import struct

from devices.esp8266.nonos_v2.image import sdk_crc32


def make_v2_image(payload: bytes = b"test image payload") -> bytes:
    entrypoint = 0x40100004
    image = bytearray(struct.pack("<BBBBI", 0xEA, 4, 0, 0x50, entrypoint))
    image.extend(struct.pack("<II", 0, 0))
    image.extend(struct.pack("<BBBBI", 0xE9, 1, 0, 0x50, entrypoint))
    image.extend(struct.pack("<II", 0x3FFE8000, len(payload)))
    image.extend(payload)

    checksum = 0xEF
    for byte in payload:
        checksum ^= byte
    checksum_offset = len(image) | 0x0F
    image.extend(bytes(checksum_offset - len(image)))
    image.append(checksum)
    image.extend(struct.pack("<I", sdk_crc32(image)))
    return bytes(image)
