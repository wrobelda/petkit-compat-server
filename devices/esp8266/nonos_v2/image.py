"""Parse and validate Espressif ESP8266 non-OS SDK V2 user-bin images."""

from __future__ import annotations

import binascii
import struct
from pathlib import Path


def sdk_crc32(data: bytes) -> int:
    crc = binascii.crc32(data) & 0xFFFFFFFF
    return crc ^ 0xFFFFFFFF if crc & 0x80000000 else crc + 1


def parse_v2_image(image: bytes, start: int = 0) -> dict[str, object]:
    magic, marker, mode, size_freq, entry = struct.unpack_from(
        "<BBBBI", image, start
    )
    if (magic, marker) != (0xEA, 4):
        raise ValueError(f"no ESP8266 V2 image at {start:#x}")

    cursor = start + 8
    irom_address, irom_size = struct.unpack_from("<II", image, cursor)
    cursor += 8 + irom_size
    normal_magic, count, mode2, size_freq2, entry2 = struct.unpack_from(
        "<BBBBI", image, cursor
    )
    cursor += 8
    if normal_magic != 0xE9 or (mode, size_freq, entry) != (
        mode2,
        size_freq2,
        entry2,
    ):
        raise ValueError(f"invalid second image header at {cursor - 8:#x}")

    checksum = 0xEF
    segments: list[dict[str, int]] = []
    for _ in range(count):
        address, size = struct.unpack_from("<II", image, cursor)
        cursor += 8
        data = image[cursor : cursor + size]
        if len(data) != size:
            raise ValueError("truncated segment")
        for byte in data:
            checksum ^= byte
        segments.append({"address": address, "size": size})
        cursor += size

    checksum_offset = cursor | 0x0F
    stored_checksum = image[checksum_offset]
    crc_offset = checksum_offset + 1
    stored_crc = struct.unpack_from("<I", image, crc_offset)[0]
    end = crc_offset + 4
    return {
        "offset": start,
        "length": end - start,
        "entrypoint": entry,
        "irom_address": irom_address,
        "irom_size": irom_size,
        "segments": segments,
        "checksum": stored_checksum,
        "checksum_valid": checksum == stored_checksum,
        "crc32": stored_crc,
        "crc32_valid": sdk_crc32(image[start:crc_offset]) == stored_crc,
    }


def load_v2_image(path: Path) -> bytes:
    image = path.read_bytes()
    try:
        result = parse_v2_image(image)
    except (IndexError, struct.error) as error:
        raise ValueError("OTA image is truncated") from error
    if not result["checksum_valid"]:
        raise ValueError("OTA image segment checksum is invalid")
    if not result["crc32_valid"]:
        raise ValueError("OTA image SDK CRC32 is invalid")
    if result["length"] != len(image):
        raise ValueError("OTA image has trailing or truncated data")
    return image


def v2_ota_digest(image: bytes) -> str:
    result = parse_v2_image(image)
    return f"{result['crc32']:08x}"
