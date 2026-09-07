#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "petkit_app_ota_reset", ROOT / "tools" / "petkit_app_ota_reset.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class AppOtaResetTest(unittest.TestCase):
    def test_login_form_matches_reversed_android_convention(self) -> None:
        with patch.dict(os.environ, {"PETKIT_TIMEZONE": "UTC"}, clear=True):
            form = MODULE.login_form("owner@example.test", "private-password", "pl")
        self.assertEqual(form["username"], "owner@example.test")
        self.assertEqual(
            form["password"], hashlib.md5(b"private-password").hexdigest()
        )
        self.assertNotIn("private-password", repr(form))
        self.assertEqual(form["region"], "pl")
        self.assertIn("'timezoneId': 'UTC'", form["client"])

    def test_existing_session_avoids_login(self) -> None:
        with patch.dict(os.environ, {"PETKIT_SESSION": "private-session"}, clear=True):
            with patch.object(MODULE, "post_json") as post:
                self.assertEqual(MODULE.obtain_session(MODULE.DEFAULT_URL), "private-session")
        post.assert_not_called()

    def test_login_extracts_session_without_persisting_it(self) -> None:
        response = {"result": {"session": {"id": "temporary-session"}}}
        environment = {
            "PETKIT_USERNAME": "owner@example.test",
            "PETKIT_PASSWORD": "private-password",
            "PETKIT_TIMEZONE": "UTC",
            "PETKIT_REGION": "us",
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch.object(MODULE, "post_json", return_value=(200, response)) as post:
                session = MODULE.obtain_session(MODULE.DEFAULT_URL)
        self.assertEqual(session, "temporary-session")
        self.assertEqual(post.call_args.args[0], "https://api.eu-pet.com/6/user/login")
        self.assertNotIn("private-password", repr(post.call_args))

    def test_send_uses_device_id_field(self) -> None:
        response = {"result": {}}
        with patch.dict(os.environ, {"PETKIT_SESSION": "private-session"}, clear=True):
            with patch.object(MODULE, "post_json", return_value=(200, response)) as post:
                with patch.object(
                    __import__("sys"),
                    "argv",
                    ["petkit_app_ota_reset.py", "--device-id", "123", "--send"],
                ):
                    with patch("sys.stdout", new_callable=io.StringIO):
                        self.assertEqual(MODULE.main(), 0)
        self.assertEqual(post.call_args.args[1], {"deviceId": "123"})


if __name__ == "__main__":
    unittest.main()
