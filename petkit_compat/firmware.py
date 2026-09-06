"""Select an OTA image validator from the device profile's firmware format."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from devices.esp8266.nonos_v2.image import load_v2_image, v2_ota_digest


ImageLoader = Callable[[Path], bytes]
ImageDigester = Callable[[bytes], str]
IMAGE_LOADERS: dict[str, ImageLoader] = {
    "esp8266-nonos-v2": load_v2_image,
}
IMAGE_DIGESTERS: dict[str, ImageDigester] = {
    "esp8266-nonos-v2": v2_ota_digest,
}


def firmware_format(profile: dict[str, Any]) -> str:
    try:
        value = profile["firmware"]["format"]
    except (KeyError, TypeError) as error:
        raise ValueError("profile does not define a firmware format") from error
    if not isinstance(value, str) or not value:
        raise ValueError("profile does not define a firmware format")
    return value


def load_ota_image(path: Path, profile: dict[str, Any]) -> bytes:
    format_name = firmware_format(profile)
    loader = IMAGE_LOADERS.get(format_name)
    if loader is None:
        raise ValueError(f"unsupported firmware format: {format_name!r}")
    image = loader(path)
    slot_capacity = min(slot["size"] for slot in profile["firmware"]["slots"])
    if len(image) > slot_capacity:
        raise ValueError(
            f"OTA image is {len(image)} bytes; smallest configured slot is "
            f"{slot_capacity} bytes"
        )
    return image


def ota_image_digest(image: bytes, profile: dict[str, Any]) -> str:
    format_name = firmware_format(profile)
    digester = IMAGE_DIGESTERS.get(format_name)
    if digester is None:
        raise ValueError(f"unsupported firmware format: {format_name!r}")
    return digester(image)
