"""Load and validate a Petkit device protocol profile."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_profile(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        profile = json.load(handle)
    try:
        http = profile["http"]
        http["ota_check_route"]
        http["ota_complete_route"]
        http["state_report_route"]
        safe_fields = http["safe_form_fields"]
        safe_state_fields = http["safe_state_fields"]
        softap = profile["softap"]
        keys = softap["keys"]
        payload_fields = softap["payload_fields"]
        status_errors = softap["status_errors"]
        firmware = profile["firmware"]
        firmware_format = firmware["format"]
        flash_size = firmware["flash_size"]
        slots = firmware["slots"]
    except (KeyError, TypeError) as error:
        raise ValueError("profile is missing required HTTP or SoftAP settings") from error
    if not isinstance(profile.get("name"), str) or not profile["name"]:
        raise ValueError("profile name must be a non-empty string")
    routes = [value for key, value in http.items() if key.endswith("_route")]
    if not routes or not all(
        isinstance(route, str) and route.startswith("/") and not route.startswith("//")
        for route in routes
    ):
        raise ValueError("profile routes must be absolute paths")
    if len(routes) != len(set(routes)):
        raise ValueError("profile routes must be unique")
    if not isinstance(safe_fields, list) or not all(isinstance(item, str) for item in safe_fields):
        raise ValueError("safe_form_fields must be a list of strings")
    if not isinstance(safe_state_fields, list) or not all(
        isinstance(item, str) for item in safe_state_fields
    ):
        raise ValueError("safe_state_fields must be a list of strings")
    if not isinstance(firmware_format, str) or not firmware_format:
        raise ValueError("firmware format must be a non-empty string")
    if not isinstance(flash_size, int) or isinstance(flash_size, bool) or flash_size <= 0:
        raise ValueError("firmware flash_size must be a positive integer")
    if not isinstance(slots, list) or not slots:
        raise ValueError("firmware slots must be a non-empty list")
    ranges = []
    for slot in slots:
        if not isinstance(slot, dict):
            raise ValueError("each firmware slot must be an object")
        name, offset, size = slot.get("name"), slot.get("offset"), slot.get("size")
        if not isinstance(name, str) or not name:
            raise ValueError("firmware slot name must be a non-empty string")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("firmware slot offset must be a non-negative integer")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ValueError("firmware slot size must be a positive integer")
        if offset + size > flash_size:
            raise ValueError("firmware slot exceeds flash_size")
        ranges.append((offset, offset + size))
    ranges.sort()
    if any(current[0] < previous[1] for previous, current in zip(ranges, ranges[1:])):
        raise ValueError("firmware slots overlap")
    if not isinstance(softap.get("host"), str) or not softap["host"]:
        raise ValueError("SoftAP host must be a non-empty string")
    if not isinstance(softap.get("port"), int) or isinstance(softap["port"], bool) or not 1 <= softap["port"] <= 65535:
        raise ValueError("SoftAP port must be between 1 and 65535")
    required_keys = {"hello", "status", "configure", "commit", "heartbeat"}
    if not isinstance(keys, dict) or set(keys) != required_keys or not all(
        isinstance(value, int) and not isinstance(value, bool) for value in keys.values()
    ):
        raise ValueError("SoftAP keys must define integer protocol keys")
    required_fields = {"ssid", "password", "hidden", "server", "timezone", "locale"}
    if not isinstance(payload_fields, dict) or set(payload_fields) != required_fields or not all(
        isinstance(value, str) and value for value in payload_fields.values()
    ):
        raise ValueError("SoftAP payload_fields are invalid")
    if not isinstance(status_errors, dict) or not all(
        isinstance(key, str) and key.isdecimal() and isinstance(value, str) and value
        for key, value in status_errors.items()
    ):
        raise ValueError("SoftAP status_errors must map numeric strings to messages")
    return profile
