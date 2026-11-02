#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""板端「应用层就绪」探针：连上去做一次完整的 CAPS 握手，成功才算就绪。

为什么需要它（2026-09-03 实测，2/2 复现）
----------------------------------------
烧录完成（xsdb 打出 `BOOT> running`）之后**紧接着**下发任务必然失败：

    ConnectionError: 连接在接收完整数据前关闭
      clients/python/protocol.py:76 recv_exact ← query_caps

失败点固定在 `query_caps`：TCP `connect()` 成功、CAPS 请求发得出去，
但读应答时对端已把连接关掉，first.py 非零退出，`run_g3.sh` 第一轮直接 FAIL。
同一份制品**不重烧**、隔几十秒再跑一次就一次通过（图片哈希逐位相同）。

原来的就绪判据是裸 TCP 连通性（`echo > /dev/tcp/IP/7`）—— 它只能证明
**传输层**有人应答，证明不了**应用层**能不能回包。本探针把判据抬到应用层：
必须收到合法的 `PKT_CAPS_INFO`（0x16）应答才算就绪。实测烧录后约 7 s 才通过，
而裸连通性在那之前就已经"成功"了 —— 这个差就是所有假失败的来源。

就绪还要求 CAPS 全字段匹配 SE150：v1、150 bp、50 LC、stride 807、40500 symbols、
129600 reads、features bit0=1。CAPS **不包含 P_WAYS/PIPE_TREE**；TCP 探针无法区分
板上运行 P4 还是 P16，架构归属必须靠本轮制品/下载证据建立。

用法：
    python3 tools/board/g3_wait_ready.py --ip 192.168.1.10 --port 7 --deadline 90
退出码 0 = 已就绪（stdout 最后一行是 `READY <秒数> <尝试次数>`）；1 = 超时未就绪。
"""

from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "clients" / "python"))
import protocol as pr  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ip", required=True, help="必须显式指定本轮实测板端 IP")
    ap.add_argument("--port", type=int, default=7)
    ap.add_argument("--deadline", type=float, default=90.0, help="最多等多少秒")
    ap.add_argument("--interval", type=float, default=2.0, help="两次尝试之间等多久")
    ap.add_argument("--settle", type=float, default=2.0,
                    help="握手成功后再等多久才返回（让板端把探针这条连接的关闭处理完）")
    args = ap.parse_args(argv)

    t0 = time.time()
    attempt = 0
    while time.time() - t0 < args.deadline:
        attempt += 1
        elapsed = time.time() - t0
        sock = None
        try:
            sock = socket.create_connection((args.ip, args.port), timeout=5)
            sock.settimeout(8)
            caps = pr.query_caps(sock, pr.NetStats())
            from g3_caps import CAPS_ARCHITECTURE_BOUNDARY, validate_caps
            validate_caps(caps)
            sock.close()
            print(f"[{elapsed:6.1f}s] 第 {attempt} 次：CAPS 全字段匹配 "
                  f"version={caps.version} read_bps={caps.read_bps} num_lc={caps.num_lc} "
                  f"stride={caps.stride} max_symbols={caps.max_symbols} "
                  f"max_reads={caps.max_reads} features=0x{caps.features:X}")
            print(f"PROFILE_BOUNDARY {CAPS_ARCHITECTURE_BOUNDARY}")
            # 探针自己也占了一条连接。板端 g_conn 是单例，连接关闭的处理要占一个
            # tcp 回调周期，所以握手成功后再让一会儿，别把任务的连接挤在它头上。
            time.sleep(args.settle)
            print(f"READY {time.time() - t0:.1f} {attempt}")
            return 0
        except Exception as exc:  # noqa: BLE001 —— 探针要吞掉所有连接期异常继续重试
            print(f"[{elapsed:6.1f}s] 第 {attempt} 次：{type(exc).__name__}: {exc}")
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        time.sleep(args.interval)

    print(f"NOT_READY {args.deadline:.0f}s 内板端始终没有正常应答 CAPS")
    return 1


if __name__ == "__main__":
    sys.exit(main())
