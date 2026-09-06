#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "petkit_softap", ROOT / "petkit_compat" / "softap.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class SoftApProtocolTest(unittest.TestCase):
    def test_json_uses_big_endian_length_prefix(self) -> None:
        frame = MODULE.encode_json({"mode": 1})
        size = struct.unpack(">I", frame[:4])[0]
        self.assertEqual(size, len(frame) - 4)
        self.assertEqual(json.loads(frame[4:]), {"mode": 1})
        self.assertEqual(MODULE.decode_frame(frame), {"mode": 1})

    def test_rejects_truncated_and_trailing_data(self) -> None:
        frame = MODULE.encode_json({"mode": 1})
        with self.assertRaisesRegex(ValueError, "length mismatch"):
            MODULE.decode_frame(frame[:-1])
        with self.assertRaisesRegex(ValueError, "length mismatch"):
            MODULE.decode_frame(frame + b"x")

    def test_recursive_redaction_is_case_insensitive(self) -> None:
        safe = MODULE.redact(
            {
                "ssid": "example-network",
                "pwd": "wifi-password",
                "nested": {"deviceSecret": "device-secret"},
                "items": [{"TOKEN": "session-token"}],
            }
        )
        self.assertEqual(safe["ssid"], "example-network")
        self.assertEqual(safe["pwd"], "<redacted>")
        self.assertEqual(safe["nested"]["deviceSecret"], "<redacted>")
        self.assertEqual(safe["items"][0]["TOKEN"], "<redacted>")
        self.assertNotIn("wifi-password", repr(safe))

    def test_redaction_covers_common_credential_key_variants(self) -> None:
        safe = MODULE.redact(
            {
                "wifiPassword": "private-1",
                "api_key": "private-2",
                "access_token": "private-3",
                "username": "private-4",
                "status": "safe",
            }
        )
        self.assertEqual(safe["status"], "safe")
        self.assertNotIn("private", repr(safe))


if __name__ == "__main__":
    unittest.main()
