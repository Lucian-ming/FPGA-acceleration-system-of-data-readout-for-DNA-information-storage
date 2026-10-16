"""G3 任意载荷字节截断与命令行透传的离线判据。"""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "clients" / "python"))
from native_ldpc import (  # noqa: E402
    K_INFO,
    bits_to_jpeg_bytes,
    bits_to_payload_bytes,
    infer_payload,
    validate_input_bytes,
)


def _info_bits_for_payload(payload):
    info = np.zeros(K_INFO, dtype=np.uint8)
    payload_bits = np.unpackbits(np.frombuffer(payload, dtype=np.uint8))
    info[:payload_bits.size] = payload_bits
    return info


def _write_synthetic_g3_artifact_bundle(root):
    params = {
        "READ_BPS": 150,
        "NUM_LC": 50,
        "STRIDE": 807,
        "REF_LEN": 957,
        "BATCH": 64,
        "C_STAGE1_P_WAYS": 16,
        "C_STAGE1_PIPE_TREE": 1,
    }
    part = "xc7z020clg400-2"
    artifacts = {
        "bit": "top_bd_wrapper.bit",
        "xsa": "dna_accel.xsa",
        "elf": "dna_lwip_app_b27.elf",
        "fsbl": "fsbl.elf",
        "boot": "BOOT.bin",
    }
    bit = b"fixture-bit-only"
    for key, name in artifacts.items():
        if key != "xsa":
            (root / name).write_bytes(bit if key == "bit" else b"fixture-" + key.encode())

    xsa_info = {
        "devices": [{"part": {"name": part}}],
        "files": [{"name": "inside.bit", "type": "FULL_BIT"}],
        "generatedVersion": "2026.1",
    }
    hwh_params = "".join(
        f'<PARAMETER NAME="{name}" VALUE="{value}"/>'
        for name, value in params.items()
    )
    hwh = (
        '<EDKSYSTEM><SYSTEMINFO DEVICE="7z020" PACKAGE="clg400" SPEEDGRADE="-2"/>'
        '<MODULE MODTYPE="Dna_accelerator_core"><PARAMETERS>'
        f"{hwh_params}</PARAMETERS></MODULE></EDKSYSTEM>"
    )
    with zipfile.ZipFile(root / artifacts["xsa"], "w") as archive:
        archive.writestr("xsa.json", json.dumps(xsa_info))
        archive.writestr("ps7_init.tcl", "fixture-init")
        archive.writestr("inside.bit", bit)
        archive.writestr("system.hwh", hwh)

    source_manifest = root / "source_manifest.json"
    source_manifest.write_text(
        json.dumps({"files": {"hw/scripts/bd.tcl": "a" * 64}}), encoding="utf-8"
    )
    manifest = {
        "schema_version": 1,
        "board_id": "bkb220",
        "part": part,
        "parameters": params,
        "artifacts": artifacts,
        "tool_versions": {"vivado": "2026.1", "vitis": "2026.1"},
        "source_manifest": {
            "path": source_manifest.name,
            "sha256": hashlib.sha256(source_manifest.read_bytes()).hexdigest(),
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    sums = []
    for path in sorted(root.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            sums.append(f"{digest}  {path.name}\n")
    (root / "SHA256SUMS").write_text("".join(sums), encoding="utf-8")


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

    def test_infer_jpeg_uses_eoi_and_reports_certain_length(self):
        payload = b"\xff\xd8\xff\xe0jpeg payload\xff\xd9"
        guess = infer_payload(_info_bits_for_payload(payload))
        self.assertEqual(guess.media_type, "image/jpeg")
        self.assertEqual(guess.extension, ".jpg")
        self.assertIs(guess.length_certain, True)
        self.assertEqual(len(guess.data), len(payload))
        self.assertEqual(guess.data, payload)

    def test_infer_utf8_text_removes_zero_padding(self):
        payload = "DNA 读出结果\n".encode("utf-8")
        guess = infer_payload(_info_bits_for_payload(payload))
        self.assertEqual(guess.media_type, "text/plain; charset=utf-8")
        self.assertEqual(guess.extension, ".txt")
        self.assertFalse(guess.length_certain)
        self.assertEqual(guess.data, payload)

    def test_infer_random_binary_keeps_uncertain_length(self):
        payload = bytes.fromhex("ff00817fa4")
        guess = infer_payload(_info_bits_for_payload(payload))
        self.assertEqual(guess.media_type, "application/octet-stream")
        self.assertEqual(guess.extension, ".bin")
        self.assertFalse(guess.length_certain)
        self.assertEqual(guess.data, payload)

    def test_infer_payload_preserves_legacy_jpeg_default(self):
        payload = b"\xff\xd8\xff\xe0embedded\xff\xd9trailing"
        info = _info_bits_for_payload(payload)
        self.assertEqual(bits_to_payload_bytes(info, None), bits_to_jpeg_bytes(info))

    def test_infer_payload_marks_trailing_zero_ambiguity(self):
        payload = b"\xff\x80\x01\0"
        guess = infer_payload(_info_bits_for_payload(payload))
        self.assertEqual(guess.extension, ".bin")
        self.assertFalse(guess.length_certain)
        self.assertEqual(guess.data, payload[:-1])

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
        with tempfile.TemporaryDirectory(prefix="g3-plan-payload-") as temp:
            artifact_dir = Path(temp) / "artifacts"
            artifact_dir.mkdir()
            _write_synthetic_g3_artifact_bundle(artifact_dir)
            base = ["bash", "tools/run_g3.sh", "--artifact-dir", str(artifact_dir),
                    "--plan-only", "--skip-boot", "--skip-dump", "--no-uart"]
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
