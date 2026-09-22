#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/board/arm_baseline.py —— 同片 ARM（Cortex-A9）纯软件 Stage1 基线，上板实测

## 为什么需要它

现有 CPU 对照是 i5-13500H（笔记本 45 W 级）。嵌入式赛题更公平、也更有说服力的对照是
**同一颗 Zynq 上的 ARM 自己做同样的比对要多久**——这正是「为什么要把 Stage1 放进 PL」的直接证据。

## 做什么

1. 用 `sw/bench_arm/arm_align.c`（与 `tools/align_omp.c` 同一算法，NEON popcount）编两份：
   主机 x86 版算参考答案，Cortex-A9 裸机版（-O3，standalone BSP）作被测；
2. 取 SE150 前 N 条读段（与 G3 同一 FASTQ、同一水印），XSDB 复位 PS、ps7_init，
   把水印/读段 `dow -data` 进 DDR，下载裸机 ELF 并运行（PL 不配置，与生产固件无关）；
3. 轮询 DDR 里的完成标志，读回每条结果与 XTime 计时，与主机参考逐条比对。

判据：ARM 结果与主机参考逐条完全相同（分数与位置，正反两向）才报告耗时。

## 用法

    python3 tools/board/arm_baseline.py --reads 64            # 默认 64 条
    python3 tools/board/arm_baseline.py --reads 256 --tag x

留证：`D:\\dna_board_smoke\\arm_baseline\\<run-id>\\`（report.json、串口无关，结果全在 DDR）。
依赖：`sw/workspace/dna_platform_b27/` 的 BSP（由 `sw/scripts/create_vitis.tcl` 生成，与生产固件同一份）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tools"))
import golden_model as g  # noqa: E402

SRC = REPO / "sw" / "bench_arm"
BUILD = REPO / "sw" / "workspace" / "arm_baseline"          # gitignore 覆盖
BSP = REPO / "sw/workspace/dna_platform_b27/export/dna_platform_b27/sw/dna_platform_b27/standalone_domain"
LDS = REPO / "sw" / "linker" / "lscript.ld"
ARM_GCC = "/tools/Xilinx/Vitis/2022.2/gnu/aarch32/lin/gcc-arm-none-eabi/bin/arm-none-eabi-gcc"
READS = REPO / "data/R0.83_data/Sequencing data/DNA-40.5Kb-MC-SE150.fastq"
WM = REPO / "data/R0.83_data/Source data/Watermark sequences/r0.83_watermark.txt"
XSA = REPO / "hw/build/export/dna_accel.xsa"
WIN_ROOT_UNIX = Path("/mnt/d/dna_board_smoke")
WIN_ROOT_WIN = "D:/dna_board_smoke"
XSDB_BAT = r"D:\dev_tools\Vivado_Lab\2022.2\bin\xsdb.bat"

HDR, REF, READS_ADDR, RES, SUM = 0x08000000, 0x08001000, 0x08010000, 0x09000000, 0x09F00000
MAGIC_IN, MAGIC_DONE, MAGIC_BAD = 0xAB5E0001, 0xAB5E00D0, 0xAB5E0BAD
RB, L = 150, 40500


def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"命令失败: {' '.join(map(str, cmd))}\n{r.stdout}\n{r.stderr}")
    return r


def build():
    BUILD.mkdir(parents=True, exist_ok=True)
    host = BUILD / "arm_align_host"
    sh(["gcc", "-O2", "-o", str(host), str(SRC / "arm_align.c"), str(SRC / "main_host.c")])
    elf = BUILD / "arm_baseline.elf"
    sh([ARM_GCC, "-O3", "-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=hard",
        f"-I{BSP}/bspinclude/include", "-Wl,-build-id=none",
        "-specs=" + str(REPO / "sw/workspace/dna_lwip_app_b27/Debug/Xilinx.spec"),
        "-Wl,-T", "-Wl," + str(LDS), f"-L{BSP}/bsplib/lib",
        "-o", str(elf), str(SRC / "arm_align.c"), str(SRC / "main_bm.c"),
        "-Wl,--start-group,-lxil,-lgcc,-lc,--end-group"])
    return host, elf


def prepare(n: int, out: Path):
    ref = g.planes_to_symbols(g.read_bits(WM)).astype("uint8")
    assert ref.size == L, ref.size
    reads = [s.upper() for s in g.iter_fastq(READS, n)]
    assert len(reads) == n and all(len(s) == RB for s in reads)
    blob = bytes(g.BASE2VAL.get(c, 0) for s in reads for c in s)
    (out / "ref.bin").write_bytes(ref.tobytes())
    (out / "reads.bin").write_bytes(blob)


def xsdb(script: Path, cwd: Path) -> str:
    win = str(script).replace(str(WIN_ROOT_UNIX), WIN_ROOT_WIN).replace("/", "\\")
    r = subprocess.run(["cmd.exe", "/c", f"{XSDB_BAT} {win}"], cwd=str(cwd),
                       stdin=subprocess.DEVNULL, capture_output=True, text=True)
    return r.stdout + r.stderr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reads", type=int, default=64)
    ap.add_argument("--timeout", type=int, default=1800, help="等待板端完成的秒数上限")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()

    run = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ") + (f"-{a.tag}" if a.tag else "")
    out = WIN_ROOT_UNIX / "arm_baseline" / run
    out.mkdir(parents=True)
    outw = f"{WIN_ROOT_WIN}/arm_baseline/{run}"
    print(f"[arm-baseline] run={run}  reads={a.reads}")

    host, elf = build()
    (out / "arm_baseline.elf").write_bytes(elf.read_bytes())
    with zipfile.ZipFile(XSA) as z:
        (out / "ps7_init.tcl").write_bytes(z.read("ps7_init.tcl"))
    prepare(a.reads, out)
    sh([str(host), str(out / "ref.bin"), str(out / "reads.bin"), str(a.reads), str(out / "expect.bin")])
    print("[arm-baseline] 构建与主机参考完成")

    poll = f"""connect
targets -set -nocase -filter {{name =~ "APU*"}}
rst -system
after 2000
targets -set -nocase -filter {{name =~ "*Cortex-A9*#0*"}}
source {outw}/ps7_init.tcl
ps7_init
ps7_post_config
dow -data {outw}/ref.bin 0x{REF:08X}
dow -data {outw}/reads.bin 0x{READS_ADDR:08X}
mwr 0x{HDR:08X} 0x{MAGIC_IN:08X}
mwr 0x{HDR + 4:08X} {a.reads}
mwr 0x{SUM:08X} 0
dow {outw}/arm_baseline.elf
con
puts "ARMBL> running"
set t0 [clock seconds]
set st 0
while {{[clock seconds] - $t0 < {a.timeout}}} {{
    after 2000
    if {{[catch {{set st [mrd -force -value 0x{SUM:08X}]}} err]}} {{ puts "ARMBL> mrd err $err"; continue }}
    if {{$st == 0x{MAGIC_DONE:08X} || $st == 0x{MAGIC_BAD:08X}}} break
}}
stop
puts [format "ARMBL> status 0x%08X after %d s" $st [expr {{[clock seconds] - $t0}}]]
mrd -bin -file {outw}/sum.bin 0x{SUM:08X} 8
mrd -bin -file {outw}/result.bin 0x{RES:08X} {a.reads * 4}
puts "ARMBL> dumped"
"""
    (out / "run.tcl").write_text(poll)
    log = xsdb(out / "run.tcl", WIN_ROOT_UNIX)
    (out / "xsdb.log").write_text(log)
    print("\n".join(l for l in log.splitlines() if "ARMBL>" in l or "rror" in l))

    magic, n, lo, hi, cps, prep, rb, _ = struct.unpack("<8I", (out / "sum.bin").read_bytes())
    if magic != MAGIC_DONE:
        print(f"[arm-baseline] ✗ 板端未完成 magic=0x{magic:08X}")
        return 1
    got = (out / "result.bin").read_bytes()
    exp = (out / "expect.bin").read_bytes()
    recs = [struct.unpack_from("<4i", got, 16 * i) for i in range(a.reads)]
    refs = [struct.unpack_from("<4i", exp, 16 * i) for i in range(a.reads)]
    bad = [i for i in range(a.reads) if recs[i] != refs[i]]
    secs = ((hi << 32) | lo) / cps
    rep = {
        "run": run, "reads": a.reads, "records": 2 * a.reads, "rb": rb,
        "cpu": "Cortex-A9 #0 (single core), bare-metal, -O3 NEON popcount",
        "seconds": secs, "ms_per_read": secs * 1000 / a.reads,
        "ms_per_record": secs * 1000 / (2 * a.reads),
        "reads_per_s": a.reads / secs, "prep_ms": prep * 1000 / cps,
        "mismatch": len(bad), "first_mismatch": bad[:5],
        "elf_sha256": subprocess.run(["sha256sum", str(elf)], capture_output=True, text=True).stdout.split()[0],
    }
    (out / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False))
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    if bad:
        print(f"[arm-baseline] ✗ {len(bad)}/{a.reads} 条与主机参考不一致，耗时不予采信")
        return 1
    print(f"[arm-baseline] ✓ {a.reads}/{a.reads} 条与主机参考逐条一致；"
          f"{rep['ms_per_record']:.3f} ms/记录（单核 A9）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
