#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上位机任务模型、协议与批处理的离线单元测试。"""

from __future__ import annotations

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
        bits = first.load_watermark_bits(
            REPO / "data/R0.83_data/Source data/Watermark sequences/r0.83_watermark.txt"
        )
        payload = first.pack_watermark_bits(bits, self.task)
        golden = (REPO / "tests/golden/watermark_packed.bin").read_bytes()
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
