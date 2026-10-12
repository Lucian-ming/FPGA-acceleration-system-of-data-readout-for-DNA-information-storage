"""CAPS 几何验收规则。TCP CAPS 不携带 Stage1 P_WAYS/PIPE_TREE。"""
from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

EXPECTED_CAPS = {
    "version": 1,
    "read_bps": 150,
    "num_lc": 50,
    "stride": 807,
    "max_symbols": 40500,
    "max_reads": 129600,
    "features": 1,
}

CAPS_ARCHITECTURE_BOUNDARY = (
    "CAPS 不含 P_WAYS/PIPE_TREE，TCP 层无法区分板上运行的是 P4 还是 P16。"
)


def validate_caps(caps) -> None:
    """要求当前 SE150 新板契约的完整 CAPS 字段逐项匹配。"""
    mismatches = []
    for name, expected in EXPECTED_CAPS.items():
        actual = caps.get(name) if isinstance(caps, dict) else getattr(caps, name, None)
        if actual != expected:
            label = "features bit0/保留位" if name == "features" else name
            mismatches.append(f"{label}: 期望 {expected}，实得 {actual}")
    if mismatches:
        raise ValueError("CAPS 几何不符: " + "; ".join(mismatches))


def query_board_caps(ip: str, port: int, *, timeout: float = 8.0, settle: float = 2.0):
    """连接并校验一次 CAPS；关闭后留 settle 时间释放板端单连接状态。"""
    repo = Path(__file__).resolve().parents[2]
    clients = str(repo / "clients" / "python")
    if clients not in sys.path:
        sys.path.insert(0, clients)
    import protocol as pr

    sock = socket.create_connection((ip, port), timeout=timeout)
    try:
        sock.settimeout(timeout)
        caps = pr.query_caps(sock, pr.NetStats())
        validate_caps(caps)
    finally:
        sock.close()
    if settle > 0:
        time.sleep(settle)
    return caps
