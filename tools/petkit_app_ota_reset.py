#!/usr/bin/env python3
"""Issue the Petkit app API OTA-reset command for an owned Petkit device.

Credentials are accepted only through the environment and are never printed.
The command is a dry run unless --send is supplied.
"""

import argparse
import datetime
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo


DEFAULT_URL = "https://api.eu-pet.com/6/feedermini/ota_reset"
API_VERSION = "13.2.1"


def base_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "okhttp/3.14.9",
        "X-Api-Version": API_VERSION,
        "X-Client": "android(16.1;23127PN0CG)",
        "X-Img-Version": "1",
        "X-Locale": "en-US",
        "X-Hour": "24",
    }


def login_form(username: str, password: str, region: str) -> dict[str, str]:
    # Match the current reversed Android client. Petkit expects an MD5 of the
    # password here; TLS protects the request in transit.
    timezone = os.environ.get("PETKIT_TIMEZONE", "Europe/Warsaw")
    offset = datetime.datetime.now(ZoneInfo(timezone)).utcoffset()
    timezone_offset = str((offset.total_seconds() if offset else 0) / 3600)
    client = {
        "locale": "en-US",
        "name": "23127PN0CG",
        "osVersion": "16.1",
        "phoneBrand": "Xiaomi",
        "platform": "android",
        "source": "app.petkit-android",
        "version": API_VERSION,
        "timezoneId": timezone,
        "timezone": timezone_offset,
    }
    return {
        "oldVersion": API_VERSION,
        "client": str(client),
        "encrypt": "1",
        "region": region,
        "username": username,
        "password": hashlib.md5(password.encode()).hexdigest(),
    }


def post_json(url: str, form: dict[str, str], headers: dict[str, str]) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(form).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = response.read(65536).decode("utf-8", "replace")
        parsed = json.loads(payload)
        if not isinstance(parsed, dict):
            raise ValueError("Petkit response is not a JSON object")
        return response.status, parsed


def api_root(ota_url: str) -> str:
    marker = "/feedermini/"
    if marker not in ota_url:
        raise ValueError("OTA URL must contain /feedermini/")
    return ota_url.split(marker, 1)[0].rstrip("/") + "/"


def obtain_session(ota_url: str) -> str:
    existing = os.environ.get("PETKIT_SESSION")
    if existing:
        return existing
    username = os.environ.get("PETKIT_USERNAME")
    password = os.environ.get("PETKIT_PASSWORD")
    if not username or not password:
        raise ValueError(
            "set PETKIT_SESSION, or set both PETKIT_USERNAME and PETKIT_PASSWORD"
        )
    region = os.environ.get("PETKIT_REGION", "pl").lower()
    login_url = urllib.parse.urljoin(api_root(ota_url), "user/login")
    _status, response = post_json(login_url, login_form(username, password, region), base_headers())
    result = response.get("result")
    session = result.get("session") if isinstance(result, dict) else None
    session_id = session.get("id") if isinstance(session, dict) else None
    if not isinstance(session_id, str) or not session_id:
        error = response.get("error")
        code = error.get("code") if isinstance(error, dict) else None
        raise ValueError(f"Petkit login failed (error code {code!r})")
    return session_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device-id", required=True, help="Petkit numeric device ID")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--send", action="store_true", help="perform the request")
    args = parser.parse_args()

    if not args.device_id.isdecimal():
        parser.error("--device-id must be numeric")

    print(json.dumps({"method": "POST", "url": args.url, "fields": ["deviceId"]}))
    if not args.send:
        print("dry run; add --send and set PETKIT_USERNAME/PETKIT_PASSWORD or PETKIT_SESSION")
        return 0

    try:
        session = obtain_session(args.url)
        headers = base_headers()
        headers.update({"F-Session": session, "X-Session": session})
        status, parsed = post_json(args.url, {"deviceId": args.device_id}, headers)
        result = parsed.get("result")
        error = parsed.get("error")
        print(json.dumps({
            "status": status,
            "result": result is not None,
            "error_code": error.get("code") if isinstance(error, dict) else None,
        }))
    except urllib.error.HTTPError as exc:
        exc.read(65536)
        print(json.dumps({"status": exc.code}), file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError) as exc:
        print(json.dumps({"error": type(exc).__name__}), file=sys.stderr)
        return 1
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
