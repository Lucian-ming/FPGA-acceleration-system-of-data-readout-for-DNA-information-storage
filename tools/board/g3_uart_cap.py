#!/usr/bin/env python3
"""WSL 本地 USB-UART 只读采集器；日志保存原始串口字节。"""
from __future__ import annotations

import argparse
import os
import select
import sys
import termios
import time
from pathlib import Path


def capture(device: Path, log_path: Path, seconds: float, stop_file: Path) -> int:
    fd = None
    received = 0
    try:
        fd = os.open(device, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0
        attrs[1] = 0
        attrs[2] = termios.B115200 | termios.CS8 | termios.CLOCAL | termios.CREAD
        attrs[3] = 0
        attrs[4] = termios.B115200
        attrs[5] = termios.B115200
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("wb") as log:
            print(f"CAPTURING {device} 115200 -> {log_path}", flush=True)
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline and not stop_file.exists():
                readable, _, _ = select.select([fd], [], [], 0.1)
                if not readable:
                    continue
                try:
                    data = os.read(fd, 4096)
                except BlockingIOError:
                    continue
                if data:
                    log.write(data)
                    log.flush()
                    received += len(data)
        print(f"CAPTURE_DONE bytes={received}", flush=True)
        return 0
    except Exception as exc:  # noqa: BLE001 - turn device/config errors into explicit capture failures
        print(f"OPEN_FAIL {type(exc).__name__}: {exc}", flush=True)
        return 1
    finally:
        if fd is not None:
            os.close(fd)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", type=Path, required=True,
                        help="WSL 串口设备，例如 /dev/ttyUSB2")
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--seconds", type=float, required=True)
    parser.add_argument("--stop-file", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.seconds <= 0:
        parser.error("--seconds 必须为正数")
    return capture(args.device, args.log, args.seconds, args.stop_file)


if __name__ == "__main__":
    sys.exit(main())
