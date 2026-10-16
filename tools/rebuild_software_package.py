#!/usr/bin/env python3
"""从一份 Vivado 硬件包构建完整的 Vitis 2022.2 软件验收包。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VITIS_ROOT = Path("/tools/Xilinx/Vitis/2022.2")
TOOLBIN = VITIS_ROOT / "gnu/aarch32/lin/gcc-arm-none-eabi/bin"
XSCT = VITIS_ROOT / "bin/xsct"
BOOTGEN = VITIS_ROOT / "bin/bootgen"
GCC = TOOLBIN / "arm-none-eabi-gcc"
OBJ_COPY = TOOLBIN / "arm-none-eabi-objcopy"
APP_NAME = "dna_lwip_app"
DOMAIN = "standalone_domain"
CPU = "ps7_cortexa9_0"
APP_OPT_LEVEL = "-O2"
APP_CFLAGS = (
    "-mcpu=cortex-a9 -mfpu=vfpv3 -mfloat-abi=hard "
    f"{APP_OPT_LEVEL} -g -Wall -Wextra -ffunction-sections -fdata-sections "
    "-MMD -MP -I$(APP_SRC) -I$(BSP)/include"
)

sys.path.insert(0, str(REPO / "tools"))
from board.g3_artifacts import inspect_xsa  # noqa: E402


class BuildError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_input(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = REPO / path
    return path.resolve()


def parse_key_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def json_write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def run_logged(name: str, command: list[str], *, cwd: Path, log_path: Path,
               env: dict[str, str] | None = None, echo: bool = True) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = shlex.join(command)
    print(f"$ {rendered}", flush=True)
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write(f"COMMAND: {rendered}\nCWD: {cwd}\n\n")
        process = subprocess.Popen(
            command, cwd=cwd, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
            if echo:
                sys.stdout.write(line)
                sys.stdout.flush()
        rc = process.wait()
        log.write(f"\nEXIT_CODE: {rc}\n")
    shown_log = log_path.relative_to(REPO).as_posix() if under(log_path, REPO) else str(log_path)
    print(f"[{name}] exit={rc}; 日志：{shown_log}", flush=True)
    return rc


def run_capture(command: list[str], *, cwd: Path = REPO) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)


def write_sums(package: Path) -> int:
    files = sorted(
        path for path in package.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    )
    lines = [f"{sha256(path)}  {path.relative_to(package).as_posix()}" for path in files]
    (package / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines)


def verify_sums(package: Path, count: int) -> None:
    result = run_capture(["sha256sum", "-c", "SHA256SUMS"], cwd=package)
    ok = sum(line.endswith(": OK") for line in result.stdout.splitlines())
    bad = [line for line in result.stdout.splitlines() if not line.endswith(": OK")]
    if result.returncode != 0 or ok != count or bad or result.stderr.strip():
        detail = "\n".join((bad[:20] + result.stderr.splitlines()[:20]))
        raise BuildError(f"sha256sum -c 失败：{ok}/{count} OK\n{detail}")
    print(f"sha256sum -c SHA256SUMS：{ok}/{count} OK", flush=True)


def copy_app_sources(app_dir: Path, repo: Path) -> int:
    src_dir = app_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for src in sorted((repo / "sw/app").glob("*")):
        if not src.is_file() or src.suffix not in {".c", ".h"} or src.name == "xparameters.h":
            continue
        target = src_dir / src.name
        shutil.copy2(src, target)
        if target.read_bytes() != src.read_bytes():
            raise BuildError(f"应用源码复制后字节不一致：{src.relative_to(repo)}")
        copied += 1
    if not copied:
        raise BuildError("sw/app 下没有可复制的 C/H 源码")
    linker = repo / "sw/linker/lscript.ld"
    if not linker.is_file():
        raise BuildError(f"缺少链接脚本：{linker}")
    shutil.copy2(linker, src_dir / "lscript.ld")
    (src_dir / "app_net_config.h").write_text(
        '#pragma once\n'
        '#define APP_IP_ADDR      "192.168.1.10"\n'
        '#define APP_IP_MASK      "255.255.255.0"\n'
        '#define APP_GW_ADDR      "192.168.1.1"\n',
        encoding="ascii",
    )
    return copied


def compute_fw_build_id(app_src_dir: Path) -> str:
    """按相对路径排序，对已暂存的应用 .c/.h 路径与内容做 SHA-256 摘要。"""
    sources = sorted(
        (path for path in app_src_dir.rglob("*")
         if path.is_file() and path.suffix in {".c", ".h"}),
        key=lambda path: path.relative_to(app_src_dir).as_posix(),
    )
    if not sources:
        raise BuildError(f"应用源码目录没有可用于构建身份的 .c/.h 文件：{app_src_dir}")
    digest = hashlib.sha256()
    for path in sources:
        digest.update(path.relative_to(app_src_dir).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def write_fallback_makefile(app_dir: Path, *, repo: Path, platform_name: str,
                            fw_build_id: str) -> None:
    if " " in str(repo) or " " in str(app_dir):
        raise BuildError("当前直接 GCC Makefile 不支持含空格的仓库/输出路径")
    if not re.fullmatch(r"[0-9a-f]{16}", fw_build_id):
        raise BuildError(f"固件构建 ID 必须为 16 位小写十六进制：{fw_build_id!r}")
    platform_rel = f"../{platform_name}/{CPU}/{DOMAIN}/bsp/{CPU}"
    makefile = f"""ROOT := {repo}
APP_SRC := $(CURDIR)/src
OUT := $(CURDIR)/Debug
BSP := $(CURDIR)/{platform_rel}
CC := {GCC}
CPU_FLAGS := -mcpu=cortex-a9 -mfpu=vfpv3 -mfloat-abi=hard
CFLAGS := {APP_CFLAGS} -DFW_BUILD_ID=\\\"{fw_build_id}\\\"
LDFLAGS := $(CPU_FLAGS) -Wl,-build-id=none -Wl,--gc-sections -Wl,-Map,$(OUT)/{APP_NAME}.map -specs=$(ROOT)/sw/app/Xilinx.spec -T$(ROOT)/sw/linker/lscript.ld -L$(BSP)/lib
SOURCES := $(wildcard $(APP_SRC)/*.c)
OBJECTS := $(patsubst $(APP_SRC)/%.c,$(OUT)/%.o,$(SOURCES))
DEPS := $(OBJECTS:.o=.d)
ELF := $(OUT)/{APP_NAME}.elf

.PHONY: all
all: $(ELF)
\t@test -s $(ELF)
\t@echo APP_BUILD_PASS source=sw/app BSP=generated-from-XSA lwip=$(LWIP_LIBRARY)

$(ELF): $(OBJECTS) $(ROOT)/sw/linker/lscript.ld
\t$(CC) $(LDFLAGS) -o $@ $(OBJECTS) -Wl,--start-group -llwip4 -lxil -lgcc -lc -Wl,--end-group

$(OUT)/%.o: $(APP_SRC)/%.c
\tmkdir -p $(OUT)
\t$(CC) $(CFLAGS) -c $< -o $@

-include $(DEPS)
"""
    (app_dir / "Makefile").write_text(makefile, encoding="utf-8")


def find_lwip_bsp(bsp_root: Path) -> tuple[str, Path, str]:
    lwip_dirs = sorted(path for path in (bsp_root / "libsrc").glob("lwip*") if path.is_dir())
    usable = []
    for path in lwip_dirs:
        m = re.fullmatch(r"lwip(\d+)_v(\d+_\d+)", path.name)
        if m:
            archive = bsp_root / "lib" / "liblwip4.a"
            if archive.is_file() and archive.stat().st_size:
                upstream = {"211": "2.1.1", "213": "2.1.3", "210": "2.1.0"}.get(m.group(1), "unknown")
                usable.append((path.name, path, upstream))
    if len(usable) != 1:
        raise BuildError(f"BSP 中需要唯一 lwIP 实现和 liblwip4.a，找到：{[x[0] for x in usable]}")
    name, path, upstream = usable[0]
    include_header = bsp_root / "include/lwipopts.h"
    tcp_headers = [include_header, path / "src/contrib/ports/xilinx/include/lwipopts.h"]
    tcp_headers = [header for header in tcp_headers if header.is_file()]
    if not tcp_headers:
        raise BuildError("新 BSP 中找不到 lwipopts.h，platform generate 未物化 BSP 头文件")
    for header in tcp_headers:
        body = header.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"^\s*#define\s+TCP_WND\s+(\S+)\s*$", body, re.M)
        if not match or match.group(1) != "32768":
            raise BuildError(f"TCP_WND 不等于 32768，拒绝打包：{header}")
    return name, path, upstream


def run_g3_gate(package: Path) -> int:
    command = [
        "bash", "tools/run_g3.sh",
        "--artifact-dir", str(package),
        "--strict-artifacts",
        "--device", "xc7z020",
        "--ip", "192.168.1.10",
        "--xsdb", str(VITIS_ROOT / "bin/xsdb"),
        "--hw-server", "TCP:127.0.0.1:3132",
        "--win-root", "/tmp/vitis-chain-plan-only",
        "--uart-port", "/dev/ttyUSB2",
        "--plan-only",
    ]
    with tempfile.NamedTemporaryFile(prefix="vitis-chain-g3-plan-", suffix=".log",
                                     dir="/tmp", delete=False) as stream:
        gate_log = Path(stream.name)
    return run_logged("run_g3 strict plan-only", command, cwd=REPO,
                      log_path=gate_log, echo=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从已有 Vivado 硬件包构建可由 G3 strict-artifacts 接受的 Vitis 2022.2 软件包。",
        epilog="只创建新输出目录；失败时保留部分日志/产物，换一个新 --out 路径重试。",
    )
    parser.add_argument("--hw-package", required=True, help="硬件包目录（hw/build 下，含 export/*.xsa）")
    parser.add_argument("--out", required=True, help="新软件包目录（必须是 hw/build 的直接子目录，不能已存在）")
    parser.add_argument("--label", default="", help="写入 manifest 的说明标签，可选")
    args = parser.parse_args()

    try:
        hw_package = resolve_input(args.hw_package)
        out_package = resolve_input(args.out)
        hw_build_root = (REPO / "hw/build").resolve()
        if not under(hw_package, hw_build_root) or hw_package == hw_build_root or not hw_package.is_dir():
            raise BuildError(f"--hw-package 必须是 hw/build 下的现存目录：{hw_package}")
        if out_package.parent != hw_build_root:
            raise BuildError(f"--out 必须是 hw/build 的直接子目录：{out_package}")
        if out_package.exists():
            raise BuildError(f"输出目录已存在，拒绝覆盖：{out_package}")
        if out_package == hw_package:
            raise BuildError("--out 不能等于 --hw-package")

        xsa_candidates = sorted((hw_package / "export").glob("*.xsa"))
        if len(xsa_candidates) != 1:
            raise BuildError(f"硬件包 export/ 必须恰有一份 XSA，实得 {len(xsa_candidates)}")
        source_xsa = xsa_candidates[0].resolve()
        source_bit = hw_package / "export/top_bd_wrapper.bit"
        hardware_config = hw_package / "export/hardware_build_config.txt"
        if not source_bit.is_file() or not hardware_config.is_file():
            raise BuildError("硬件包缺少 export/top_bd_wrapper.bit 或 hardware_build_config.txt")
        if not XSCT.is_file() or not os.access(XSCT, os.X_OK):
            raise BuildError(f"缺少 Vitis 2022.2 XSCT：{XSCT}")
        if not all(p.is_file() and os.access(p, os.X_OK) for p in (GCC, BOOTGEN, OBJ_COPY)):
            raise BuildError("Vitis 2022.2 安装树缺 ARM GCC / objcopy / bootgen")

        xsa = inspect_xsa(source_xsa)
        config = parse_key_values(hardware_config)
        if config.get("part", "").lower() != xsa["part"]:
            raise BuildError(f"硬件配置 part 与 XSA 不同：{config.get('part')} / {xsa['part']}")
        if config.get("tool_version") != xsa["tool_version"]:
            raise BuildError("hardware_build_config 的 tool_version 与 XSA generatedVersion 不同")
        source_bit_sha = sha256(source_bit)
        if source_bit_sha != xsa["bit_sha256"]:
            raise BuildError("硬件包独立 bit 与 XSA 内 FULL_BIT 不一致")
        for name in ("READ_BPS", "NUM_LC", "STRIDE", "REF_LEN", "BATCH",
                     "C_STAGE1_P_WAYS", "C_STAGE1_PIPE_TREE"):
            if name not in config or int(config[name], 0) != xsa["parameters"].get(name):
                raise BuildError(f"hardware_build_config 的 {name} 与 XSA HWH 不一致")

        platform_name = source_xsa.stem + "_platform"
        out_package.mkdir(parents=True)
        export_dir = out_package / "export"
        workspace = out_package / "workspace"
        logs = out_package / "logs"
        reports = out_package / "reports"
        for directory in (export_dir, workspace, logs, reports):
            directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_bit, export_dir / "top_bd_wrapper.bit")
        shutil.copy2(source_xsa, export_dir / "dna_accel.xsa")
        shutil.copy2(hardware_config, export_dir / "hardware_build_config.txt")
        if (hw_package / "reports").is_dir():
            shutil.copytree(hw_package / "reports", reports, dirs_exist_ok=True)
        with zipfile.ZipFile(source_xsa) as archive:
            ps7_members = [name for name in archive.namelist() if name.rsplit("/", 1)[-1] == "ps7_init.tcl"]
            if len(ps7_members) != 1:
                raise BuildError(f"XSA 应含唯一 ps7_init.tcl，实得 {len(ps7_members)}")
            ps7_data = archive.read(ps7_members[0])
        (export_dir / "ps7_init.tcl").write_bytes(ps7_data)

        print(f"硬件输入：{hw_package}", flush=True)
        print(f"XSA SHA-256：{sha256(source_xsa)}", flush=True)
        print(f"FULL_BIT SHA-256：{source_bit_sha}", flush=True)
        print(f"平台名：{platform_name}；应用名：{APP_NAME}", flush=True)

        version_log = logs / "xsct-version.log"
        version_rc = run_logged("XSCT version", [str(XSCT), "-nodisp", "-eval", "puts [version]"],
                                cwd=REPO, log_path=version_log)
        if version_rc != 0:
            raise BuildError("XSCT 版本探针失败")
        xsct_version_text = version_log.read_text(encoding="utf-8", errors="replace")
        xsct_version_match = re.search(r"xsct\s+(20\d{2}\.\d+\.\d+)", xsct_version_text, re.I)
        if not xsct_version_match:
            raise BuildError("無法從 XSCT 版本輸出核实版本")
        xsct_version = xsct_version_match.group(1)
        if not xsct_version.startswith("2022.2"):
            raise BuildError(f"此入口限定 Vitis/XSCT 2022.2，实际 XSCT={xsct_version}")

        xsct_command = [
            str(XSCT), "-nodisp", str(REPO / "sw/scripts/create_vitis.tcl"),
            f"xsa={source_xsa}", f"ws={workspace}", f"plat={platform_name}",
            f"app={APP_NAME}", f"dom={DOMAIN}", "uart=ps7_uart_0",
            "phy_link_speed=CONFIG_LINKSPEED_AUTODETECT", "build_app=0",
        ]
        xsct_log = logs / "xsct-build.log"
        xsct_rc = run_logged("XSCT platform/BSP/FSBL (app skipped)", xsct_command,
                             cwd=REPO, log_path=xsct_log)
        if xsct_rc != 0:
            raise BuildError(f"XSCT 平台/BSP/FSBL 构建失败（exit={xsct_rc}）")

        platform_dir = workspace / platform_name
        bsp_root = platform_dir / CPU / DOMAIN / "bsp" / CPU
        xparameters = bsp_root / "include/xparameters.h"
        if not xparameters.is_file() or not (bsp_root / "lib/libxil.a").is_file():
            raise BuildError("XSCT 后没有新 XSA 的 BSP 头文件/libxil.a")
        lwip_library, lwip_dir, lwip_upstream = find_lwip_bsp(bsp_root)
        tcp_header = bsp_root / "include/lwipopts.h"
        tcp_match = re.search(r"^\s*#define\s+TCP_WND\s+(\S+)\s*$",
                              tcp_header.read_text(encoding="utf-8", errors="replace"), re.M)
        if not tcp_match or tcp_match.group(1) != "32768":
            raise BuildError("新 BSP include/lwipopts.h 未确认 TCP_WND=32768")
        print(f"BSP 头文件物化顺序已验证：TCP_WND={tcp_match.group(1)}，lwIP={lwip_library}", flush=True)

        app_dir = workspace / APP_NAME
        app_elf = app_dir / "Debug" / f"{APP_NAME}.elf"
        gcc_version_result = run_capture([str(GCC), "-dumpfullversion", "-dumpversion"])
        if gcc_version_result.returncode != 0:
            raise BuildError("ARM GCC 版本探针失败")
        gcc_version = gcc_version_result.stdout.strip().splitlines()[-1]
        print(f"APPLICATION: XSCT app create/build skipped; use Vitis 2022.2 ARM GCC {gcc_version} with the generated XSA BSP.", flush=True)
        copied = copy_app_sources(app_dir, REPO)
        print(f"APPLICATION: 从 sw/app 复制并逐字节核对 {copied} 个 .c/.h 文件；排除历史 xparameters.h。", flush=True)
        fw_build_id = compute_fw_build_id(app_dir / "src")
        app_cflags = f'{APP_CFLAGS} -DFW_BUILD_ID=\\"{fw_build_id}\\"'
        print(f"APPLICATION: fw_build_id={fw_build_id}（按暂存 .c/.h 路径与内容计算）。", flush=True)
        write_fallback_makefile(
            app_dir, repo=REPO, platform_name=platform_name,
            fw_build_id=fw_build_id,
        )
        build_env = os.environ.copy()
        build_env["PATH"] = str(TOOLBIN) + os.pathsep + build_env.get("PATH", "")
        build_env["LWIP_LIBRARY"] = lwip_library
        if run_logged("ARM GCC fixed -O2 app build", ["make", "-C", str(app_dir), "all"],
                      cwd=REPO, log_path=logs / "app-build.log", env=build_env) != 0:
            raise BuildError("ARM GCC 固定 -O2 应用编译/链接失败")
        app_log = (logs / "app-build.log").read_text(encoding="utf-8", errors="replace")
        if "APP_BUILD_PASS" not in app_log:
            raise BuildError("ARM GCC 日志缺 APP_BUILD_PASS")
        echo_compile_lines = [
            line for line in app_log.splitlines()
            if "-c " in line and "src/echo.c" in line and "Debug/echo.o" in line
        ]
        if len(echo_compile_lines) != 1:
            raise BuildError(f"ARM GCC 日志中的 echo.c 编译命令不是恰好一条：{len(echo_compile_lines)}")
        echo_compile_line = echo_compile_lines[0]
        if APP_OPT_LEVEL not in echo_compile_line.split() or "-O0" in echo_compile_line.split():
            raise BuildError(f"echo.c 编译命令没有唯一固定优化级别 {APP_OPT_LEVEL}：{echo_compile_line}")
        if not app_elf.is_file() or not app_elf.stat().st_size:
            raise BuildError(f"应用 ELF 缺失或为空：{app_elf}")

        fsbl_candidates = [
            platform_dir / "export" / platform_name / "sw" / platform_name / "boot/fsbl.elf",
            platform_dir / "zynq_fsbl/fsbl.elf",
        ]
        fsbl_source = next((path for path in fsbl_candidates if path.is_file() and path.stat().st_size), None)
        if fsbl_source is None:
            raise BuildError("platform generate 后没有非空 FSBL ELF")
        shutil.copy2(fsbl_source, export_dir / "fsbl.elf")
        shutil.copy2(app_elf, export_dir / f"{APP_NAME}.elf")
        bif = export_dir / "boot.bif"
        bif.write_text(
            "the_ROM_image:\n{\n  [bootloader] fsbl.elf\n  top_bd_wrapper.bit\n  dna_lwip_app.elf\n}\n",
            encoding="ascii",
        )

        bootgen_log = logs / "bootgen-create.log"
        bootgen_rc = run_logged(
            "Bootgen create BOOT.bin",
            [str(BOOTGEN), "-image", "boot.bif", "-arch", "zynq", "-o", "BOOT.bin", "-w", "on"],
            cwd=export_dir, log_path=bootgen_log,
        )
        bootgen_text = bootgen_log.read_text(encoding="utf-8", errors="replace")
        if bootgen_rc != 0 or "Bootimage generated successfully" not in bootgen_text:
            raise BuildError("Bootgen 没有以成功哨兵生成 BOOT.bin")
        if not (export_dir / "BOOT.bin").is_file() or not (export_dir / "BOOT.bin").stat().st_size:
            raise BuildError("BOOT.bin 缺失或为空")
        bootgen_version_match = re.search(r"Xilinx Bootgen v([0-9.]+)", bootgen_text)
        if not bootgen_version_match:
            raise BuildError("无法从 Bootgen 实际构建输出核实版本")
        bootgen_version = bootgen_version_match.group(1)

        readback_path = reports / "bootgen-readback.txt"
        readback_rc = run_logged(
            "Bootgen readback", [str(BOOTGEN), "-read", "BOOT.bin"],
            cwd=export_dir, log_path=readback_path,
        )
        readback_text = readback_path.read_text(encoding="utf-8", errors="replace")
        if readback_rc != 0 or "total_images (0x04) : 0x00000003" not in readback_text:
            raise BuildError("Bootgen readback 未确认 3 个 image")
        for name in ("fsbl.elf", "top_bd_wrapper.bit", f"{APP_NAME}.elf"):
            if f"IMAGE HEADER ({name})" not in readback_text:
                raise BuildError(f"BOOT.bin readback 缺少 {name}")

        xpar_text = xparameters.read_text(encoding="utf-8", errors="replace")
        ldpc_match = re.search(r"^\s*#define\s+XPAR_LDPC_DECODER_0_BASEADDR\s+(0x[0-9A-Fa-f]+)", xpar_text, re.M)
        if not ldpc_match:
            raise BuildError("本次 XSA 的新 BSP 缺少 XPAR_LDPC_DECODER_0_BASEADDR")
        params = {name: int(xsa["parameters"][name]) for name in (
            "READ_BPS", "NUM_LC", "STRIDE", "REF_LEN", "BATCH",
            "C_STAGE1_P_WAYS", "C_STAGE1_PIPE_TREE",
        )}
        params["LDPC_DECODER"] = True
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        hw_rel = hw_package.relative_to(REPO).as_posix()
        xsa_rel = source_xsa.relative_to(REPO).as_posix()
        manifest = {
            "schema_version": 1,
            "package_name": out_package.name,
            "created_utc": now,
            "fw_build_id": fw_build_id,
            "board_id": config["board_id"],
            "part": xsa["part"],
            "parameters": params,
            "artifacts": {
                "bit": "export/top_bd_wrapper.bit",
                "xsa": "export/dna_accel.xsa",
                "ps7_init": "export/ps7_init.tcl",
                "elf": f"export/{APP_NAME}.elf",
                "fsbl": "export/fsbl.elf",
                "boot": "export/BOOT.bin",
            },
            "tool_versions": {
                "vivado": str(xsa["tool_version"]),
                "vitis": "2022.2",
                "xsct": xsct_version,
                "arm_none_eabi_gcc": gcc_version,
                "bootgen": bootgen_version,
                "vivado_note": "硬件来自指定源包；软件重建未重新运行 Vivado",
            },
            "software": {
                "cpu": CPU,
                "os": "standalone",
                "uart": "ps7_uart_0",
                "lwip_library": lwip_library,
                "lwip_upstream": lwip_upstream,
                "tcp_wnd": 32768,
                "phy_link_speed": "CONFIG_LINKSPEED_AUTODETECT",
                "application_build_method": "Vitis 2022.2 ARM GCC direct make against the newly generated XSA BSP; XSCT app create/build skipped",
                "application_optimization_level": APP_OPT_LEVEL,
                "application_cflags": app_cflags,
                "application_build_sentinel": "APP_BUILD_PASS",
                "ldpc_base_macro": "XPAR_LDPC_DECODER_0_BASEADDR",
                "ldpc_base_address": ldpc_match.group(1).lower(),
            },
            "hardware_build": {
                "source_package": hw_rel,
                "source_xsa": xsa_rel,
                "source_xsa_sha256": sha256(source_xsa),
                "result": f"源硬件包 {hw_rel}；本软件入口未重新运行 Vivado",
            },
        }
        if args.label:
            manifest["label"] = args.label
        json_write(out_package / "manifest.json", manifest)

        summary = [
            "# Software package build summary",
            "",
            f"- Hardware package: `{hw_rel}`.",
            f"- Source XSA: `{xsa_rel}`; SHA-256 `{sha256(source_xsa)}`.",
            f"- Part: `{xsa['part']}`; XSA generatedVersion: `{xsa['tool_version']}`.",
            f"- Geometry: `{json.dumps(params, sort_keys=True)}`.",
            f"- Toolchain: Vivado {xsa['tool_version']} source package; Vitis/XSCT {xsct_version}; ARM GCC {gcc_version}; Bootgen {bootgen_version}.",
            f"- BSP: `{lwip_library}`; materialized by the first `platform generate`, then verified `TCP_WND=32768` after the second generate.",
            "- Application: XSCT app create/build skipped; the final app is always built with `write_fallback_makefile` against the newly generated XSA BSP.",
            f"- Application optimization: `{APP_OPT_LEVEL}` (fixed for every package built by this entrypoint).",
            f"- Application CFLAGS: `{app_cflags}`.",
            f"- Firmware build ID: `{fw_build_id}` (first 16 lowercase hex characters of SHA-256 over sorted staged `.c`/`.h` relative paths and contents).",
            f"- FSBL source: `{fsbl_source.relative_to(workspace).as_posix()}`.",
            f"- LDPC base address from newly generated BSP: `{ldpc_match.group(1).lower()}`.",
            "- BOOT.bin readback requires three images: FSBL, bitstream, and application ELF.",
            "- Final SHA256SUMS and G3 strict plan-only checks are executed by this entrypoint; neither step accesses a board.",
            "- This package is a software/build artifact result, not board-pass evidence.",
        ]
        (reports / "software_build_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

        commands = [
            f"XSCT version probe: {version_rc}",
            f"XSCT create_vitis.tcl platform/BSP/FSBL (app skipped): {xsct_rc}",
            f"Vitis 2022.2 ARM GCC make ({APP_OPT_LEVEL}): 0 (APP_BUILD_PASS)",
        ]
        commands.extend((f"Bootgen create: {bootgen_rc}", f"Bootgen readback: {readback_rc}"))
        (reports / "command-exit-codes.txt").write_text("\n".join(commands) + "\n", encoding="utf-8")

        source_manifest_result = run_capture([
            sys.executable, str(REPO / "tools/write_source_manifest.py"),
            "--package", str(out_package),
        ])
        sys.stdout.write(source_manifest_result.stdout)
        sys.stderr.write(source_manifest_result.stderr)
        if source_manifest_result.returncode != 0:
            raise BuildError("write_source_manifest.py 失败")

        manifest_path = out_package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifact_paths = sorted(path for path in export_dir.iterdir() if path.is_file())
        artifact_table = {path.relative_to(out_package).as_posix(): sha256(path) for path in artifact_paths}
        artifact_manifest = {
            "schema_version": 1,
            "scope": "exported-software-package-artifacts",
            "source_manifest": manifest["source_manifest"],
            "artifacts_sha256": artifact_table,
        }
        artifact_manifest_path = out_package / "artifact_manifest.json"
        json_write(artifact_manifest_path, artifact_manifest)
        manifest["artifact_manifest"] = {
            "path": "artifact_manifest.json",
            "sha256": sha256(artifact_manifest_path),
        }
        json_write(manifest_path, manifest)

        count = write_sums(out_package)
        verify_sums(out_package, count)
        print(f"制品目录：{out_package}", flush=True)
        print(f"  XSA / bit / ps7_init：{sha256(export_dir / 'dna_accel.xsa')} / {sha256(export_dir / 'top_bd_wrapper.bit')} / {sha256(export_dir / 'ps7_init.tcl')}", flush=True)
        print(f"  FSBL / ELF / BOOT：{sha256(export_dir / 'fsbl.elf')} / {sha256(export_dir / f'{APP_NAME}.elf')} / {sha256(export_dir / 'BOOT.bin')}", flush=True)
        print(f"  SHA256SUMS entries：{count}", flush=True)

        gate_rc = run_g3_gate(out_package)
        if gate_rc != 0:
            raise BuildError("run_g3.sh --plan-only --strict-artifacts 门禁失败")
        print("G3 strict-artifacts --plan-only：PASS（未连接板卡、未烧录）", flush=True)
        return 0
    except BuildError as error:
        print(f"ERROR: {error}", file=sys.stderr, flush=True)
        print("失败时保留新输出目录中的部分留证；不会改动输入硬件包。", file=sys.stderr, flush=True)
        return 1
    except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
        print("失败时保留新输出目录中的部分留证；不会改动输入硬件包。", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
