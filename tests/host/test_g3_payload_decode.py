"""G3 任意载荷字节截断与命令行透传的离线判据。"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "clients" / "python"))
from native_ldpc import (  # noqa: E402
    K_INFO,
    bits_to_jpeg_bytes,
    bits_to_payload_bytes,
    validate_input_bytes,
)


class PayloadDecodeTests(unittest.TestCase):
    def test_explicit_length_ignores_embedded_jpeg_eoi(self):
        payload = b"CSV\xff\xd9tail"
        info = np.zeros(K_INFO, dtype=np.uint8)
        packed = np.unpackbits(np.frombuffer(payload, dtype=np.uint8))
        info[:packed.size] = packed

        self.assertEqual(bits_to_payload_bytes(info, input_bytes=len(payload)), payload)
        self.assertEqual(bits_to_jpeg_bytes(info), b"CSV\xff\xd9")
        self.assertEqual(bits_to_payload_bytes(info), bits_to_jpeg_bytes(info))

    def test_explicit_length_removes_only_zero_padding(self):
        payload = b"plain binary payload"
        info = np.zeros(K_INFO, dtype=np.uint8)
        info[:len(payload) * 8] = np.unpackbits(np.frombuffer(payload, dtype=np.uint8))
        self.assertEqual(len(bits_to_jpeg_bytes(info)), K_INFO // 8)
        self.assertEqual(bits_to_payload_bytes(info, input_bytes=len(payload)), payload)

    def test_input_length_boundaries(self):
        self.assertEqual(validate_input_bytes(6750, K_INFO), 6750)
        for invalid in (0, -1, 6751):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "input_bytes"):
                validate_input_bytes(invalid, K_INFO)
        with self.assertRaisesRegex(ValueError, "只有 16 bit"):
            bits_to_payload_bytes(np.zeros(16, dtype=np.uint8), input_bytes=3)

    def test_cli_writes_raw_payload(self):
        with tempfile.TemporaryDirectory(prefix="g3-payload-") as temp:
            root = Path(temp)
            rx = root / "zero-codeword.txt"
            out = root / "payload.bin"
            rx.write_text("0" * 64800, encoding="ascii")
            result = subprocess.run(
                [sys.executable, str(REPO / "tools/ldpc_decode.py"), "decode", str(rx),
                 "--output", str(root / "decoded.txt"), "--payload", str(out),
                 "--input-bytes", "12"],
                cwd=REPO, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(out.read_bytes(), bytes(12))
            self.assertIn("原始载荷已写入", result.stdout)

    def test_cli_rejects_invalid_or_incomplete_payload_options(self):
        common = [sys.executable, str(REPO / "tools/ldpc_decode.py"), "decode", "unused.txt"]
        cases = (
            (["--payload", "x"], "必须同时指定 --input-bytes"),
            (["--input-bytes", "6751", "--payload", "x"], "1..6750"),
            (["--input-bytes", "3"], "只用于 --payload"),
        )
        for options, expected in cases:
            with self.subTest(options=options):
                result = subprocess.run(common + options, cwd=REPO, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn(expected, result.stderr)

    def test_g3_plan_accepts_and_rejects_input_byte_count_without_board_access(self):
        base = ["bash", "tools/run_g3.sh", "--plan-only", "--skip-boot", "--skip-dump", "--no-uart"]
        accepted = subprocess.run(base + ["--input-bytes", "3862"], cwd=REPO,
                                  capture_output=True, text=True)
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
        self.assertIn("原始字节截断（3862 B）", accepted.stdout)

        rejected = subprocess.run(base + ["--input-bytes", "6751"], cwd=REPO,
                                  capture_output=True, text=True)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("--input-bytes 必须为 1..6750", rejected.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
