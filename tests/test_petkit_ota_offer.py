from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.v2_image import make_v2_image

SPEC = importlib.util.spec_from_file_location("serve_petkit_api", ROOT / "serve_petkit_api.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PetkitOtaOfferTest(unittest.TestCase):
    def test_fixture_uses_image_size_and_appended_sdk_crc(self) -> None:
        image = make_v2_image()
        profile = MODULE.load_profile(
            ROOT / "devices" / "esp8266" / "nonos_v2" / "fresh-element-mini" / "profile.json"
        )
        result = MODULE.make_ota_offer(image, profile)
        file_info = result["details"][0]["file"]
        self.assertEqual(file_info["size"], len(image))
        self.assertEqual(file_info["digest"], MODULE.ota_image_digest(image, profile))
        self.assertEqual(file_info["url"], "${OTA_IMAGE_URL}")


if __name__ == "__main__":
    unittest.main()
