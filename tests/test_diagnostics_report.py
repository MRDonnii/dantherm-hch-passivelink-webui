import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("diagnostics_report", ROOT / "gateway/diagnostics_report.py")
MODULE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)


class DiagnosticReportTests(unittest.TestCase):
    def test_redacts_credentials(self):
        text = "DANTHERM_REBOOT_TOKEN=abc123\npassword=hunter2\nAuthorization: Bearer secret-token\ndantherm_session=session-value\nNetworkManager: secret-key: local-value"
        redacted = MODULE.redact(text)
        self.assertNotIn("abc123", redacted)
        self.assertNotIn("hunter2", redacted)
        self.assertNotIn("secret-token", redacted)
        self.assertNotIn("session-value", redacted)
        self.assertNotIn("local-value", redacted)
        self.assertGreaterEqual(redacted.count("[REDACTED]"), 5)

    def test_report_is_one_bounded_text_file(self):
        completed = mock.Mock(stdout="PASSWORD=do-not-share\nservice ok\n", stderr="", returncode=0)
        with mock.patch.object(MODULE.subprocess, "run", return_value=completed), mock.patch.object(MODULE.platform, "platform", return_value="Linux-test"):
            payload, filename = MODULE.build_report({"gateway": "gateway.service"})
        self.assertTrue(filename.startswith("dantherm-debug-"))
        self.assertTrue(filename.endswith(".txt"))
        self.assertIn(b"SERVICE STATUS", payload)
        self.assertIn(b"PASS", payload)
        self.assertNotIn(b"do-not-share", payload)
        self.assertLess(len(payload), 8 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
