from pathlib import Path
import tempfile
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from petkit_compat.firmware import load_ota_image
from tests.v2_image import make_v2_image


class FirmwareFormatTest(unittest.TestCase):
    def test_rejects_unknown_profile_format(self) -> None:
        profile = {"firmware": {"format": "unknown-format"}}
        with self.assertRaisesRegex(ValueError, "unsupported firmware format"):
            load_ota_image(Path("unused.bin"), profile)

    def test_requires_profile_format(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not define"):
            load_ota_image(Path("unused.bin"), {})

    def test_rejects_image_larger_than_smallest_slot(self) -> None:
        profile = {
            "firmware": {
                "format": "esp8266-nonos-v2",
                "slots": [{"size": 32}, {"size": 64}],
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.bin"
            path.write_bytes(make_v2_image())
            with self.assertRaisesRegex(ValueError, "smallest configured slot"):
                load_ota_image(path, profile)


if __name__ == "__main__":
    unittest.main()
