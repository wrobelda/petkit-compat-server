from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from petkit_compat.profile import load_profile


ROOT = Path(__file__).resolve().parents[1]
PROFILE = (
    ROOT
    / "devices"
    / "esp8266"
    / "nonos_v2"
    / "fresh-element-mini"
    / "profile.json"
)


class ProfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.valid = json.loads(PROFILE.read_text(encoding="utf-8"))

    def load_changed(self, change) -> None:
        profile = copy.deepcopy(self.valid)
        change(profile)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            load_profile(path)

    def test_current_profile_is_valid(self) -> None:
        self.assertEqual(load_profile(PROFILE)["name"], "petkit-fresh-element-mini")

    def test_rejects_overlapping_slots(self) -> None:
        with self.assertRaisesRegex(ValueError, "overlap"):
            self.load_changed(
                lambda profile: profile["firmware"]["slots"][1].update(
                    offset=0x1000
                )
            )

    def test_rejects_incomplete_softap_keys(self) -> None:
        with self.assertRaisesRegex(ValueError, "protocol keys"):
            self.load_changed(
                lambda profile: profile["softap"]["keys"].pop("heartbeat")
            )

    def test_rejects_duplicate_routes(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            self.load_changed(
                lambda profile: profile["http"].update(
                    ota_complete_route=profile["http"]["ota_check_route"]
                )
            )

    def test_rejects_absolute_fixture_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "relative paths"):
            self.load_changed(
                lambda profile: profile.update(fixtures=["/private.json"])
            )


if __name__ == "__main__":
    unittest.main()
