import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "xbox/platform/xgr/run_tests.py"
spec = importlib.util.spec_from_file_location("xgr_run_tests", SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class XgrTestTimeoutOutput(unittest.TestCase):
    def timeout(self, stdout=None, stderr=None, encoding="utf-8"):
        error = subprocess.TimeoutExpired(["synthetic.exe"], 1, output=stdout, stderr=stderr)
        with (
            patch.object(runner, "TIMEOUT", 1),
            patch.object(runner.subprocess, "run", side_effect=error),
            patch.object(runner.locale, "getpreferredencoding", return_value=encoding),
        ):
            out, code, seconds = runner.run_test(Path("synthetic.exe"), [], {}, Path("."))
        self.assertIsNone(code)
        self.assertGreaterEqual(seconds, 0)
        self.assertTrue(out.endswith("\nFAIL timed out after 1 s"))
        return out

    def test_timeout_retains_stdout_and_stderr_bytes(self):
        out = self.timeout(b"last progress\n", b"last diagnostic\n")
        self.assertEqual(out, "last progress\nlast diagnostic\n\nFAIL timed out after 1 s")

    def test_timeout_retains_text_captures(self):
        out = self.timeout("last progress\n", "last diagnostic\n")
        self.assertEqual(out, "last progress\nlast diagnostic\n\nFAIL timed out after 1 s")

    def test_timeout_with_only_stderr_keeps_the_diagnostic(self):
        self.assertEqual(self.timeout(stderr=b"diagnostic"), "diagnostic\nFAIL timed out after 1 s")

    def test_timeout_without_output_still_has_the_failure_line(self):
        self.assertEqual(self.timeout(), "\nFAIL timed out after 1 s")

    def test_timeout_replaces_invalid_bytes(self):
        self.assertEqual(self.timeout(b"bad: \xff"), "bad: \ufffd\nFAIL timed out after 1 s")

    def test_timeout_decodes_with_the_subprocess_locale(self):
        self.assertEqual(self.timeout(b"caf\xe9", encoding="cp1252"), "caf\u00e9\nFAIL timed out after 1 s")

    def test_completed_test_keeps_combined_output_and_exit_status(self):
        result = subprocess.CompletedProcess(["synthetic.exe"], 7, "progress\n", "diagnostic\n")
        with patch.object(runner.subprocess, "run", return_value=result):
            out, code, seconds = runner.run_test(Path("synthetic.exe"), [], {}, Path("."))
        self.assertEqual((out, code), ("progress\ndiagnostic\n", 7))
        self.assertGreaterEqual(seconds, 0)


if __name__ == "__main__":
    unittest.main()
