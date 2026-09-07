#!/usr/bin/env python3
"""Provision a stock Petkit device through its profiled SoftAP TCP service."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import socket
from typing import Any
from urllib.parse import urlsplit

from petkit_compat.profile import load_profile
from petkit_compat.softap import MAX_BODY_BYTES, decode_frame, encode_json, redact


def provisioning_payload(
    ssid: str,
    password: str,
    server: str,
    timezone: str,
    locale: str,
    profile: dict[str, Any],
) -> dict[str, Any]:
    softap = profile["softap"]
    fields = softap["payload_fields"]
    return {
        fields["ssid"]: ssid,
        fields["password"]: password,
        fields["hidden"]: softap["hidden_value"],
        fields["server"]: server,
        fields["timezone"]: timezone,
        fields["locale"]: locale,
    }


def validate_server(value: str, suffix: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise argparse.ArgumentTypeError("server must be an http(s) URL")
    if not parsed.path.endswith(suffix):
        raise argparse.ArgumentTypeError(f"server URL must end with {suffix}")
    return value


def server_from_host(host: str, port: int, suffix: str) -> str:
    if not host or any(character in host for character in "/?#@"):
        raise argparse.ArgumentTypeError("server host must be an IP address or hostname")
    url_host = f"[{host}]" if ":" in host else host
    return validate_server(f"http://{url_host}:{port}{suffix}", suffix)


def recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise EOFError("SoftAP connection closed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def recv_message(sock: socket.socket) -> Any:
    header = recv_exact(sock, 4)
    size = int.from_bytes(header, "big")
    if size > MAX_BODY_BYTES:
        raise ValueError(f"SoftAP response is too large: {size} bytes")
    return decode_frame(header + recv_exact(sock, size))


def message_key(message: Any) -> int | None:
    if not isinstance(message, dict):
        return None
    key = message.get("key")
    return key if isinstance(key, int) else None


def log_event(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **redact(fields)}, separators=(",", ":")))


def send_message(sock: socket.socket, message: dict[str, Any]) -> None:
    sock.sendall(encode_json(message))
    payload = message.get("payload")
    log_event(
        "softap_send",
        key=message.get("key"),
        payload_fields=sorted(payload) if isinstance(payload, dict) else [],
    )


def wait_for_key(
    sock: socket.socket, expected: int, heartbeat: int
) -> dict[str, Any]:
    while True:
        message = recv_message(sock)
        key = message_key(message)
        log_event(
            "softap_receive",
            key=key,
            payload_fields=(
                sorted(message.get("payload", {}))
                if isinstance(message, dict) and isinstance(message.get("payload"), dict)
                else []
            ),
        )
        if key == heartbeat:
            send_message(sock, {"key": heartbeat})
            continue
        if key != expected:
            raise ValueError(f"expected SoftAP key {expected}, received {key!r}")
        return message


def provision(
    host: str,
    port: int,
    payload: dict[str, Any],
    timeout: float,
    softap: dict[str, Any],
) -> None:
    keys = softap["keys"]
    heartbeat = keys["heartbeat"]
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)

        send_message(sock, {"key": keys["hello"]})
        wait_for_key(sock, keys["hello"], heartbeat)

        send_message(sock, {"key": keys["status"]})
        status_message = wait_for_key(sock, keys["status"], heartbeat)
        status_payload = status_message.get("payload", {})
        status = status_payload.get("status") if isinstance(status_payload, dict) else None
        meaning = softap["status_errors"].get(str(status))
        if meaning is not None:
            raise RuntimeError(f"feeder reports status {status}: {meaning}")

        send_message(sock, {"key": keys["configure"], "payload": payload})
        wait_for_key(sock, keys["configure"], heartbeat)

        send_message(sock, {"key": keys["commit"]})
        try:
            wait_for_key(sock, keys["commit"], heartbeat)
        except (EOFError, ConnectionResetError):
            # Stock firmware may leave SoftAP immediately after key 153.
            log_event("softap_disconnect_after_commit")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--profile", type=Path, required=True)
    result.add_argument("--host")
    result.add_argument("--port", type=int)
    result.add_argument("--ssid", required=True, help="target 2.4 GHz Wi-Fi SSID")
    server = result.add_mutually_exclusive_group(required=True)
    server.add_argument("--server", help="complete Petkit API URL")
    server.add_argument(
        "--server-host",
        help="address of this computer; the profile supplies the API path",
    )
    result.add_argument("--server-port", type=int, default=8080)
    result.add_argument("--timezone", required=True, help="UTC offset in hours")
    result.add_argument("--locale", required=True, help="IANA time zone")
    result.add_argument("--timeout", type=float, default=15.0)
    result.add_argument(
        "--send",
        action="store_true",
        help="perform provisioning; otherwise print a redacted preview",
    )
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        profile = load_profile(args.profile)
    except ValueError as error:
        raise SystemExit(f"invalid profile: {error}") from error
    softap = profile["softap"]
    host = args.host or softap["host"]
    port = args.port or softap["port"]
    try:
        server = (
            validate_server(args.server, softap["server_path_suffix"])
            if args.server is not None
            else server_from_host(
                args.server_host,
                args.server_port,
                softap["server_path_suffix"],
            )
        )
    except argparse.ArgumentTypeError as error:
        raise SystemExit(str(error)) from error
    password = os.environ.get("ESPHOME_WIFI_PASSWORD")
    if args.send and password is None:
        password = getpass.getpass("Target Wi-Fi password: ")
    if password is None:
        password = "<not supplied>"
    payload = provisioning_payload(
        args.ssid, password, server, args.timezone, args.locale, profile
    )
    log_event(
        "softap_plan",
        profile=profile["name"],
        host=host,
        port=port,
        payload=payload,
        send=args.send,
    )
    if not args.send:
        return
    if not password:
        raise SystemExit("target Wi-Fi password must not be empty")
    try:
        provision(host, port, payload, args.timeout, softap)
    except (OSError, EOFError, ValueError, RuntimeError) as error:
        raise SystemExit(f"provisioning failed: {error}") from error
    log_event("softap_provisioned")


if __name__ == "__main__":
    main()
