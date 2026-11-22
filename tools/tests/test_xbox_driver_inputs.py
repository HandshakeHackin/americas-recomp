import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
DRIVER = Path(os.environ.get("XBOX_DRIVER", ROOT / "build-xbox" / ("driver.exe" if os.name == "nt" else "driver")))


@unittest.skipUnless(DRIVER.is_file(), "build tools/xbox or set XBOX_DRIVER")
class DriverInputTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.input = self.root / "shader.bin"
        self.output = self.root / "shader.spv"

    def run_driver(self):
        return subprocess.run([str(DRIVER), str(self.input), "32", str(self.output)],
                              capture_output=True, text=True, timeout=30)

    def check_input_error(self, result, message):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(message, result.stdout)
        self.assertNotIn("runtime error:", result.stderr)
        self.assertNotIn("AddressSanitizer", result.stderr)
        self.assertFalse(self.output.exists())

    def test_missing_shader_file_reports_an_input_error(self):
        self.check_input_error(self.run_driver(), "cannot open shader file")

    def test_inputs_without_a_complete_word_are_rejected(self):
        for size in range(4):
            with self.subTest(size=size):
                self.input.write_bytes(bytes(size))
                self.check_input_error(self.run_driver(), "no complete instruction word")

    def test_a_complete_endpgm_instruction_still_compiles(self):
        self.input.write_bytes(struct.pack("<I", 0xBF810000))
        result = self.run_driver()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.output.read_bytes()[:4], struct.pack("<I", 0x07230203))


if __name__ == "__main__":
    unittest.main()
