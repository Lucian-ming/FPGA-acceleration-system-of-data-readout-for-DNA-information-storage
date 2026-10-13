#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/profile_upload.py —— 上位机「读段上传」段的时间去向拆解（只读，不触板）。

`first.py` 把 `stats.t_batches` 报成一个数（全量档 3.94 s），但那段里其实混了
**三件性质完全不同的事**，优化手段也完全不同：

  1. **客户端预处理**：`fast_iter_read_batches` 在**第一次 next() 时**就一次性读完整份
     FASTQ、做 2-bit 位平面打包、生成正反向记录、再切批。这部分是纯 CPU，与网络无关，
     可以提前算、也可以与上一轮重叠。
  2. **TCP 发送**：把 40 KB/批的负载写进 socket。
  3. **逐批 ACK 停等**：每批发完都要等板端回一个字节，RTT 串行叠加。

本工具把这三段分开计时，并额外提供 `--loopback` 模式：用本机回环跑同一个协议，
（本机 ACK 几乎瞬时）用于把「客户端 + 协议栈」的开销与「板端真实响应」区分开。

**边界**：
- 本工具**不触板、不烧录、不占串口**，`--loopback` 也只在本机回环上跑。
- 回环数字**不能**代表板端：它只回答「客户端这侧最少要花多久」。
- 这里量的是**墙钟**，不是硬件周期；不产生任何板端周期数。

用法：
    python3 tools/profile_upload.py                          # 全量档，只测分段
    python3 tools/profile_upload.py --batch 20000            # 看批大小对 ACK 停等的影响
    python3 tools/profile_upload.py --loopback               # 本机回环对照
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
import sys
import threading
import time
from pathlib import Path
from time import perf_counter

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENT_DIR = REPO_ROOT / "clients" / "python"
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from fast_readout import fast_iter_read_batches  # noqa: E402
from protocol import (  # noqa: E402
    HDR_FMT, HDR_SZ, MAGIC, PKT_BATCH, PKT_BATCH_OK, PKT_CAPS,
)
from task_protocol import FRAME_READS, read_size_bytes  # noqa: E402

DEFAULT_READS = "data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE150.fastq"
DEFAULT_BATCH = 1000


def analyze_total_reads(path: Path) -> int:
    n = 0
    with path.open("rb") as fh:
        for line in fh:
            if not line:
                continue
            n += 1
    return n // 4


def time_generation(reads: Path, source_reads: int, send_total: int,
                    batch: int, orient: str, read_bps: int) -> dict:
    """分段：第一批之前的预处理 vs 之后的切批产出。"""
    per_read = 2 if orient == "both" else 1
    rec_sz = read_size_bytes(read_bps)

    gen = fast_iter_read_batches(reads, source_reads, send_total,
                                 batch_size=batch, orient=orient, read_bps=read_bps)
    t0 = perf_counter()
    first = next(gen)          # 触发一次性预处理（读文件 + 打包 + 切批）
    t_prep = perf_counter() - t0

    t0 = perf_counter()
    n_batches = 1
    total_bytes = len(first)
    for payload in gen:
        n_batches += 1
        total_bytes += len(payload)
    t_slice = perf_counter() - t0

    return {
        "batches": n_batches,
        "wire_bytes": total_bytes,
        "t_prep_s": t_prep,
        "t_slice_s": t_slice,
        "t_gen_s": t_prep + t_slice,
        "per_read": per_read,
        "rec_sz": rec_sz,
    }


def run_loopback(reads: Path, source_reads: int, send_total: int, batch: int,
                 orient: str, read_bps: int) -> dict:
    """本机回环上跑同一套「发一批 → 等 1 字节 ACK」的停等协议。"""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    ready = threading.Event()

    def server() -> None:
        conn, _ = srv.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        ready.set()
        buf = b""
        try:
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buf += chunk
                # 极简：每收到一个完整包就回一个 ACK 字节（回环上近似瞬时）
                while len(buf) >= HDR_SZ:
                    _magic, _ptype, _rsv, plen = struct.unpack(HDR_FMT, buf[:HDR_SZ])
                    need = HDR_SZ + plen
                    if len(buf) < need:
                        break
                    buf = buf[need:]
                    conn.sendall(bytes([PKT_BATCH_OK]))
        finally:
            conn.close()
            srv.close()

    th = threading.Thread(target=server, daemon=True)
    th.start()

    sock = socket.create_connection(("127.0.0.1", port))
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    ready.wait(2.0)

    def recv_one() -> None:
        got = 0
        while got < 1:
            chunk = sock.recv(1 - got)
            if not chunk:
                raise RuntimeError("回环服务端提前关闭")
            got += len(chunk)

    rtts = []
    t0 = perf_counter()
    n_batches = 0
    total_bytes = 0
    for payload in fast_iter_read_batches(reads, source_reads, send_total,
                                          batch_size=batch, orient=orient,
                                          read_bps=read_bps):
        pkt = struct.pack(HDR_FMT, MAGIC, PKT_BATCH, 0, len(payload)) + payload
        t_b = perf_counter()
        sock.sendall(pkt)
        recv_one()
        rtts.append(perf_counter() - t_b)
        n_batches += 1
        total_bytes += len(payload)
    t_total = perf_counter() - t0
    sock.close()
    th.join(timeout=2.0)

    rtts_sorted = sorted(rtts)
    return {
        "batches": n_batches,
        "wire_bytes": total_bytes,
        "t_total_s": t_total,
        "rtt_median_s": rtts_sorted[len(rtts_sorted) // 2] if rtts_sorted else 0.0,
        "rtt_min_s": rtts_sorted[0] if rtts_sorted else 0.0,
        "rtt_max_s": rtts_sorted[-1] if rtts_sorted else 0.0,
        "sum_rtt_s": sum(rtts),
    }


def probe_rtt(ip: str, port: int, n: int) -> dict:
    """量「一次小包往返」的板端 RTT：发 PKT_CAPS（8 B）→ 等 CAPS_INFO 应答。

    这是**没有窗口压力**的纯延迟：8 B 远小于任何接收窗口，所以它把
    「板端主循环多久才处理一次」与「TCP 接收窗口」两个因素**分开**了：
      - 若这个 RTT ≈ 1~2 ms，说明板端空闲主循环的 `usleep(1000)` 是延迟主项；
      - 若它只有几百 µs，则上传慢纯粹是接收窗口太小（WND/RTT 限速）。
    """
    samples = []
    with socket.create_connection((ip, port), timeout=10) as sock:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        for i in range(n):
            pkt = struct.pack(HDR_FMT, MAGIC, PKT_CAPS, 0, 0)
            t0 = perf_counter()
            sock.sendall(pkt)
            buf = b""
            while len(buf) < HDR_SZ:
                chunk = sock.recv(HDR_SZ - len(buf))
                if not chunk:
                    raise RuntimeError("板端在 CAPS 应答首部前关闭连接")
                buf += chunk
            _m, _t, _r, plen = struct.unpack(HDR_FMT, buf)
            got = 0
            while got < plen:
                chunk = sock.recv(plen - got)
                if not chunk:
                    raise RuntimeError("板端在 CAPS 应答负载中途关闭连接")
                got += len(chunk)
            samples.append(perf_counter() - t0)
    s = sorted(samples)
    return {
        "samples": n,
        "rtt_median_s": s[len(s) // 2],
        "rtt_min_s": s[0],
        "rtt_max_s": s[-1],
        "rtt_mean_s": sum(s) / len(s),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reads", default=DEFAULT_READS)
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    ap.add_argument("--orient", default="both", choices=["both", "forward"])
    ap.add_argument("--read-bps", type=int, default=150)
    ap.add_argument("--loopback", action="store_true",
                    help="额外在本机回环上跑同一停等协议做对照")
    ap.add_argument("--rtt-probe", metavar="IP:PORT", default=None,
                    help="只做板端小包 RTT 探针，不做生成/回环（例：192.168.1.10:7）")
    ap.add_argument("--rtt-samples", type=int, default=200)
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    if args.rtt_probe:
        host, _, p = args.rtt_probe.partition(":")
        rtt = probe_rtt(host, int(p or 7), args.rtt_samples)
        print(f"[板端小包 RTT 探针] {host}:{p or 7}，{rtt['samples']} 次 PKT_CAPS 往返")
        print(f"  中位 : {rtt['rtt_median_s'] * 1e3:.3f} ms")
        print(f"  最小 : {rtt['rtt_min_s'] * 1e3:.3f} ms")
        print(f"  最大 : {rtt['rtt_max_s'] * 1e3:.3f} ms")
        print(f"  均值 : {rtt['rtt_mean_s'] * 1e3:.3f} ms")
        if args.json_out:
            Path(args.json_out).write_text(json.dumps({"rtt_probe": rtt}, indent=1),
                                           encoding="utf-8")
            print(f"[留证] 已写 {args.json_out}")
        return 0

    reads = Path(args.reads)
    if not reads.exists():
        print(f"[ERR] 读段文件不存在：{reads}", file=sys.stderr)
        return 2

    source_reads = analyze_total_reads(reads)
    per_read = 2 if args.orient == "both" else 1
    send_total = ((source_reads * per_read + FRAME_READS - 1) // FRAME_READS) * FRAME_READS

    print(f"读段文件      : {reads}")
    print(f"源读段        : {source_reads} 条 → 发送 {send_total} 条记录"
          f"（{args.orient}，{read_size_bytes(args.read_bps)} B/条）")
    print(f"批大小        : {args.batch} 条/批")
    print()

    gen = time_generation(reads, source_reads, send_total, args.batch,
                          args.orient, args.read_bps)
    print("[客户端预处理 + 切批]（不触网）")
    print(f"  第一次 next() 前的预处理 : {gen['t_prep_s']:.3f} s"
          f"   ← 读文件 + 位平面打包 + 生成正反向 + 切批")
    print(f"  其余批次的切批产出       : {gen['t_slice_s']:.3f} s")
    print(f"  合计                     : {gen['t_gen_s']:.3f} s"
          f"（{gen['batches']} 批，{gen['wire_bytes']} B 负载）")
    print()

    result = {"generation": gen}

    if args.loopback:
        lb = run_loopback(reads, source_reads, send_total, args.batch,
                          args.orient, args.read_bps)
        result["loopback"] = lb
        print("[本机回环停等对照]（同一协议，本机 ACK）")
        print(f"  总耗时        : {lb['t_total_s']:.3f} s")
        print(f"  逐批 RTT 中位 : {lb['rtt_median_s'] * 1e3:.3f} ms"
              f"（min {lb['rtt_min_s'] * 1e3:.3f} / max {lb['rtt_max_s'] * 1e3:.3f}）")
        print(f"  RTT 合计      : {lb['sum_rtt_s']:.3f} s"
              f"（占回环总耗时 {100 * lb['sum_rtt_s'] / lb['t_total_s']:.1f}%）")
        print()

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(f"[留证] 已写 {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
