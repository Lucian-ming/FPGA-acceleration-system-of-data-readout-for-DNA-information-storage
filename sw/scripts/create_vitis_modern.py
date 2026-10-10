#!/usr/bin/env python3
"""Vitis2026.1 Python构建入口；输入由DNA_VITIS_CONFIG指向的JSON显式指定。

配置/硬件生成/下载分离；不连接JTAG，不修改网卡，不复用旧BSP。
调用方必须同时检查SOFTWARE_BUILD_PASS哨兵和software_build_config.json，
Vitis2026.1启动器在Python异常时也可能返回0。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
import xml.etree.ElementTree as ET


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def one_file(paths, label):
    candidates = sorted(p for p in paths if p.is_file() and p.stat().st_size > 0)
    # Vitis exports an identical FSBL copy alongside its build output.
    # Permit those copies only after verifying one unique nonempty image.
    if not candidates or len({sha256(p) for p in candidates}) != 1:
        raise RuntimeError(f"{label}需要唯一非空镜像（副本须逐字节同哈希），实际为：{candidates}")
    return candidates[0]


def run(config):
    required = {"repo_root", "workspace", "xsa", "export_dir", "uart", "board_id", "part", "bootgen"}
    missing = required - config.keys()
    allowed = required | {"platform", "domain", "app", "lwip", "dry_run", "embedded_sw_repo"}
    if missing or config.keys() - allowed:
        raise ValueError(f"缺少字段：{missing}；未知字段：{config.keys() - allowed}")
    root = Path(config["repo_root"]).resolve()
    ws = Path(config["workspace"]).resolve()
    xsa = Path(config["xsa"]).resolve()
    export = Path(config["export_dir"]).resolve()
    bootgen = Path(config["bootgen"]).resolve()
    app_src = root / "sw/app"
    linker = root / "sw/linker/lscript.ld"
    for p in (xsa, linker, bootgen):
        if not p.is_file():
            raise ValueError(f"必需输入不存在：{p}")
    if not app_src.is_dir():
        raise ValueError(f"应用源码目录不存在：{app_src}")
    if ws.exists() and any(ws.iterdir()):
        raise ValueError(f"workspace必须全新或空，禁止复用旧BSP：{ws}")
    if config["uart"] not in {"ps7_uart_0", "ps7_uart_1"}:
        raise ValueError("uart必须依据本板XSA显式选ps7_uart_0/1")
    with zipfile.ZipFile(xsa) as archive:
        parts = set()
        for name in archive.namelist():
            if name.endswith((".hwh", ".xml")):
                doc = ET.fromstring(archive.read(name))
                for info in doc.iter("SYSTEMINFO"):
                    value = info.get("PART")
                    if not value and all(info.get(key) for key in ("DEVICE", "PACKAGE", "SPEEDGRADE")):
                        value = "xc" + info.get("DEVICE") + info.get("PACKAGE") + info.get("SPEEDGRADE")
                    if value:
                        parts.add(value.lower())
        if parts != {config["part"].lower()}:
            raise ValueError(f"XSA器件{parts}与期望{config['part']}不一致")
    print(f"SOFTWARE_CONFIG board={config['board_id']} part={config['part']} XSA={xsa} UART={config['uart']}", flush=True)
    if config.get("dry_run", False):
        print("SOFTWARE_CONFIG_PASS (仅配置检查，未生成BSP/ELF)", flush=True)
        return
    for name in ("dna_lwip_app.elf", "fsbl.elf", "BOOT.bin", "software_build_config.json"):
        if (export / name).exists():
            raise ValueError(f"发布输出已存在，禁止覆盖：{export / name}")
    import vitis
    plat_name = config.get("platform", "dna_platform")
    dom_name = config.get("domain", "standalone_domain")
    app_name = config.get("app", "dna_lwip_app")
    lwip = config.get("lwip", "lwip220")
    client = vitis.create_client()
    try:
        client.set_workspace(str(ws))
        if config.get("embedded_sw_repo"):
            client.add_embedded_sw_repo(level="LOCAL", path=config["embedded_sw_repo"])
        platform = client.create_platform_component(
            name=plat_name, hw_design=str(xsa), cpu="ps7_cortexa9_0",
            os="standalone", domain_name=dom_name, no_boot_bsp=False,
            generate_dtb=False, compiler="gcc")
        domain = platform.get_domain(name=dom_name)
        domain.set_lib(lwip)
        domain.set_config("os", "standalone_stdin", config["uart"])
        domain.set_config("os", "standalone_stdout", config["uart"])
        for param, value in {"lwip220_api_mode": "RAW_API", "lwip220_dhcp": "false", "lwip220_tcp": "true", "lwip220_udp": "true", "lwip220_pbuf_pool_size": "256"}.items():
            domain.set_config("lib", param, value, lwip)
        platform_status = platform.build()
        print(f"PLATFORM_BUILD_STATUS={platform_status}", flush=True)
        if platform_status != 0:
            raise RuntimeError(f"平台构建失败：{platform_status}")
        xpfm = one_file((ws / plat_name).rglob("*.xpfm"), "平台XPFM")
        app = client.create_app_component(name=app_name, platform=str(xpfm), domain=dom_name, template="empty_application")
        # 全部源码来自权威checkout/有manifest的只读快照；不改用户源码。
        import_names = [p.name for p in sorted(app_src.iterdir())
                        if p.is_file() and p.suffix in {".c", ".h"} and p.name != "xparameters.h"]
        app.import_files(from_loc=str(app_src), files=import_names, dest_dir_in_cmp="src")
        if (ws / app_name / "src/xparameters.h").exists():
            raise RuntimeError("应用目录存在历史xparameters.h，拒绝覆盖当前XSA生成的BSP")
        app.set_app_config(key="USER_LINKER_SCRIPT", values=[str(linker)])
        app.set_app_config(key="USER_LINK_LIBRARIES", values=[lwip])
        app.set_app_config(key="USER_COMPILE_DEFINITIONS", values=["PLATFORM_ZYNQ"])
        app_status = app.build()
        print(f"APP_BUILD_STATUS={app_status}", flush=True)
        if app_status != 0:
            raise RuntimeError(f"应用构建失败：{app_status}")
        elf = one_file((ws / app_name).rglob("*.elf"), "应用ELF")
        fsbl = one_file((p for p in (ws / plat_name).rglob("*.elf") if "fsbl" in p.name.lower()), "新XSA的FSBL")
        export.mkdir(parents=True, exist_ok=True)
        shutil.copy2(elf, export / "dna_lwip_app.elf")
        shutil.copy2(fsbl, export / "fsbl.elf")
        # PS7初始化与bit必须来自同一XSA，不使用旧workspace内版本。
        with zipfile.ZipFile(xsa) as archive:
            bit_name = one_file_name(archive.namelist(), ".bit")
            bit = export / "top_bd_wrapper.bit"
            bit_bytes = archive.read(bit_name)
            if bit.exists() and bit.read_bytes() != bit_bytes:
                raise ValueError("已有独立bit与输入XSA不一致")
            if not bit.exists():
                bit.write_bytes(bit_bytes)
            ps7_names = [n for n in archive.namelist() if Path(n).name in {"ps7_init.tcl", "ps7_init.c", "ps7_init.h"}]
            if not any(Path(n).name == "ps7_init.tcl" for n in ps7_names):
                raise ValueError("XSA缺少ps7_init.tcl")
            for n in ps7_names:
                dst = export / Path(n).name
                content = archive.read(n)
                if dst.exists() and dst.read_bytes() != content:
                    raise ValueError(f"已有{dst.name}与XSA不一致")
                dst.write_bytes(content)
        exported_xsa = export / xsa.name
        if exported_xsa.exists() and sha256(exported_xsa) != sha256(xsa):
            raise ValueError("输出目录已有同名但不同的XSA")
        if exported_xsa != xsa:
            shutil.copy2(xsa, exported_xsa)
        bif = export / "boot.bif"
        bif.write_text('the_ROM_image:\n{\n  [bootloader] "' + str(export / "fsbl.elf").replace("\\", "/") + '"\n  "' + str(bit).replace("\\", "/") + '"\n  "' + str(export / "dna_lwip_app.elf").replace("\\", "/") + '"\n}\n')
        subprocess.run([str(bootgen), "-arch", "zynq", "-image", str(bif), "-o", str(export / "BOOT.bin"), "-w", "on"], cwd=export, check=True)
        boot = export / "BOOT.bin"
        if not boot.is_file() or boot.stat().st_size == 0:
            raise RuntimeError("Bootgen没有生成非空BOOT.bin")
        readback = subprocess.run([str(bootgen), "-arch", "zynq", "-read", str(boot)], cwd=export, check=True, capture_output=True)
        (export / "bootgen_readback.txt").write_bytes(readback.stdout + readback.stderr)
        inputs = {str((app_src / name).relative_to(root)).replace("\\", "/"): sha256(app_src / name) for name in import_names}
        inputs["sw/linker/lscript.ld"] = sha256(linker)
        summary = {"schema_version": 1, "scope": "software-build-only", "board_id": config["board_id"], "part": config["part"], "uart": config["uart"], "lwip": lwip, "tool_root": os.environ.get("XILINX_VITIS"), "input_xsa_sha256": sha256(xsa), "source_files": inputs, "artifacts": {p.name: sha256(p) for p in (export / "dna_lwip_app.elf", export / "fsbl.elf", boot, bit, exported_xsa, export / "ps7_init.tcl")}}
        (export / "software_build_config.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("SOFTWARE_BUILD_PASS (构建产物已核对；尚需新板完整manifest和板测)", flush=True)
    finally:
        vitis.dispose()


def one_file_name(names, suffix):
    hits = [name for name in names if name.endswith(suffix)]
    if len(hits) != 1:
        raise ValueError(f"XSA必须含唯一{suffix}，实际{hits}")
    return hits[0]


if __name__ == "__main__":
    config_path = os.environ.get("DNA_VITIS_CONFIG")
    if not config_path:
        raise ValueError("必须设置DNA_VITIS_CONFIG，禁止自动猜XSA/板/UART/workspace")
    run(json.loads(Path(config_path).read_text(encoding="utf-8-sig")))
