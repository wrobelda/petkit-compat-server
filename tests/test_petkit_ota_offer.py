from __future__ import annotations

import importlib.util
import struct
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.v2_image import make_v2_image

SPEC = importlib.util.spec_from_file_location(
    "make_petkit_ota_offer",
    ROOT
    / "devices"
    / "esp8266"
    / "nonos_v2"
    / "fresh-element-mini"
    / "tools"
    / "make_ota_offer.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PetkitOtaOfferTest(unittest.TestCase):
    def test_fixture_uses_image_size_and_appended_sdk_crc(self) -> None:
        image = make_v2_image()
        fixture = MODULE.make_fixture(
            image,
            firmware_id=7,
            version="local-transition",
            module_version=8,
            url="http://192.0.2.1/ota/transition.bin",
        )
        result = fixture["/6/feedermini/dev_ota_check"]["body"]["result"]
        file_info = result["details"][0]["file"]
        self.assertEqual(file_info["size"], len(image))
        self.assertEqual(
            file_info["digest"], f"{struct.unpack_from('<I', image, len(image) - 4)[0]:08x}"
        )


if __name__ == "__main__":
    unittest.main()
