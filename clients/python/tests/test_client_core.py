#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上位机任务模型、协议与批处理的离线单元测试。"""

from __future__ import annotations

import hashlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[3]
CLIENT = REPO / "clients" / "python"
sys.path.insert(0, str(CLIENT))

import first  # noqa: E402
import ldpc_pipeline  # noqa: E402
import protocol  # noqa: E402
import task_protocol  # noqa: E402
from task_protocol import TaskCaps, TaskSpec  # noqa: E402


class FakeSocket:
    def __init__(self, incoming: bytes = b"", chunk: int = 3) -> None:
        self.incoming = bytearray(incoming)
        self.chunk = chunk
        self.sent = bytearray()
        self.timeout = None

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def recv(self, size: int) -> bytes:
        if not self.incoming:
            return b""
        count = min(size, self.chunk, len(self.incoming))
        result = bytes(self.incoming[:count])
        del self.incoming[:count]
        return result

    def sendall(self, data: bytes) -> None:
        self.sent.extend(data)


class TaskProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task = TaskSpec.from_watermark_bits(
            81_000, total_reads=4_096, score_min=67
        )

    def test_r083_geometry_and_config_crc(self) -> None:
        self.assertEqual((self.task.symbols, self.task.stride), (40_500, 807))
        payload = self.task.config_payload()
        self.assertEqual(len(payload), 44)
        self.assertEqual(struct.unpack(">I", payload[-4:])[0], 0xD5BC6633)

    def test_caps_round_trip_and_validation(self) -> None:
        payload = struct.pack(
            ">BBHIIIII", 1, 150, 0, 50, 807, 40_500, 107_968, 1
        )
        caps = TaskCaps.from_payload(payload)
        self.task.validate_caps(caps)
        self.assertEqual(caps.max_reads, 107_968)

    def test_invalid_geometry_and_bounds_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            TaskSpec.from_watermark_bits(81_001, total_reads=4_096, score_min=67)
        with self.assertRaises(ValueError):
            TaskSpec.from_watermark_bits(81_000, total_reads=100, score_min=67)
        with self.assertRaises(ValueError):
            TaskSpec.from_watermark_bits(81_000, total_reads=4_096, score_min=1_024)

    def test_client_count_limits_never_silently_truncate(self) -> None:
        with self.assertRaisesRegex(ValueError, "超过客户端上限"):
            first.ClientConfig().resolve_total(200_000)
        with self.assertRaisesRegex(ValueError, "--limit"):
            first.ClientConfig(send_limit=0).resolve_total(10)


class WatermarkAndBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task = TaskSpec.from_watermark_bits(
            81_000, total_reads=4_096, score_min=67
        )

    def test_watermark_pack_matches_golden_and_padding(self) -> None:
        golden = (REPO / "tests/golden/watermark_packed.bin").read_bytes()
        # data/R0.83_data 是不入 Git 的只读原始数据。这里从已受
        # SHA256SUMS 保护的打包黄金向量还原文本输入，既覆盖文本解析，
        # 又保证干净 clone 的主机回归不依赖本机私有数据目录。
        text_bits = "".join(
            "01"[(byte >> bit) & 1]
            for byte in golden
            for bit in range(8)
        )
        with tempfile.TemporaryDirectory() as directory:
            watermark = Path(directory) / "watermark.txt"
            watermark.write_text(text_bits + "\n", encoding="utf-8")
            bits = first.load_watermark_bits(watermark)
        payload = first.pack_watermark_bits(bits, self.task)
        self.assertEqual(payload[:len(golden)], golden)
        self.assertEqual(payload[len(golden):], b"\x00" * 3)

    def test_watermark_never_truncates(self) -> None:
        with self.assertRaises(ValueError):
            first.pack_watermark_bits("0" * 81_001, self.task)
        with self.assertRaises(ValueError):
            first.parse_watermark_text("0101x")

    def test_batches_have_exact_count_and_zero_padding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            reads = Path(directory) / "reads.txt"
            reads.write_text("A" * 150 + "\n" + "C" * 150 + "\n", encoding="utf-8")
            payloads = list(first.iter_read_batches(
                reads, 2, 64, batch_size=10, format_type="plain", orient="both"
            ))
        counts = [struct.unpack(">I", payload[:4])[0] for payload in payloads]
        self.assertEqual(sum(counts), 64)
        records = b"".join(payload[4:] for payload in payloads)
        self.assertNotEqual(records[:4 * first.READ_SIZE_BYTES], b"\x00" * (4 * first.READ_SIZE_BYTES))
        self.assertEqual(records[4 * first.READ_SIZE_BYTES:], b"\x00" * (60 * first.READ_SIZE_BYTES))

    def test_short_file_raises_instead_of_silent_padding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            reads = Path(directory) / "reads.txt"
            reads.write_text("A" * 150 + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "提前结束"):
                list(first.iter_read_batches(
                    reads, 2, 64, batch_size=100, format_type="plain", orient="forward"
                ))


class NetworkProtocolTests(unittest.TestCase):
    def test_packet_round_trip_with_fragmented_socket(self) -> None:
        packet = protocol.make_packet(protocol.PKT_CAPS_INFO, b"abc")
        sock = FakeSocket(packet, chunk=2)
        stats = protocol.NetStats()
        packet_type, payload = protocol.recv_packet(sock, stats)
        self.assertEqual((packet_type, payload), (protocol.PKT_CAPS_INFO, b"abc"))
        self.assertEqual(stats.download, len(packet))

    def test_error_ack_is_diagnostic(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "PKT_ERROR"):
            protocol.expect_ack(
                FakeSocket(bytes([protocol.PKT_ERROR])),
                protocol.NetStats(),
                protocol.PKT_WM_OK,
                operation="水印上传",
            )

    def test_query_caps_and_send_config(self) -> None:
        caps_payload = struct.pack(
            ">BBHIIIII", 1, 150, 0, 50, 807, 40_500, 107_968, 1
        )
        caps_sock = FakeSocket(protocol.make_packet(protocol.PKT_CAPS_INFO, caps_payload))
        caps = protocol.query_caps(caps_sock, protocol.NetStats())
        self.assertEqual(caps.stride, 807)
        self.assertEqual(bytes(caps_sock.sent), protocol.make_packet(protocol.PKT_CAPS))

        task = TaskSpec.from_watermark_bits(81_000, total_reads=4_096, score_min=67)
        config_sock = FakeSocket(
            protocol.make_packet(protocol.PKT_CONFIG_OK, struct.pack(">I", 0))
        )
        protocol.send_config(config_sock, protocol.NetStats(), task)
        self.assertEqual(config_sock.sent[2], protocol.PKT_CONFIG)


class LDPCBackendTests(unittest.TestCase):
    def test_auto_selects_native_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "result.txt"
            source.write_text("0" * 64_800, encoding="utf-8")
            expected = ldpc_pipeline.LDPCResult(
                source, root / "dec_input.txt", root / "decoded_bits.txt",
                root / "decoded_image.jpg", "native"
            )
            with mock.patch.object(ldpc_pipeline, "_run_native", return_value=expected) as native, \
                    mock.patch.object(ldpc_pipeline, "_run_external") as external:
                result = ldpc_pipeline.run_ldpc_decoder(
                    source, output_dir=root, backend="auto"
                )
        self.assertEqual(result.backend, "native")
        native.assert_called_once()
        external.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class SE250GeometryTests(unittest.TestCase):
    """SE250（64,800 条 × 250 bp）的主机侧支持。

    判据纪律（AGENTS.md）：SE150 与 SE250 最终产出**同一个图片哈希**
    `fcd0cf90…f2c3`（docs/20 §2 实跑证明），所以哈希分不出用的是哪套几何。
    这里的判据全部盯在**几何本身**上——线上字节数、阈值、stride、能力协商——
    因为那才是两套路径唯一能被区分的地方。
    """

    GOLDEN_SE250 = REPO / "tests" / "golden" / "se250"
    SE250_FASTQ = (REPO / "data" / "R0.83_data" / "Sequencing data"
                   / "DNA-40.5Kb-MC-SE250.fastq")

    def test_wire_size_and_threshold_follow_read_bps(self) -> None:
        # 40 B / 64 B 都是「ceil(2*rb/8) 再对齐到 4 B」的结果，不是两个魔数：
        # SE250 的 63 B 有效载荷必须补到 64 B，因为 AXIS 是 32 bit。
        self.assertEqual(task_protocol.read_size_bytes(150), 40)
        self.assertEqual(task_protocol.read_size_bytes(250), 64)
        self.assertEqual(task_protocol.default_score_min(150), 67)
        self.assertEqual(task_protocol.default_score_min(250), 112)

    def test_se250_task_geometry_and_config_crc(self) -> None:
        task = TaskSpec.from_watermark_bits(
            81_000, total_reads=4_096, score_min=112, read_bps=250
        )
        # stride 是反解出来的：(40500-250)/50 = 805，REF_LEN = 805+250 = 1055。
        self.assertEqual((task.symbols, task.stride, task.read_bps), (40_500, 805, 250))
        self.assertEqual(task.read_size_bytes, 64)
        payload = task.config_payload()
        self.assertEqual(len(payload), 44)
        # 钉死 CRC：SE250 的 CONFIG 与 SE150 的 0xD5BC6633 必须是不同的两串字节。
        self.assertEqual(struct.unpack(">I", payload[-4:])[0], 0x28E2B962)

    def test_unsupported_read_bps_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "read_bps"):
            TaskSpec.from_watermark_bits(
                81_000, total_reads=4_096, score_min=67, read_bps=200
            )

    def test_mixing_se150_and_se250_is_refused_at_caps(self) -> None:
        """「SE150 与 SE250 不可混用」在主机侧的闸门。

        板端的强制点是 PKT_CONFIG 拒绝码 2（`task_config.h:113-114`，至今未在
        板上验证，见 docs/20 阶段 S5 的反向判据）。这条测的是客户端在连上去
        之前就该拦住，免得把 64 B 记录喂给只认 40 B 的比特流。
        """
        se150_caps = TaskCaps(1, 150, 50, 807, 40_500, 107_968, 1)
        se250_caps = TaskCaps(1, 250, 50, 805, 40_500, 107_968, 1)
        se250_task = TaskSpec.from_watermark_bits(
            81_000, total_reads=4_096, score_min=112, read_bps=250)
        se150_task = TaskSpec.from_watermark_bits(
            81_000, total_reads=4_096, score_min=67, read_bps=150)
        with self.assertRaisesRegex(ValueError, "150bp"):
            se250_task.validate_caps(se150_caps)
        with self.assertRaisesRegex(ValueError, "250bp"):
            se150_task.validate_caps(se250_caps)
        # 同一套几何必须放行，否则这条判据只会「永远红」而没有信息量。
        se250_task.validate_caps(se250_caps)
        se150_task.validate_caps(se150_caps)

    def test_se250_encoding_bit_positions(self) -> None:
        """位平面 + 字节内 LSB-first 在 250 bp 下的落点（手推，不依赖实现）。

        序列 = 249 个 A + 1 个 C。A=00 不置位；C=11 置两位：
          高位平面 bit 249  → 字节 249>>3=31，位 249&7=1 → 0x02
          低位平面 bit 250+249=499 → 字节 62，位 3 → 0x08
        末字节 63 是 4 B 对齐的补零，必须为 0。
        """
        encoded = first.seq_to_read_bytes("A" * 249 + "C", 250)
        self.assertEqual(len(encoded), 64)
        self.assertEqual([(i, v) for i, v in enumerate(encoded) if v],
                         [(31, 0x02), (62, 0x08)])
        self.assertEqual(encoded[63], 0)

    def test_se250_read_is_not_truncated_to_150(self) -> None:
        """read_bps 写死成 150 时，250 bp 读段会被静默砍掉 100 个碱基。"""
        seq = "C" * 250
        se250 = first.seq_to_read_bytes(seq, 250)
        se150 = first.seq_to_read_bytes(seq, 150)
        self.assertEqual(len(se250), 64)
        self.assertEqual(len(se150), 40)
        # 高位平面：SE250 有 250 个 1，SE150 只剩 150 个。
        self.assertEqual(sum(bin(b).count("1") for b in se250), 500)
        self.assertEqual(sum(bin(b).count("1") for b in se150), 300)

    def test_se250_batches_pad_with_64_byte_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            reads = Path(directory) / "reads.txt"
            reads.write_text("A" * 250 + "\n" + "C" * 250 + "\n", encoding="utf-8")
            payloads = list(first.iter_read_batches(
                reads, 2, 64, batch_size=10, format_type="plain",
                orient="both", read_bps=250,
            ))
        counts = [struct.unpack(">I", payload[:4])[0] for payload in payloads]
        self.assertEqual(sum(counts), 64)
        records = b"".join(payload[4:] for payload in payloads)
        self.assertEqual(len(records), 64 * 64)          # 64 条 × 64 B
        self.assertEqual(records[4 * 64:], b"\x00" * (60 * 64))

    def test_se250_golden_manifest_records_the_geometry(self) -> None:
        """黄金向量目录必须自带几何清单——哈希守不住「用的哪套几何」。"""
        manifest = self.GOLDEN_SE250 / "GEOMETRY.txt"
        self.assertTrue(manifest.exists(), "缺少 tests/golden/se250/GEOMETRY.txt")
        fields = dict(
            (k.strip(), v.strip())
            for k, _, v in (line.partition("=") for line in
                            manifest.read_text(encoding="utf-8").splitlines())
            if k.strip() and not k.startswith("#")
        )
        self.assertEqual(fields["read_bps"], "250")
        self.assertEqual(fields["stride"], "805")
        self.assertEqual(fields["ref_len"], "1055")
        self.assertEqual(fields["read_wire_bytes"], "64")
        self.assertEqual(fields["record_bytes"], "72")
        self.assertEqual(fields["score_min"], "112")
        self.assertEqual(fields["wm_regions_rows"], "52750")
        rows = len((self.GOLDEN_SE250 / "wm_regions.hex").read_text().splitlines())
        self.assertEqual(rows, 50 * 1055)

    def test_se250_golden_is_not_the_se150_watermark_layout(self) -> None:
        """撞上 SE150 那份就是「几何没生效」的特征签名（docs/20 §3.7 G1）。"""
        se150 = (REPO / "tests" / "golden" / "wm_regions.hex").read_bytes()
        se250 = (self.GOLDEN_SE250 / "wm_regions.hex").read_bytes()
        self.assertNotEqual(
            hashlib.sha256(se150).hexdigest(), hashlib.sha256(se250).hexdigest())
        self.assertEqual(
            hashlib.sha256(se150).hexdigest(),
            "f352853912338cd0e0a1787445a341a0a74897948c048328903b2723bbdf7f5e",
            "SE150 的 wm_regions.hex 被改动了——它是其它所有判据的地基")

    @unittest.skipUnless(SE250_FASTQ.exists(),
                         "data/R0.83_data 不入 Git，无此原始数据时跳过")
    def test_client_encoding_matches_se250_golden_reads(self) -> None:
        """上位机的编码与黄金向量 reads.hex 逐字节一致（跨实现交叉核对）。

        `make_golden.py` 走 numpy 位平面打包，`first.py` 走逐碱基置位，
        两条独立实现必须给出同一串字节；黄金那份是 63 B（不含 AXIS 对齐补零），
        所以比的是客户端 64 B 里的前 63 B。
        """
        golden = (self.GOLDEN_SE250 / "reads.hex").read_text().splitlines()
        seqs = list(first.iter_source_seqs(self.SE250_FASTQ, 64, "fastq"))
        self.assertEqual(len(seqs), 64)
        for i, seq in enumerate(seqs):
            encoded = first.seq_to_read_bytes(seq, 250)
            self.assertEqual(encoded[:63].hex(), golden[i], f"第 {i} 条读段不一致")
            self.assertEqual(encoded[63], 0)
