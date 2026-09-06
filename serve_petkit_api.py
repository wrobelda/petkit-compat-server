#!/usr/bin/env python3
"""Serve a local fixture-driven HTTP API to stock Petkit devices."""

from __future__ import annotations

import argparse
import email.utils
import json
import logging
import re
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from petkit_compat.firmware import load_ota_image, ota_image_digest
from petkit_compat.profile import load_profile


LOG = logging.getLogger("petkit.compat")
DEFAULT_OTA_IMAGE_ROUTE = "/ota/image.bin"
OTA_IMAGE_URL_PLACEHOLDER = "${OTA_IMAGE_URL}"


def load_fixtures(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        fixtures = json.load(handle)
    if not isinstance(fixtures, dict):
        raise ValueError("fixture root must be an object")
    for route, response in fixtures.items():
        if (
            not isinstance(route, str)
            or not route.startswith("/")
            or route.startswith("//")
            or urllib.parse.urlsplit(route).path != route
        ):
            raise ValueError("fixture routes must be plain absolute HTTP paths")
        if not isinstance(response, dict) or "body" not in response:
            raise ValueError(f"fixture response for {route!r} must contain a body")
        status = response.get("status", 200)
        if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
            raise ValueError(f"fixture status for {route!r} must be an HTTP status")
    return fixtures


def validate_ota_route(route: str, api_routes: set[str]) -> str:
    parts = urllib.parse.urlsplit(route)
    if (
        not route.startswith("/")
        or route.startswith("//")
        or parts.scheme
        or parts.netloc
        or parts.query
        or parts.fragment
        or parts.path != route
        or any(ord(character) < 0x20 for character in route)
    ):
        raise ValueError("OTA route must be a plain absolute HTTP path")
    if route in api_routes:
        raise ValueError("OTA route conflicts with a Petkit API route")
    return route


def profile_routes(profile: dict[str, Any]) -> set[str]:
    return {
        value
        for key, value in profile["http"].items()
        if key.endswith("_route")
    }


def validate_ota_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "http"
        or not parsed.netloc
        or not parsed.path.startswith("/")
        or parsed.path.startswith("//")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "OTA URL must be plain HTTP with a host and an absolute path, "
            "without a query or fragment"
        )
    return url


def validate_ota_offer(
    offer: Any,
    ota_image: bytes | None,
    ota_route: str,
    profile: dict[str, Any],
) -> dict[str, Any] | None:
    if offer == {}:
        return None
    if not isinstance(offer, dict):
        raise ValueError("OTA result must be an object")
    if ota_image is None:
        raise ValueError("non-empty OTA metadata requires --ota-image")
    details = offer.get("details")
    if not isinstance(details, list) or len(details) != 1 or not isinstance(details[0], dict):
        raise ValueError("OTA metadata must contain exactly one details entry")
    detail = details[0]
    file_info = detail.get("file")
    if not isinstance(file_info, dict):
        raise ValueError("OTA metadata details must contain file information")
    size = file_info.get("size")
    digest = file_info.get("digest")
    url = file_info.get("url")
    if not isinstance(size, int) or isinstance(size, bool) or size != len(ota_image):
        raise ValueError("OTA metadata size does not match --ota-image")
    if digest != ota_image_digest(ota_image, profile):
        raise ValueError("OTA metadata digest does not match --ota-image")
    if not isinstance(url, str):
        raise ValueError("OTA metadata file URL must be a string")
    parsed_url = urllib.parse.urlsplit(url)
    if parsed_url.scheme != "http" or not parsed_url.netloc or parsed_url.query or parsed_url.fragment:
        raise ValueError("OTA metadata file URL must be plain HTTP without query or fragment")
    if parsed_url.path != ota_route:
        raise ValueError("OTA metadata URL path does not match --ota-url")
    return detail


def render(value: Any) -> Any:
    """Expand the small set of safe dynamic values supported by fixtures."""
    if isinstance(value, dict):
        return {key: render(item) for key, item in value.items()}
    if isinstance(value, list):
        return [render(item) for item in value]
    if value == "${NOW_ISO8601}":
        now = datetime.now().astimezone()
        return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}" + now.strftime("%z")
    return value


def request_summary(handler: BaseHTTPRequestHandler, body: bytes) -> dict[str, Any]:
    """Return log-safe metadata, never request values or authentication data."""
    content_type = handler.headers.get("Content-Type", "").split(";", 1)[0]
    summary: dict[str, Any] = {
        "event": "request",
        "method": handler.command,
        # Keep the path for protocol discovery, but never retain its query.
        # Control characters are escaped by json.dumps below.
        "path": (path := handler.path.split("?", 1)[0]),
        "content_type": content_type,
        "body_bytes": len(body),
    }
    if path == handler.server.ota_image_route and handler.headers.get("Range"):  # type: ignore[attr-defined]
        requested_range = handler.headers["Range"].strip()
        if re.fullmatch(r"bytes=\d{1,10}-\d{0,10}", requested_range):
            summary["range"] = requested_range
        else:
            summary["range"] = "<invalid>"
    if content_type == "application/x-www-form-urlencoded":
        from urllib.parse import parse_qs

        # Field names help diagnose protocol drift; values may contain secrets.
        form = parse_qs(body.decode("utf-8", "replace"))
        fields = set(form.keys())
        http_profile = handler.server.profile["http"]  # type: ignore[attr-defined]
        safe_form_fields = set(http_profile["safe_form_fields"])
        safe_state_fields = set(http_profile["safe_state_fields"])
        summary["form_fields"] = sorted(fields & safe_form_fields)
        summary["unknown_form_fields"] = len(fields - safe_form_fields)
        if path == http_profile["state_report_route"] and form.get("state"):
            try:
                state = json.loads(form["state"][0])
                if isinstance(state, dict):
                    # Only small operational integers are admitted. Strings,
                    # nested WiFi data, identifiers, and unknown keys remain
                    # redacted even if the stock schema changes.
                    flags = {
                        key: state[key]
                        for key in sorted(safe_state_fields)
                        if key in state
                        and isinstance(state[key], int)
                        and not isinstance(state[key], bool)
                    }
                    if flags:
                        summary["state_flags"] = flags
            except (json.JSONDecodeError, TypeError):
                summary["state_parse_error"] = True
        if path == http_profile["ota_check_route"]:
            firmware = form.get("firmware", [""])[0]
            if re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", firmware):
                summary["firmware_version"] = firmware
            if form.get("firmwareDetails"):
                try:
                    details = json.loads(form["firmwareDetails"][0])
                    modules = []
                    if isinstance(details, list):
                        for detail in details:
                            if not isinstance(detail, dict):
                                continue
                            module = detail.get("module")
                            version = detail.get("version")
                            if (
                                isinstance(module, str)
                                and re.fullmatch(r"[A-Za-z0-9_-]{1,24}", module)
                                and isinstance(version, int)
                                and not isinstance(version, bool)
                            ):
                                modules.append({"module": module, "version": version})
                    if modules:
                        summary["firmware_modules"] = modules
                except (json.JSONDecodeError, TypeError):
                    summary["firmware_details_parse_error"] = True
        if path == http_profile["ota_complete_route"] and form.get("success"):
            success = form["success"][0]
            if success in {"0", "1"}:
                summary["ota_success"] = int(success)
            summary["ota_error_present"] = "errmsg" in form
    return summary


class PetkitHandler(BaseHTTPRequestHandler):
    server_version = "PetkitCompat/1"
    # The older user1 stock image rejects the BaseHTTPRequestHandler default
    # HTTP/1.0 response before exposing its body to the Petkit callback. Match
    # the captured Petkit frontend status line and headers instead.
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        LOG.info(json.dumps(request_summary(self, body), separators=(",", ":")))

        route = self.path.split("?", 1)[0]
        http_profile = self.server.profile["http"]  # type: ignore[attr-defined]
        if route == http_profile["ota_complete_route"]:
            from urllib.parse import parse_qs

            form = parse_qs(body.decode("utf-8", "replace"))
            if form.get("success") == ["1"]:
                self.server.ota_offer_completed = True  # type: ignore[attr-defined]
        if (
            route == http_profile["ota_check_route"]
            and self.server.ota_offer_completed  # type: ignore[attr-defined]
        ):
            self._send_json(200, {"result": {}})
            return
        if route == self.server.ota_image_route and self.server.ota_image is not None:  # type: ignore[attr-defined]
            self._send_ota_image()
            return
        fixture = self.server.fixtures.get(route)  # type: ignore[attr-defined]
        if fixture is None:
            self._send_json(404, {"error": "unsupported route"})
            return
        self._send_json(int(fixture.get("status", 200)), render(fixture["body"]))

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        LOG.info(json.dumps(request_summary(self, b""), separators=(",", ":")))
        if self.path.split("?", 1)[0] == self.server.ota_image_route and self.server.ota_image is not None:  # type: ignore[attr-defined]
            self._send_ota_image()
            return
        self._send_json(405, {"error": "method not allowed"})

    def _send_ota_image(self) -> None:
        image = self.server.ota_image  # type: ignore[attr-defined]
        start, end = 0, len(image) - 1
        range_header = self.headers.get("Range")
        if range_header:
            match = re.fullmatch(r"bytes=(\d+)-(\d*)", range_header.strip())
            if not match:
                self.send_error(416)
                return
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else end
            if start > end or end >= len(image):
                self.send_error(416)
                return
        payload = image[start : end + 1]
        self._send_captured_headers(
            206 if range_header else 200,
            "application/octet-stream",
            len(payload),
        )
        self.send_header("Accept-Ranges", "bytes")
        if range_header:
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(image)}")
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, status: int, body: Any) -> None:
        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        # The captured Petkit frontend puts each small JSON response's headers
        # and body in one TCP write. user1's old HTTP client appears sensitive
        # to receiving the body separately, so reproduce that behavior.
        headers = (
            f"HTTP/1.1 {status} \r\n"
            f"Date: {email.utils.formatdate(usegmt=True)}\r\n"
            "Content-Type: application/json;charset=utf-8\r\n"
            f"Content-Length: {len(encoded)}\r\n"
            "Connection: close\r\n"
            "Cache-Control: no-cache\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "\r\n"
        ).encode("ascii")
        self.connection.sendall(headers + encoded)
        self.close_connection = True

    def _send_captured_headers(
        self, status: int, content_type: str, content_length: int
    ) -> None:
        # Petkit's captured response is `HTTP/1.1 200 ` (empty reason phrase),
        # with no identifying Server header. Some old embedded HTTP parsers are
        # less tolerant than browsers, so preserve that wire format.
        self.send_response_only(status, "")
        self.send_header("Date", self.date_time_string())
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")

    def log_message(self, _format: str, *_args: object) -> None:
        # The standard logger can include raw request targets. Our structured
        # request log above deliberately records only the path without a query.
        return


def make_server(
    host: str,
    port: int,
    fixtures: dict[str, dict[str, Any]],
    profile: dict[str, Any],
    ota_image: bytes | None = None,
    ota_image_route: str = DEFAULT_OTA_IMAGE_ROUTE,
) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), PetkitHandler)
    server.fixtures = fixtures  # type: ignore[attr-defined]
    server.profile = profile  # type: ignore[attr-defined]
    server.ota_image = ota_image  # type: ignore[attr-defined]
    server.ota_image_route = validate_ota_route(  # type: ignore[attr-defined]
        ota_image_route, set(fixtures) | profile_routes(profile)
    )
    server.ota_offer_completed = False  # type: ignore[attr-defined]
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--profile",
        type=Path,
        required=True,
        help="device protocol profile",
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--overlay",
        type=Path,
        help="optional fixture file whose routes override the base fixtures",
    )
    parser.add_argument(
        "--ota-image",
        type=Path,
        help="serve an OTA image validated for the selected device profile",
    )
    parser.add_argument(
        "--ota-url",
        help="client-visible HTTP URL used to download --ota-image",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate fixtures and OTA image, then exit without listening",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        profile = load_profile(args.profile)
        fixtures = load_fixtures(args.fixtures)
    except ValueError as error:
        parser.error(str(error))
    if args.overlay:
        fixtures.update(load_fixtures(args.overlay))
    ota_check_route = profile["http"]["ota_check_route"]
    ota_body = fixtures.get(ota_check_route, {}).get("body", {})
    payload_offer = ota_body.get("payload", {})
    if payload_offer:
        parser.error("non-empty OTA metadata must use the result wrapper")
    ota_offer = ota_body.get("result", {})
    if ota_offer:
        try:
            offered_url = ota_offer["details"][0]["file"]["url"]
        except (KeyError, IndexError, TypeError):
            offered_url = None
        if offered_url != OTA_IMAGE_URL_PLACEHOLDER:
            parser.error("OTA metadata file URL must use ${OTA_IMAGE_URL}")
        if args.ota_url is None:
            parser.error("non-empty OTA metadata requires --ota-url")
        ota_offer["details"][0]["file"]["url"] = args.ota_url
    try:
        if args.ota_url is not None:
            validate_ota_url(args.ota_url)
            ota_route = urllib.parse.urlsplit(args.ota_url).path
        else:
            ota_route = DEFAULT_OTA_IMAGE_ROUTE
        ota_route = validate_ota_route(
            ota_route, set(fixtures) | profile_routes(profile)
        )
        ota_image = load_ota_image(args.ota_image, profile) if args.ota_image else None
    except ValueError as error:
        parser.error(str(error))
    try:
        detail = validate_ota_offer(ota_offer, ota_image, ota_route, profile)
    except ValueError as error:
        parser.error(str(error))
    if detail is not None:
        offer_path = urllib.parse.urlsplit(detail["file"]["url"]).path
        LOG.info(
            json.dumps(
                {
                    "event": "ota_offer",
                    "firmware_id": ota_offer.get("firmwareId"),
                    "offer_version": ota_offer.get("version"),
                    "module": detail.get("module"),
                    "module_version": detail.get("version"),
                    "image_bytes": detail["file"].get("size"),
                    "path": offer_path,
                },
                separators=(",", ":"),
            )
        )
    if args.check:
        return
    server = make_server(
        args.host,
        args.port,
        fixtures,
        profile,
        ota_image,
        ota_route,
    )
    LOG.info(
        "listening on %s:%d with profile %s and fixtures %s%s",
        args.host,
        args.port,
        profile["name"],
        args.fixtures,
        f" plus {args.overlay}" if args.overlay else "",
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
