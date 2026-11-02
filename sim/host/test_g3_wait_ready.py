"""G3 CAPS 契约和显式目标地址的主机侧检查。"""
import contextlib
import importlib.util
import io
import socket
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "board"))
sys.path.insert(0, str(REPO / "clients" / "python"))
from g3_caps import EXPECTED_CAPS, validate_caps

PROBE = REPO / "tools" / "board" / "g3_wait_ready.py"
NETWORK_TOOLS = (
    "g3_wait_ready.py",
    "g3_recovery_probe.py",
    "g3_netfault_probe.py",
    "g3_config_guard_probe.py",
    "g3_overhead_sweep.py",
    "g3_performance_matrix.py",
)


spec = importlib.util.spec_from_file_location("g3_wait_ready", PROBE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class CapsContractTests(unittest.TestCase):
    def test_accepts_exact_se150_caps(self):
        validate_caps(EXPECTED_CAPS)

    def test_every_caps_field_is_checked(self):
        for field, expected in EXPECTED_CAPS.items():
            with self.subTest(field=field):
                wrong = dict(EXPECTED_CAPS)
                wrong[field] = expected + 1
                with self.assertRaisesRegex(ValueError, field if field != "features" else "features"):
                    validate_caps(wrong)

    def test_wait_probe_prints_p4_p16_boundary(self):
        class FakeSocket:
            def settimeout(self, _seconds): pass
            def close(self): pass

        fake_caps = SimpleNamespace(**EXPECTED_CAPS)
        output = io.StringIO()
        with patch.object(probe.socket, "create_connection", return_value=FakeSocket()), \
             patch.object(probe.pr, "query_caps", return_value=fake_caps), \
             patch.object(probe.time, "sleep"), \
             contextlib.redirect_stdout(output):
            result = probe.main(["--ip", "127.0.0.1", "--deadline", "1", "--interval", "0.01", "--settle", "0"])
        self.assertEqual(result, 0, output.getvalue())
        self.assertIn("CAPS 全字段匹配", output.getvalue())
        self.assertIn("CAPS 不含 P_WAYS/PIPE_TREE", output.getvalue())
        self.assertIn("READY ", output.getvalue())

    def test_network_probes_require_explicit_ip(self):
        for name in NETWORK_TOOLS:
            with self.subTest(tool=name):
                result = subprocess.run(
                    [sys.executable, str(REPO / "tools" / "board" / name)],
                    capture_output=True, text=True, timeout=5,
                )
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("--ip", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
