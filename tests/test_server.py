#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import logging
import socket
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.v2_image import make_v2_image

FLASH = ROOT.parent / "petkit-serial-bus" / "flash dumps" / "petkitesp8266flash.bin"
SPEC = importlib.util.spec_from_file_location(
    "serve_petkit_api", ROOT / "serve_petkit_api.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fixtures = MODULE.load_fixtures(
            ROOT
            / "devices"
            / "esp8266"
            / "nonos_v2"
            / "fresh-element-mini"
            / "fixtures.json"
        )
        cls.profile = MODULE.load_profile(
            ROOT
            / "devices"
            / "esp8266"
            / "nonos_v2"
            / "fresh-element-mini"
            / "profile.json"
        )
        ota_image = make_v2_image()
        cls.ota_image = ota_image
        cls.server = MODULE.make_server(
            "127.0.0.1", 0, fixtures, cls.profile, ota_image
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.requests = json.loads((ROOT / "tests" / "requests.json").read_text())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def post(self, path: str, body: str, x_device: str = "sign=TOP_SECRET_SIGNATURE"):
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        conn.request("POST", path, body, {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Device": x_device,
        })
        response = conn.getresponse()
        payload = json.loads(response.read())
        conn.close()
        return response.status, payload

    def test_sanitized_cold_boot_requests(self) -> None:
        for request in self.requests:
            with self.subTest(path=request["path"]):
                status, body = self.post(request["path"], request["body"])
                self.assertEqual(status, 200)
                self.assertIn("result", body)

    def test_ota_is_non_destructive(self) -> None:
        request = self.requests[0]
        status, body = self.post(request["path"], request["body"])
        self.assertEqual(status, 200)
        self.assertEqual(body, {"result": {}})

    def test_response_matches_captured_http11_framing(self) -> None:
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        conn.request("POST", "/6/feedermini/dev_ota_check", "")
        response = conn.getresponse()
        self.assertEqual(response.version, 11)
        self.assertEqual(response.reason, "")
        self.assertIsNone(response.getheader("Server"))
        self.assertEqual(response.getheader("Connection"), "close")
        self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "*")
        response.read()
        conn.close()

    def test_small_json_headers_and_body_use_one_socket_write(self) -> None:
        with socket.create_connection(("127.0.0.1", self.server.server_port)) as conn:
            conn.sendall(
                b"POST /6/feedermini/dev_ota_check HTTP/1.1\r\n"
                b"Host: localhost\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            )
            first_read = conn.recv(1460)
        self.assertIn(b"HTTP/1.1 200 \r\n", first_read)
        self.assertIn(b"\r\n\r\n{\"result\":{}}", first_read)

    def test_rejects_malformed_content_length(self) -> None:
        with socket.create_connection(("127.0.0.1", self.server.server_port)) as conn:
            conn.sendall(
                b"POST /6/feedermini/dev_ota_check HTTP/1.1\r\n"
                b"Host: localhost\r\nContent-Length: invalid\r\n"
                b"Connection: close\r\n\r\n"
            )
            response = conn.recv(1460)
        self.assertIn(b"HTTP/1.1 400 ", response)
        self.assertIn(b"invalid content length", response)

    def test_rejects_oversized_request_without_reading_body(self) -> None:
        with socket.create_connection(("127.0.0.1", self.server.server_port)) as conn:
            conn.sendall(
                b"POST /6/feedermini/dev_ota_check HTTP/1.1\r\n"
                b"Host: localhost\r\nContent-Length: 1048577\r\n"
                b"Connection: close\r\n\r\n"
            )
            response = conn.recv(1460)
        self.assertIn(b"HTTP/1.1 413 ", response)
        self.assertIn(b"request body too large", response)

    def test_times_out_incomplete_request_body(self) -> None:
        server = MODULE.make_server(
            "127.0.0.1",
            0,
            self.server.fixtures,
            self.profile,
            request_read_timeout=0.1,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with socket.create_connection(("127.0.0.1", server.server_port)) as conn:
                conn.settimeout(1)
                conn.sendall(
                    b"POST /6/feedermini/dev_ota_check HTTP/1.1\r\n"
                    b"Host: localhost\r\nContent-Length: 10\r\n"
                    b"Connection: close\r\n\r\n"
                )
                response = conn.recv(1460)
            self.assertIn(b"HTTP/1.1 408 ", response)
            self.assertIn(b"request body timed out", response)

            conn = HTTPConnection("127.0.0.1", server.server_port, timeout=1)
            conn.request("POST", "/6/feedermini/dev_ota_check", "")
            normal_response = conn.getresponse()
            self.assertEqual(normal_response.status, 200)
            normal_response.read()
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_ota_check_logs_only_sanitized_versions(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        MODULE.LOG.addHandler(handler)
        MODULE.LOG.setLevel(logging.INFO)
        try:
            self.post(
                "/6/feedermini/dev_ota_check",
                "firmware=1.406&firmwareDetails=%5B%7B%22module%22%3A%22userbin%22%2C%22version%22%3A2207006%2C%22secret%22%3A%22PRIVATE%22%7D%5D",
            )
        finally:
            MODULE.LOG.removeHandler(handler)
        output = stream.getvalue()
        self.assertIn('"firmware_version":"1.406"', output)
        self.assertIn('"firmware_modules":[{"module":"userbin","version":2207006}]', output)
        self.assertNotIn("PRIVATE", output)

    def test_ota_start_acknowledges_without_echoing_metadata(self) -> None:
        status, body = self.post(
            "/6/feedermini/dev_ota_start",
            "hardware=1&firmware=1.406&firmwareDetails=[]&otaFirmwareId=2207007",
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, {"result": {}})

    def test_ota_complete_acknowledges_success_report(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        MODULE.LOG.addHandler(handler)
        MODULE.LOG.setLevel(logging.INFO)
        try:
            status, body = self.post(
                "/6/feedermini/dev_ota_complete",
                "hardware=1&firmware=PRIVATE&firmwareDetails=[]&success=1",
            )
        finally:
            MODULE.LOG.removeHandler(handler)
        self.assertEqual(status, 200)
        self.assertEqual(body, {"result": {}})
        output = stream.getvalue()
        self.assertIn('"ota_success":1', output)
        self.assertIn('"ota_error_present":false', output)
        self.assertNotIn("PRIVATE", output)

        ota_path = "/6/feedermini/dev_ota_check"
        original = self.server.fixtures[ota_path]
        self.server.fixtures[ota_path] = {
            "status": 200,
            "body": {"result": {"firmwareId": 999}},
        }
        try:
            status, body = self.post(
                ota_path,
                "hardware=1&firmware=1.406&firmwareDetails=[]&wait=0&force=0",
            )
            self.assertEqual(status, 200)
            self.assertEqual(body, {"result": {}})
        finally:
            self.server.fixtures[ota_path] = original
            self.server.ota_offer_completed = False

    def test_ota_heartbeat_is_supported(self) -> None:
        status, body = self.post(
            "/6/feedermini/dev_ota_heartbeat",
            "hardware=1&firmware=1.406&firmwareDetails=[]",
        )
        self.assertEqual(status, 200)
        self.assertEqual(body, {"result": {}})

    def test_logs_omit_values_headers_and_query(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        MODULE.LOG.addHandler(handler)
        MODULE.LOG.setLevel(logging.INFO)
        try:
            self.post(
                "/6/feedermini/dev_signup?token=QUERY_SECRET",
                "sn=BODY_SECRET&mac=MAC_SECRET",
                "sign=HEADER_SECRET",
            )
        finally:
            MODULE.LOG.removeHandler(handler)
        output = stream.getvalue()
        self.assertIn('"form_fields":["mac","sn"]', output)
        for secret in ("QUERY_SECRET", "BODY_SECRET", "MAC_SECRET", "HEADER_SECRET"):
            self.assertNotIn(secret, output)

    def test_state_log_exposes_only_whitelisted_integer_flags(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        MODULE.LOG.addHandler(handler)
        MODULE.LOG.setLevel(logging.INFO)
        state = json.dumps({
            "ota": 3,
            "feeding": 0,
            "runtime": 48,
            "firmware": "PRIVATE_FIRMWARE",
            "wifi": {"ssid": "PRIVATE_SSID"},
            "secret": "PRIVATE_SECRET",
        })
        try:
            from urllib.parse import urlencode

            self.post("/6/feedermini/dev_state_report", urlencode({"state": state}))
        finally:
            MODULE.LOG.removeHandler(handler)
        output = stream.getvalue()
        self.assertIn('"state_flags":{"feeding":0,"ota":3,"runtime":48}', output)
        for secret in ("PRIVATE_FIRMWARE", "PRIVATE_SSID", "PRIVATE_SECRET"):
            self.assertNotIn(secret, output)

    def test_unknown_route_fails_closed(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        MODULE.LOG.addHandler(handler)
        MODULE.LOG.setLevel(logging.INFO)
        try:
            status, body = self.post("/unknown?token=QUERY_SECRET", "secret=DO_NOT_LOG")
        finally:
            MODULE.LOG.removeHandler(handler)
        self.assertEqual(status, 404)
        self.assertEqual(body, {"error": "unsupported route"})
        self.assertIn('"path":"/unknown"', stream.getvalue())
        self.assertNotIn("QUERY_SECRET", stream.getvalue())
        self.assertNotIn("DO_NOT_LOG", stream.getvalue())

    def test_synctime_is_supported(self) -> None:
        status, body = self.post("/6/feedermini/dev_synctime", "")
        self.assertEqual(status, 200)
        self.assertRegex(body["result"]["time"], r"^\d{4}-\d{2}-\d{2}T")

    def test_ota_image_byte_range(self) -> None:
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        conn.request("POST", MODULE.DEFAULT_OTA_IMAGE_ROUTE, b"", {"Range": "bytes=0-15"})
        response = conn.getresponse()
        payload = response.read()
        self.assertEqual(response.status, 206)
        self.assertEqual(
            response.getheader("Content-Range"),
            f"bytes 0-15/{len(self.ota_image)}",
        )
        self.assertEqual(payload[:2], b"\xEA\x04")
        self.assertEqual(len(payload), 16)
        conn.close()

    def test_invalid_ota_range_returns_json_416(self) -> None:
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        conn.request(
            "GET",
            MODULE.DEFAULT_OTA_IMAGE_ROUTE,
            headers={"Range": f"bytes={len(self.ota_image)}-"},
        )
        response = conn.getresponse()
        payload = json.loads(response.read())
        self.assertEqual(response.status, 416)
        self.assertEqual(
            response.getheader("Content-Range"), f"bytes */{len(self.ota_image)}"
        )
        self.assertIsNone(response.getheader("Server"))
        self.assertEqual(payload, {"error": "range not satisfiable"})
        conn.close()

    def test_unsupported_method_returns_json_501(self) -> None:
        conn = HTTPConnection("127.0.0.1", self.server.server_port)
        conn.request("PUT", "/unsupported", "")
        response = conn.getresponse()
        payload = json.loads(response.read())
        self.assertEqual(response.status, 501)
        self.assertIsNone(response.getheader("Server"))
        self.assertEqual(payload, {"error": "not implemented"})
        conn.close()

    def test_profiled_image_route(self) -> None:
        server = MODULE.make_server(
            "127.0.0.1", 0, {}, self.profile, self.ota_image, "/ota/test.bin"
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", server.server_port)
            conn.request("GET", "/ota/test.bin", headers={"Range": "bytes=0-15"})
            response = conn.getresponse()
            payload = response.read()
            self.assertEqual(response.status, 206)
            self.assertEqual(
                response.getheader("Content-Range"),
                f"bytes 0-15/{len(self.ota_image)}",
            )
            self.assertEqual(payload[:2], b"\xEA\x04")
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_ota_loader_rejects_corruption(self) -> None:
        image = bytearray(self.ota_image)
        image[-1] ^= 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrupt-v2.bin"
            path.write_bytes(image)
            with self.assertRaisesRegex(ValueError, "CRC32"):
                MODULE.load_ota_image(path, self.profile)

    def test_ota_route_must_be_a_plain_absolute_path(self) -> None:
        for route in ("relative.bin", "//host/image.bin", "/image.bin?token=secret"):
            with self.subTest(route=route):
                with self.assertRaisesRegex(ValueError, "absolute HTTP path"):
                    MODULE.validate_ota_route(route, set())

    def test_ota_route_cannot_replace_a_petkit_api(self) -> None:
        with self.assertRaisesRegex(ValueError, "conflicts"):
            MODULE.validate_ota_route(
                "/6/feedermini/dev_ota_check",
                {"/6/feedermini/dev_ota_check"},
            )

    def test_ota_offer_rejects_digest_mismatch(self) -> None:
        offer = {
            "details": [
                {
                    "file": {
                        "size": len(self.ota_image),
                        "digest": "00000000",
                        "url": MODULE.OTA_IMAGE_URL_PLACEHOLDER,
                    }
                }
            ]
        }
        with self.assertRaisesRegex(ValueError, "digest"):
            MODULE.validate_ota_offer(
                offer,
                self.ota_image,
                self.profile,
            )

    def test_ota_offer_rejects_malformed_details(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly one"):
            MODULE.validate_ota_offer(
                {"details": []},
                self.ota_image,
                self.profile,
            )

    def test_ota_offer_rejects_fixed_download_url(self) -> None:
        offer = {
            "details": [
                {
                    "file": {
                        "size": len(self.ota_image),
                        "digest": MODULE.ota_image_digest(
                            self.ota_image, self.profile
                        ),
                        "url": "http://192.0.2.1/ota/image.bin",
                    }
                }
            ]
        }
        with self.assertRaisesRegex(ValueError, "must use.*OTA_IMAGE_URL"):
            MODULE.validate_ota_offer(offer, self.ota_image, self.profile)

    def test_ota_offer_uses_address_reached_by_device(self) -> None:
        digest = MODULE.ota_image_digest(self.ota_image, self.profile)
        fixtures = {
            self.profile["http"]["ota_check_route"]: {
                "body": {
                    "result": {
                        "firmwareId": 7,
                        "version": "test",
                        "details": [
                            {
                                "module": "userbin",
                                "version": 8,
                                "file": {
                                    "size": len(self.ota_image),
                                    "digest": digest,
                                    "url": MODULE.OTA_IMAGE_URL_PLACEHOLDER,
                                },
                            }
                        ],
                    }
                }
            }
        }
        server = MODULE.make_server(
            "127.0.0.1", 0, fixtures, self.profile, self.ota_image
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", server.server_port)
            conn.request("POST", self.profile["http"]["ota_check_route"], "")
            response = conn.getresponse()
            body = json.loads(response.read())
            self.assertEqual(
                body["result"]["details"][0]["file"]["url"],
                f"http://127.0.0.1:{server.server_port}/ota/image.bin",
            )
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_fixture_loader_rejects_malformed_response(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixtures.json"
            path.write_text('{"relative": {"status": 999}}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "absolute HTTP paths"):
                MODULE.load_fixtures(path)

    def test_nearest_fixture_overrides_parent_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "parent.json"
            child = Path(directory) / "child.json"
            parent.write_text(
                '{"/shared":{"body":{"source":"parent"}}}', encoding="utf-8"
            )
            child.write_text(
                '{"/shared":{"body":{"source":"child"}}}', encoding="utf-8"
            )
            fixtures = MODULE.merge_fixtures([parent, child])
            self.assertEqual(fixtures["/shared"]["body"]["source"], "child")


if __name__ == "__main__":
    unittest.main()
