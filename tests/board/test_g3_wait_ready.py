#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`tools/board/g3_wait_ready.py`（B28 就绪探针）的离板判据。

为什么要有它
------------
探针现在是 `tools/run_g3.sh` 第 5 步的**硬门禁**：它红了就不下发任务。
门禁本身坏掉的代价是所有上板实验都被挡住（或者更糟——它恒绿，B28 照样漏过去），
而板子是稀缺资源，不该拿上板时间去验证一个纯主机侧的脚本。

判据必须「能失败」
------------------
本项目的判据纪律是：跑之前先问「如果缺陷真的存在，这条判据会变红吗」。
所以这里的核心用例是 B：**裸 TCP 全程可连、但应用层永远不回 CAPS**。
被替换掉的旧判据（`echo > /dev/tcp/IP/PORT`）在这个场景下**立刻就绿**——
那正是 B28 的成因。探针必须红。用例 B 绿了，探针就没有鉴别力，别的用例全过也没用。

用法：python3 tests/board/test_g3_wait_ready.py     退出码 0 = 全过
"""

from __future__ import annotations

import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PROBE = REPO / "tools" / "board" / "g3_wait_ready.py"
sys.path.insert(0, str(REPO / "clients" / "python"))
import protocol as pr  # noqa: E402
from task_protocol import TASK_PROTO_VERSION  # noqa: E402

# 一份合法的 CAPS_INFO 载荷：>BBHIIIII = version, read_bps, reserved, num_lc,
# stride, max_symbols, max_reads, features。取 SE150 的实际几何（docs/02）。
CAPS_PAYLOAD = struct.pack(">BBHIIIII", TASK_PROTO_VERSION, 150, 0, 807, 129, 4096, 103616, 0)


class FakeBoard:
    """假板子：`answer_after` 秒之前只接受连接就关掉（B28 的现象），之后正常应答 CAPS。

    `answer_after=None` = 永远不应答，只接受连接再关闭 —— 裸 TCP 判据眼里它一直是"就绪"的。
    """

    def __init__(self, answer_after: float | None):
        self.answer_after = answer_after
        self.t0 = time.time()
        self.conns = 0
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(8)
        self._srv.settimeout(0.3)
        self.port = self._srv.getsockname()[1]
        self._stop = threading.Event()
        self._th = threading.Thread(target=self._serve, daemon=True)
        self._th.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._srv.accept()
            except (socket.timeout, OSError):
                continue
            self.conns += 1
            ready = (self.answer_after is not None
                     and time.time() - self.t0 >= self.answer_after)
            try:
                if ready:
                    conn.settimeout(3)
                    # 把请求读掉再应答，走完 query_caps 的完整往返
                    conn.recv(pr.HDR_SZ)
                    conn.sendall(pr.make_packet(pr.PKT_CAPS_INFO, CAPS_PAYLOAD))
                    time.sleep(0.2)
                # 未就绪：什么都不发，直接关 —— recv_exact 那边就是"连接在接收完整数据前关闭"
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def close(self) -> None:
        self._stop.set()
        self._th.join(timeout=2)
        try:
            self._srv.close()
        except OSError:
            pass


def run_probe(port: int, deadline: float, interval: float = 0.5, settle: float = 0.2):
    t0 = time.time()
    p = subprocess.run(
        [sys.executable, str(PROBE), "--ip", "127.0.0.1", "--port", str(port),
         "--deadline", str(deadline), "--interval", str(interval), "--settle", str(settle)],
        capture_output=True, text=True, timeout=deadline + 60,
    )
    return p.returncode, p.stdout, time.time() - t0


def bare_tcp_ok(port: int) -> bool:
    """复刻被替换掉的旧判据：只看 TCP 连不连得上。"""
    try:
        socket.create_connection(("127.0.0.1", port), timeout=2).close()
        return True
    except OSError:
        return False


FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" —— {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def case_a_becomes_ready() -> None:
    """A：板端 3 s 后才能回 CAPS —— 探针必须等到那时才 READY，不能被裸连通性骗绿。"""
    print("A. 应用层 3 s 后才就绪（B28 的时间窗）")
    board = FakeBoard(answer_after=3.0)
    try:
        check("裸 TCP 判据在 0 s 就已经'就绪'（这就是 B28 的成因）", bare_tcp_ok(board.port))
        rc, out, elapsed = run_probe(board.port, deadline=30)
        check("探针退出码为 0", rc == 0, f"rc={rc}")
        check("stdout 末尾是 READY 行", "READY " in out and "NOT_READY" not in out,
              out.strip().splitlines()[-1] if out.strip() else "(空)")
        check("READY 出现在 3 s 之后，说明它真的在等应用层", elapsed >= 3.0,
              f"实耗 {elapsed:.1f}s")
        check("期间重试过不止一次", board.conns >= 2, f"连接数 {board.conns}")
    finally:
        board.close()


def case_b_never_answers() -> None:
    """B：鉴别力自证。TCP 全程可连、CAPS 永不应答 —— 旧判据绿，探针必须红。"""
    print("B. 裸 TCP 全程可连、应用层永不回包（鉴别力自证：探针必须红）")
    board = FakeBoard(answer_after=None)
    try:
        check("旧的裸 TCP 判据在这个场景下是绿的", bare_tcp_ok(board.port))
        rc, out, _ = run_probe(board.port, deadline=6)
        check("探针退出码为 1", rc == 1, f"rc={rc}")
        check("stdout 报 NOT_READY", "NOT_READY" in out,
              out.strip().splitlines()[-1] if out.strip() else "(空)")
        check("失败信息里能看出是应用层没回包，而不是连不上",
              "recv" in out.lower() or "关闭" in out or "ConnectionError" in out,
              "逐次尝试的异常类型都留在日志里")
    finally:
        board.close()


def case_c_nothing_listening() -> None:
    """C：板子/网络根本没起来 —— 也必须红，且异常类型与 B 可区分。"""
    print("C. 端口上没有任何人监听")
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # 拿一个确定没人监听的端口
    check("裸 TCP 判据也是红的", not bare_tcp_ok(port))
    rc, out, _ = run_probe(port, deadline=4)
    check("探针退出码为 1", rc == 1, f"rc={rc}")
    check("异常是连接被拒，与用例 B 的'连上了但没回包'可区分",
          "ConnectionRefusedError" in out, "两者的处置完全不同")


def main() -> int:
    if not PROBE.exists():
        print(f"找不到探针：{PROBE}")
        return 2
    for case in (case_a_becomes_ready, case_b_never_answers, case_c_nothing_listening):
        case()
        print()
    if FAILURES:
        print(f"FAIL —— {len(FAILURES)} 条不通过：" + "；".join(FAILURES))
        return 1
    print("PASS —— g3_wait_ready.py 三个场景全过（含鉴别力自证）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
