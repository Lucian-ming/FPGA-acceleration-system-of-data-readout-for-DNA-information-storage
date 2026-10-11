#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从历史 gui_app.exe 中提取 LDPC 解码器缺失的 MinGW 运行时 DLL。

`clients/python/resources/R5_6_LDPC_hard_decoder.exe` 是 MinGW 编译的，运行时依赖
`libstdc++-6.dll`、`libgcc_s_seh-1.dll`、`libwinpthread-1.dll`。这三个 DLL 没有随
仓库交付，所以在干净的 Windows 机器上直接运行该 EXE 会**静默失败**（无输出、无报错、
退出码还是 0），非常容易被误判成「输入数据不对」。

它们被打包在 `archive/submission_2025-11-07/演示文件/gui_app.exe`（PyInstaller onefile）里。
本脚本解析 PyInstaller 的 CArchive 结构把它们取出来。提取结果已放在
`clients/python/resources/`，此脚本仅用于说明来源与必要时重新提取。

用法：python3 tools/extract_ldpc_dlls.py [输出目录]
"""

import struct
import sys
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXE = REPO / "archive" / "submission_2025-11-07" / "演示文件" / "gui_app.exe"
WANTED = {"libstdc++-6.dll", "libgcc_s_seh-1.dll", "libwinpthread-1.dll"}
PYINST_MAGIC = b"MEI\014\013\012\013\016"


def main(argv):
    out = Path(argv[1]) if len(argv) > 1 else REPO / "clients" / "python" / "resources"
    out.mkdir(parents=True, exist_ok=True)

    data = EXE.read_bytes()
    idx = data.rfind(PYINST_MAGIC)
    if idx < 0:
        print("未找到 PyInstaller cookie")
        return 1

    # cookie: magic(8) + pkgLen(4) + tocPos(4) + tocLen(4) + pyvers(4) + pylibname(64)
    pkg_len, toc_pos, toc_len, _pyvers = struct.unpack("!IIII", data[idx + 8: idx + 24])
    start = idx + 8 + 16 + 64 - pkg_len
    toc = data[start + toc_pos: start + toc_pos + toc_len]

    pos = 0
    while pos < len(toc):
        (entry_len,) = struct.unpack("!I", toc[pos:pos + 4])
        entry_pos, c_size, _u_size = struct.unpack("!III", toc[pos + 4: pos + 16])
        compressed = toc[pos + 16]
        name = toc[pos + 18: pos + entry_len].rstrip(b"\x00").decode("utf-8", "ignore")
        if name in WANTED:
            blob = data[start + entry_pos: start + entry_pos + c_size]
            if compressed:
                blob = zlib.decompress(blob)
            (out / name).write_bytes(blob)
            print(f"已提取 {name}  ({len(blob)} 字节)")
        pos += entry_len
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
