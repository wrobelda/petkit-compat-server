#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location(
    "provision_petkit_device", ROOT / "provision_petkit_device.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class SoftApProvisionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = MODULE.load_profile(
            ROOT
            / "devices"
            / "esp8266"
            / "nonos_v2"
            / "fresh-element-mini"
            / "profile.json"
        )

    def test_payload_matches_d2_app_schema(self) -> None:
        payload = MODULE.provisioning_payload(
            "test-network", "private-password", "http://192.0.2.1:8080/6/",
            "2.0", "Europe/Warsaw", self.profile
        )
        self.assertEqual(
            payload,
            {
                "ssid": "test-network",
                "pwd": "private-password",
                "hide": 1,
                "server": "http://192.0.2.1:8080/6/",
                "timezone": "2.0",
                "locale": "Europe/Warsaw",
            },
        )

    def test_socket_message_uses_big_endian_frame(self) -> None:
        left, right = socket.socketpair()
        try:
            MODULE.send_message(left, {"key": 151, "payload": {"ssid": "safe"}})
            self.assertEqual(
                MODULE.recv_message(right),
                {"key": 151, "payload": {"ssid": "safe"}},
            )
        finally:
            left.close()
            right.close()

    def test_log_redacts_wifi_password(self) -> None:
        output = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = output
            MODULE.log_event("test", payload={"ssid": "safe", "pwd": "private"})
        finally:
            sys.stdout = old_stdout
        parsed = json.loads(output.getvalue())
        self.assertEqual(parsed["payload"]["ssid"], "safe")
        self.assertEqual(parsed["payload"]["pwd"], "<redacted>")
        self.assertNotIn("private", output.getvalue())

    def test_server_requires_api_version_path(self) -> None:
        self.assertEqual(
            MODULE.validate_server("http://192.0.2.1:8080/6/", "/6/"),
            "http://192.0.2.1:8080/6/",
        )
        with self.assertRaises(Exception):
            MODULE.validate_server("http://192.0.2.1:8080/", "/6/")

    def test_server_url_is_built_from_host_and_profile_path(self) -> None:
        self.assertEqual(
            MODULE.server_from_host("192.0.2.1", 8080, "/6/"),
            "http://192.0.2.1:8080/6/",
        )
        self.assertEqual(
            MODULE.server_from_host("2001:db8::1", 8080, "/6/"),
            "http://[2001:db8::1]:8080/6/",
        )

    def test_wait_uses_profiled_heartbeat_key(self) -> None:
        class FakeSocket:
            def __init__(self, received: bytes) -> None:
                self.received = bytearray(received)
                self.sent = bytearray()

            def recv(self, size: int) -> bytes:
                result = bytes(self.received[:size])
                del self.received[:size]
                return result

            def sendall(self, data: bytes) -> None:
                self.sent.extend(data)

        sock = FakeSocket(
            MODULE.encode_json({"key": 42}) + MODULE.encode_json({"key": 7})
        )
        self.assertEqual(MODULE.wait_for_key(sock, 7, 42), {"key": 7})
        self.assertEqual(MODULE.decode_frame(bytes(sock.sent)), {"key": 42})

    def test_provision_reports_confirmed_commit(self) -> None:
        connection = mock.MagicMock()
        replies = [
            {"key": 1},
            {"key": 2, "payload": {"status": 0}},
            {"key": 151},
            {"key": 153},
        ]
        with (
            mock.patch.object(MODULE.socket, "create_connection") as connect,
            mock.patch.object(MODULE, "wait_for_key", side_effect=replies),
        ):
            connect.return_value.__enter__.return_value = connection
            outcome = MODULE.provision(
                "192.0.2.1", 8001, {}, 1.0, self.profile["softap"]
            )

        self.assertIs(outcome, MODULE.ProvisioningOutcome.CONFIRMED)

    def test_provision_reports_timeout_after_commit_as_indeterminate(self) -> None:
        connection = mock.MagicMock()
        replies = [
            {"key": 1},
            {"key": 2, "payload": {"status": 0}},
            {"key": 151},
            socket.timeout("SoftAP disappeared"),
        ]
        with (
            mock.patch.object(MODULE.socket, "create_connection") as connect,
            mock.patch.object(MODULE, "wait_for_key", side_effect=replies),
        ):
            connect.return_value.__enter__.return_value = connection
            outcome = MODULE.provision(
                "192.0.2.1", 8001, {}, 1.0, self.profile["softap"]
            )

        self.assertIs(
            outcome, MODULE.ProvisioningOutcome.COMMIT_OUTCOME_UNKNOWN
        )

    def test_provision_preserves_failure_before_commit(self) -> None:
        connection = mock.MagicMock()
        with (
            mock.patch.object(MODULE.socket, "create_connection") as connect,
            mock.patch.object(
                MODULE, "wait_for_key", side_effect=socket.timeout("no hello")
            ),
        ):
            connect.return_value.__enter__.return_value = connection
            with self.assertRaises(socket.timeout):
                MODULE.provision(
                    "192.0.2.1", 8001, {}, 1.0, self.profile["softap"]
                )


if __name__ == "__main__":
    unittest.main()
