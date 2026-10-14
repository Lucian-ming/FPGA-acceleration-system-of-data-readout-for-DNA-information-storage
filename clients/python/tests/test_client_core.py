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
import fast_readout  # noqa: E402
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
            expected_c = ldpc_pipeline.LDPCResult(
                source, root / "dec_input.txt", root / "decoded_bits.txt",
                root / "decoded_image.jpg", "c_accel"
            )
            expected_native = ldpc_pipeline.LDPCResult(
                source, root / "dec_input.txt", root / "decoded_bits.txt",
                root / "decoded_image.jpg", "native"
            )
            # 1. 当 C 加速器存在时，auto 优先选用 c_accel
            with mock.patch.object(ldpc_pipeline, "is_c_accel_available", return_value=True), \
                    mock.patch.object(ldpc_pipeline, "_run_c_accel", return_value=expected_c) as run_c:
                res_c = ldpc_pipeline.run_ldpc_decoder(source, output_dir=root, backend="auto")
                self.assertEqual(res_c.backend, "c_accel")
                run_c.assert_called_once()

            # 2. 当 C 加速器缺失时，auto 优雅降级至 native
            with mock.patch.object(ldpc_pipeline, "is_c_accel_available", return_value=False), \
                    mock.patch.object(ldpc_pipeline, "_run_native", return_value=expected_native) as run_nat:
                res_nat = ldpc_pipeline.run_ldpc_decoder(source, output_dir=root, backend="auto")
                self.assertEqual(res_nat.backend, "native")
                run_nat.assert_called_once()


class ReadoutEquivalenceTests(unittest.TestCase):
    """比较 first.py 的逐读路径与 fast_readout 的向量化线上输出。"""

    SE150_FASTQ = (
        REPO / "data" / "R0.83_data" / "Sequencing data"
        / "DNA-40.5Kb-MC-SE150.fastq"
    )
    SEND_TOTAL = 64
    BATCH_SIZE = 13

    @staticmethod
    def _first_wire_bytes(
        path: Path,
        source_reads: int,
        *,
        format_type: str,
        orient: str,
        read_bps: int,
    ) -> bytes:
        """用 first.py 的逐读记录编码，按 PKT_BATCH 头部序列化线上字节。"""
        read_size = task_protocol.read_size_bytes(read_bps)
        records = list(first.iter_reads(
            path, source_reads, format_type, orient, read_bps
        ))[:ReadoutEquivalenceTests.SEND_TOTAL]
        records.extend(
            [b"\x00" * read_size]
            * (ReadoutEquivalenceTests.SEND_TOTAL - len(records))
        )

        packets = []
        offset = 0
        while offset < ReadoutEquivalenceTests.SEND_TOTAL:
            count = min(
                ReadoutEquivalenceTests.BATCH_SIZE,
                ReadoutEquivalenceTests.SEND_TOTAL - offset,
            )
            chunk = b"".join(records[offset : offset + count])
            packets.append(struct.pack(">I", count) + chunk)
            offset += count
        return b"".join(packets)

    def _assert_wire_matches(
        self,
        path: Path,
        source_reads: int,
        *,
        format_type: str,
        orient: str,
        read_bps: int,
        label: str,
    ) -> None:
        first_wire = self._first_wire_bytes(
            path,
            source_reads,
            format_type=format_type,
            orient=orient,
            read_bps=read_bps,
        )
        fast_wire = b"".join(fast_readout.fast_iter_read_batches(
            path,
            source_reads,
            self.SEND_TOTAL,
            batch_size=self.BATCH_SIZE,
            format_type=format_type,
            orient=orient,
            read_bps=read_bps,
        ))
        if first_wire != fast_wire:
            offset = next(
                (i for i, (left, right) in enumerate(zip(first_wire, fast_wire))
                 if left != right),
                min(len(first_wire), len(fast_wire)),
            )
            first_byte = first_wire[offset] if offset < len(first_wire) else None
            fast_byte = fast_wire[offset] if offset < len(fast_wire) else None
            self.fail(
                f"{label}: FAIL；首个不符的线上字节偏移={offset}，"
                f"first.py={first_byte!r}，fast_readout={fast_byte!r}，"
                f"长度分别为 {len(first_wire)} / {len(fast_wire)}"
            )

    @unittest.skipUnless(SE150_FASTQ.is_file(), "缺少真实 SE150 FASTQ 样本")
    def test_real_fastq_wire_bytes_match(self) -> None:
        """以仓库外置 R0.83 FASTQ 的前三条真实读段核对线上字节。"""
        self.assertEqual(
            len(list(first.iter_source_seqs(self.SE150_FASTQ, 3, "fastq"))), 3
        )
        self._assert_wire_matches(
            self.SE150_FASTQ,
            3,  # 3 条不是 4 的整数倍；both 后仍由 64 条线上帧补零
            format_type="fastq",
            orient="both",
            read_bps=150,
            label="R0.83 SE150 FASTQ / both",
        )

    def test_plain_n_mixed_case_both_orientations_and_two_lengths(self) -> None:
        """覆盖 plain、N、大小写、非 4 倍数，以及两种方向和读长。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = (
                ("plain150", 150, ["acgtn" * 30, "TgCaN" * 30, "N" * 150]),
                ("plain250", 250, ["aCGtn" * 50, "cGATn" * 50, "N" * 250]),
            )
            for stem, read_bps, seqs in cases:
                reads = root / f"{stem}.txt"
                reads.write_text("\n".join(seqs) + "\n", encoding="ascii")
                self.assertEqual(len(list(first.iter_source_seqs(
                    reads, 4, "plain"
                ))), 3)
                for orient in ("both", "forward"):
                    with self.subTest(read_bps=read_bps, orient=orient):
                        self._assert_wire_matches(
                            reads,
                            3,
                            format_type="plain",
                            orient=orient,
                            read_bps=read_bps,
                            label=f"plain SE{read_bps} / {orient}",
                        )

    def test_empty_and_single_record_inputs(self) -> None:
        """空文件不产生伪记录；单条极小批次仍逐字节等价。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            empty = root / "empty.fastq"
            empty.write_text("", encoding="ascii")
            self.assertEqual(list(first.iter_source_seqs(empty, 1, "fastq")), [])
            self.assertEqual(fast_readout.fast_iter_source_seqs(
                empty, 1, "fastq"
            ), [])
            # 请求一条而文件为空时两条生产批处理入口都必须拒绝，不能补成有效读段。
            for iterator in (first.iter_read_batches,
                             fast_readout.fast_iter_read_batches):
                with self.assertRaisesRegex(ValueError, "读段文件提前结束"):
                    list(iterator(
                        empty, 1, self.SEND_TOTAL, batch_size=self.BATCH_SIZE,
                        format_type="fastq", orient="forward", read_bps=150,
                    ))

            tiny = root / "tiny.fastq"
            sequence = "AcgTN" * 30
            tiny.write_text(
                f"@tiny\n{sequence}\n+\n{'I' * len(sequence)}\n",
                encoding="ascii",
            )
            self._assert_wire_matches(
                tiny,
                1,
                format_type="fastq",
                orient="forward",
                read_bps=150,
                label="one-record FASTQ / forward",
            )


class LDPCBackendCrossCheckTests(unittest.TestCase):
    """用仓库黄金输入实际运行可用后端并比较解码载荷 SHA-256。"""

    DEC_INPUT = REPO / "tests" / "golden" / "se250" / "dec_input.txt"
    RESOURCE_DIR = CLIENT / "resources"
    EXTERNAL_FILES = (
        "R5_6_LDPC_hard_decoder.exe",
        "libstdc++-6.dll",
        "libgcc_s_seh-1.dll",
        "libwinpthread-1.dll",
    )

    @staticmethod
    def _decoded_payload(path: Path) -> bytes:
        """将文本位串或 0/1 字节载荷规范化为逐位 ASCII 载荷。"""
        raw = path.read_bytes()
        text_chars = set(b"01 \t\r\n")
        if set(raw).issubset(text_chars):
            payload = bytes(value for value in raw if value in (ord("0"), ord("1")))
        elif set(raw).issubset({0, 1}):
            payload = bytes(value + ord("0") for value in raw)
        else:
            raise AssertionError(
                f"无法识别 {path} 的解码载荷格式（{len(raw)} bytes）"
            )
        if len(payload) != 54_000:
            raise AssertionError(
                f"{path} 应有 54,000 个解码位，实得 {len(payload)}"
            )
        return payload

    def _run_backend(self, backend: str, output_dir: Path) -> str:
        result = ldpc_pipeline.run_ldpc_decoder(
            self.DEC_INPUT,
            output_dir=output_dir,
            backend=backend,
        )
        self.assertEqual(result.backend, backend)
        payload = self._decoded_payload(result.decoded_bits_path)
        digest = hashlib.sha256(payload).hexdigest()
        print(
            f"PASS: LDPC backend={backend} payload_bits={len(payload)} "
            f"sha256={digest}"
        )
        return digest

    def test_native_backend_runs_on_golden_input(self) -> None:
        self.assertTrue(self.DEC_INPUT.is_file(), f"缺少 LDPC 黄金输入: {self.DEC_INPUT}")
        input_sha = hashlib.sha256(self.DEC_INPUT.read_bytes()).hexdigest()
        print(f"LDPC cross-check input={self.DEC_INPUT.name} sha256={input_sha}")
        with tempfile.TemporaryDirectory() as directory:
            self._run_backend("native", Path(directory) / "native")

    def test_c_accel_payload_sha_matches_native_when_library_exists(self) -> None:
        c_library = self.RESOURCE_DIR / "libc_ldpc.so"
        if not c_library.is_file():
            reason = f"缺少 {c_library}"
            print(f"SKIP: LDPC backend=c_accel：{reason}")
            self.skipTest(reason)

        self.assertTrue(
            ldpc_pipeline.is_c_accel_available(),
            "libc_ldpc.so 存在但 c_accel 无法加载，必须修复而不能跳过",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native_sha = self._run_backend("native", root / "native")
            c_sha = self._run_backend("c_accel", root / "c_accel")
        self.assertEqual(
            c_sha, native_sha,
            "真实 c_accel 与 native 解码载荷 SHA-256 不同",
        )

    def test_external_payload_sha_matches_native_when_runnable(self) -> None:
        missing = [
            name for name in self.EXTERNAL_FILES
            if not (self.RESOURCE_DIR / name).is_file()
        ]
        if missing:
            reason = "resources 不完整，缺少 " + ", ".join(missing)
            print(f"SKIP: LDPC backend=external：{reason}")
            self.skipTest(reason)
        if sys.platform != "win32":
            reason = (
                f"当前宿主为 {sys.platform}，resources 中是 Windows PE EXE；"
                "该执行环境不能直接启动此 EXE"
            )
            print(f"SKIP: LDPC backend=external：{reason}")
            self.skipTest(reason)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native_sha = self._run_backend("native", root / "native")
            external_sha = self._run_backend("external", root / "external")
        self.assertEqual(
            external_sha, native_sha,
            "真实 external 与 native 解码载荷 SHA-256 不同",
        )


class SE250GeometryTests(unittest.TestCase):
    """SE250（64,800 条 × 250 bp）的主机侧支持。

    判据纪律（AGENTS.md）：SE150 与 SE250 最终产出**同一个图片哈希**
    `fcd0cf90…f2c3`（docs/07 §2 实跑证明），所以哈希分不出用的是哪套几何。
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
        板上验证，见 docs/07 阶段 S5 的反向判据）。这条测的是客户端在连上去
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
        """撞上 SE150 那份就是「几何没生效」的特征签名（docs/07 §3.7 G1）。"""
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


class CLDPCAndAdaptivityTests(unittest.TestCase):
    GOLDEN_SE250 = REPO / "tests" / "golden" / "se250"
    SE150_FASTQ = REPO / "data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE150.fastq"
    SE250_FASTQ = REPO / "data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE250.fastq"

    def test_c_accel_availability_and_bit_exactness(self) -> None:
        """C 加速器必须可用且译码结果与黄金图片哈希 100% 逐位吻合。"""
        import c_ldpc
        self.assertTrue(c_ldpc.is_c_accel_available(), "libc_ldpc.so 应该存在且可被加载")

        pchk = CLIENT / "resources" / "dvb_s2_r5_6.pchk"
        perm = CLIENT / "resources" / "permutation64800"
        dec_input = self.GOLDEN_SE250 / "dec_input.txt"

        bits_str = ldpc_pipeline.read_bit_text(dec_input)
        import numpy as np
        rx = np.frombuffer(bits_str.encode("ascii"), dtype=np.uint8) - ord("0")

        info, failed, iters = c_ldpc.decode_bits_c(rx, pchk, perm)
        self.assertEqual(len(info), 54_000)
        self.assertEqual(failed, 141)
        self.assertEqual(iters, 45)

        jpeg = ldpc_pipeline.bits_to_jpeg_bytes(info)
        sha = hashlib.sha256(jpeg).hexdigest()
        self.assertEqual(
            sha,
            "fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3",
            "C 加速器译码图片哈希必须与 R0.83 黄金标准完全逐位相同",
        )

    def test_ldpc_pipeline_auto_selects_c_accel(self) -> None:
        """ldpc_pipeline 在 auto 模式下优先选用 c_accel。"""
        dec_input = self.GOLDEN_SE250 / "dec_input.txt"
        with tempfile.TemporaryDirectory() as tmpdir:
            res = ldpc_pipeline.run_ldpc_decoder(dec_input, output_dir=Path(tmpdir), backend="auto")
            self.assertEqual(res.backend, "c_accel")
            self.assertTrue(res.decoded_bits_path.is_file())
            self.assertTrue(res.image_path.is_file())

    @unittest.skipUnless(SE150_FASTQ.exists() and SE250_FASTQ.exists(), "缺少 data/R0.83_data 时跳过")
    def test_reads_adaptive_detection_and_estimation(self) -> None:
        """自适应探测必须精确识别 150bp 与 250bp 并给出匹配阈值与耗时模型。"""
        info150 = first.analyze_reads_file(self.SE150_FASTQ)
        self.assertEqual(info150.total_reads, 51_781)
        self.assertEqual(info150.detected_read_bps, 150)
        self.assertEqual(info150.suggested_score_min, 67)
        self.assertAlmostEqual(info150.estimated_seconds, 102.24, delta=0.5)

        info250 = first.analyze_reads_file(self.SE250_FASTQ)
        self.assertEqual(info250.total_reads, 64_800)
        self.assertEqual(info250.detected_read_bps, 250)
        self.assertEqual(info250.suggested_score_min, 112)
        self.assertAlmostEqual(info250.estimated_seconds, 126.70, delta=0.5)


if __name__ == "__main__":
    unittest.main()
