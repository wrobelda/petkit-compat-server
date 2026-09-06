from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CommandLineSmokeTest(unittest.TestCase):
    def assert_help(self, script: Path) -> None:
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout)

    def test_user_commands_start(self) -> None:
        self.assert_help(ROOT / "serve_petkit_api.py")
        self.assert_help(ROOT / "provision_petkit_device.py")

    def test_layout_analyzer_starts_by_path(self) -> None:
        self.assert_help(
            ROOT
            / "devices"
            / "esp8266"
            / "nonos_v2"
            / "tools"
            / "analyze_stock_ota.py"
        )


if __name__ == "__main__":
    unittest.main()
