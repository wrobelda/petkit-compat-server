#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLASH = ROOT.parent / "petkit-serial-bus" / "flash dumps" / "petkitesp8266flash.bin"
SPEC = importlib.util.spec_from_file_location(
    "analyze_stock_ota",
    ROOT
    / "devices"
    / "esp8266"
    / "nonos_v2"
    / "tools"
    / "analyze_stock_ota.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


@unittest.skipUnless(FLASH.exists(), "stock flash reference is absent")
class StockOtaImageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.flash = FLASH.read_bytes()

    def test_both_stock_slots_are_complete_and_valid(self) -> None:
        expected = ((0x1000, 0x9B974), (0x101000, 0xA17D4))
        for offset, length in expected:
            with self.subTest(offset=hex(offset)):
                image = MODULE.parse_v2_image(self.flash, offset)
                self.assertEqual(image["length"], length)
                self.assertTrue(image["checksum_valid"])
                self.assertTrue(image["crc32_valid"])

    def test_corruption_breaks_sdk_crc(self) -> None:
        damaged = bytearray(self.flash)
        damaged[0x2000] ^= 1
        image = MODULE.parse_v2_image(damaged, 0x1000)
        self.assertFalse(image["crc32_valid"])


if __name__ == "__main__":
    unittest.main()
