#!/usr/bin/env python3
"""G3 制品包静态门禁；只读核验，--stage 时才复制到指定新 run 目录。"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

GEOMETRY = ("READ_BPS", "NUM_LC", "STRIDE", "REF_LEN", "BATCH")
PARAMS = GEOMETRY + ("C_STAGE1_P_WAYS", "C_STAGE1_PIPE_TREE")
REQUIRED_ARTIFACT_KEYS = ("bit", "xsa", "elf", "fsbl", "boot")

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def bundle_path(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError(f"制品路径越出所选目录: {name}")
    if not path.is_file():
        raise ValueError(f"制品路径不存在或越出所选目录: {name}")
    return path

def check_sums(root: Path) -> dict[str, str]:
    sums = {}
    for line in bundle_path(root, "SHA256SUMS").read_text().splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
        if not match:
            raise ValueError("SHA256SUMS 格式错误")
        digest, name = match.groups()
        if name in sums:
            raise ValueError(f"SHA256SUMS 重复项: {name}")
        if sha(bundle_path(root, name)) != digest.lower():
            raise ValueError(f"SHA256SUMS 校验失败: {name}")
        sums[name] = digest.lower()
    return sums

def inspect_xsa(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        # 只接受唯一 PS 初始化和完整 bit；不任意选 zip 内第一份同名文件。
        def unique(suffix):
            names = [n for n in archive.namelist() if n.split("/")[-1] == suffix]
            if len(names) != 1:
                raise ValueError(f"XSA 应含唯一 {suffix}，实际 {len(names)}")
            return names[0]
        ps7 = archive.read(unique("ps7_init.tcl"))
        info = json.loads(archive.read(unique("xsa.json")))
        parts = [d.get("part", {}).get("name") for d in info.get("devices", [])]
        if len(parts) != 1 or not parts[0]:
            raise ValueError("XSA 缺少唯一完整器件 part")
        part = parts[0].lower()
        bit_names = [f["name"] for f in info.get("files", []) if f.get("type") == "FULL_BIT"]
        if len(bit_names) != 1:
            raise ValueError("XSA 缺少唯一 FULL_BIT")
        bit = archive.read(bit_names[0])
        hwh_names = [n for n in archive.namelist() if n.endswith(".hwh")]
        if len(hwh_names) != 1:
            raise ValueError("XSA 缺少唯一 HWH")
        hwh = ET.fromstring(archive.read(hwh_names[0]))
        system = hwh.find("SYSTEMINFO")
        if system is None:
            raise ValueError("XSA HWH 缺少 SYSTEMINFO")
        actual = "xc" + system.get("DEVICE", "") + system.get("PACKAGE", "") + system.get("SPEEDGRADE", "")
        if not re.fullmatch(r"xc7z\d{3}[a-z]+\d+-[123](?:[a-z])?", part):
            raise ValueError(f"XSA part格式无效: {part}")
        if actual.lower() != part:
            raise ValueError(f"XSA JSON/HWH part 不一致: {part} / {actual}")
        cores = [m for m in hwh.iter("MODULE") if m.get("MODTYPE") == "Dna_accelerator_core"]
        if len(cores) != 1:
            raise ValueError("XSA 缺少唯一生产 Dna_accelerator_core")
        values = {p.get("NAME"): p.get("VALUE") for p in cores[0].iter("PARAMETER")}
        params = {p: int(values[p], 0) for p in PARAMS if p in values}
        if any(p not in params for p in GEOMETRY):
            raise ValueError("XSA HWH 缺少生产几何参数")
        return {"part": part, "parameters": params, "ps7": ps7,
                "bit_sha256": hashlib.sha256(bit).hexdigest(),
                "tool_version": info.get("generatedVersion")}

def validate(root: Path, *, device=None, read_bps=150,
             bit_override=None, elf_override=None) -> dict:
    root = root.resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("缺 manifest.json；拒绝接受无清单制品包")
    sums = check_sums(root)
    if "manifest.json" not in sums:
        raise ValueError("manifest.json 未被 SHA256SUMS 覆盖")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("manifest schema_version 必须为 1")
    files = manifest.get("artifacts", {})
    if not isinstance(files, dict) or set(REQUIRED_ARTIFACT_KEYS) - set(files):
        raise ValueError("manifest 缺 bit/xsa/elf/fsbl/boot 完整制品")
    source = manifest.get("source_manifest", {})
    if not source.get("path") or source.get("sha256") != sums.get(source["path"]):
        raise ValueError("缺少被 SHA256SUMS 覆盖的 source_manifest 及其哈希")
    source_data = json.loads(bundle_path(root, source["path"]).read_text())
    source_files = source_data.get("files")
    if not isinstance(source_files, dict) or not source_files:
        raise ValueError("source_manifest.files 必须是非空相对路径->SHA256字典")
    for name, digest in source_files.items():
        if not isinstance(name, str) or not name or Path(name).is_absolute() or ".." in Path(name).parts or "\\" in name or ":" in name:
            raise ValueError("source_manifest包含非法源码相对路径")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("source_manifest包含非法SHA256")
    versions = manifest.get("tool_versions")
    if not isinstance(versions, dict) or not versions or any(not isinstance(k,str) or not k or not isinstance(v,str) or not v.strip() for k,v in versions.items()):
        raise ValueError("tool_versions必须为非空工具名->版本字符串字典")
    if any(not re.fullmatch(r"20\d{2}\.\d+(?:\.\d+)?",versions.get(k,"")) for k in ("vivado","vitis")):
        raise ValueError("tool_versions缺少可核验vivado/vitis版本(如2026.1)")
    if not manifest.get("board_id"):
        raise ValueError("manifest 缺 board_id/tool_versions")
    paths = {k: bundle_path(root, files[k]) for k in REQUIRED_ARTIFACT_KEYS}
    for name in files.values():
        if name not in sums:
            raise ValueError(f"制品未被 SHA256SUMS 覆盖: {name}")
    actual = inspect_xsa(paths["xsa"])
    if manifest["tool_versions"]["vivado"] != actual["tool_version"]:
        raise ValueError("manifest Vivado版本与XSA generatedVersion不符")
    if manifest.get("part", "").lower() != actual["part"]:
        raise ValueError("manifest part 与 XSA 实际 part 不符")
    expected = manifest.get("parameters", {})
    if any(p not in expected or int(expected[p]) != actual["parameters"].get(p) for p in PARAMS):
        raise ValueError("manifest 参数与 XSA HWH 不符或缺少 P_WAYS/PIPE_TREE 证据")
    if device and not (actual["part"] == device.lower() or re.match(r"^xc7z\d{3}$", device.lower()) and actual["part"].startswith(device.lower())):
        raise ValueError(f"目标器件 {device} 与 XSA {actual['part']} 不符")
    if actual["parameters"]["READ_BPS"] != read_bps:
        raise ValueError("任务 read_bps 与 XSA 不符")
    if actual["parameters"]["BATCH"] != 64:
        raise ValueError("G3 当前只支持 BATCH=64 制品")
    geometry = tuple(actual["parameters"][p] for p in GEOMETRY)
    required_geometry = {150:(150,50,807,957,64),250:(250,50,805,1055,64)}
    if geometry != required_geometry.get(read_bps):
        raise ValueError(f"G3正式生产几何不符: {geometry}，禁止简化LC6制品用于真板验收")
    architecture=(actual["parameters"]["C_STAGE1_P_WAYS"],actual["parameters"]["C_STAGE1_PIPE_TREE"])
    if architecture not in ((4,0),(16,1)):
        raise ValueError("G3只接受P4/0或P16/1生产架构")
    if architecture==(16,1) and actual["part"].startswith("xc7z010"):
        raise ValueError("XC7Z010禁止P16生产制品")
    if bit_override and Path(bit_override).resolve() != paths["bit"]:
        raise ValueError("单独覆盖 bit 会混用 XSA；请生成完整制品包并用 --artifact-dir")
    if elf_override and Path(elf_override).resolve() != paths["elf"]:
        raise ValueError("单独覆盖 ELF 缺同源证据；请生成完整制品包并用 --artifact-dir")
    if sha(paths["bit"]) != actual["bit_sha256"]:
        raise ValueError("独立 bit 与所选 XSA 内置 bit 不符")
    return {"artifact_dir": str(root), "board_id": manifest["board_id"],
            "part": actual["part"], "device": re.match(r"xc7z\d{3}", actual["part"]).group(),
            "parameters": actual["parameters"], "xsa_tool_version": actual["tool_version"],
            "artifacts": {k: str(v) for k, v in paths.items()},
            "hashes": {k: sha(v) for k, v in paths.items()},
            "manifest_sha256": sha(manifest_path),
            "provenance_note": "哈希核验证明制品包一致性；不独立证明构建日志与源码的因果关系，须审查构建源manifest及日志。",
            "_ps7": actual["ps7"]}

def normalize_windows_path(value: str) -> tuple[str, str]:
    value = value.replace("\\", "/").rstrip("/")
    if re.match(r"^[A-Za-z]:/", value):
        return value[0].upper() + value[1:], "/mnt/" + value[0].lower() + value[2:]
    if re.match(r"^/mnt/[a-z]/", value):
        return value[5].upper() + ":" + value[6:], value
    raise ValueError("Windows 工具/留证路径必须是盘符绝对路径或 /mnt/<盘符>/ 路径")

def choose_uart(devices: list[dict], explicit: str | None = None) -> str:
    # FT4232HL 会有多条 COM，必须人工辨认 PS 一路；只在唯一 USB COM 时自动选择。
    eligible = []
    for dev in devices:
        ident = dev.get("InstanceId", "").upper()
        name = dev.get("FriendlyName", "")
        match = re.search(r"\bCOM\d+\b", name, re.I)
        if match and (ident.startswith("USB\\") or ident.startswith("FTDIBUS\\")) and "BTH" not in ident:
            eligible.append(match.group().upper())
    eligible = sorted(set(eligible))
    if explicit:
        if not re.fullmatch(r"COM\d+", explicit, re.I) or explicit.upper() not in eligible:
            raise ValueError(f"显式串口 {explicit} 不是当前可用 USB/FTDI 串口；可选 {eligible}")
        return explicit.upper()
    if len(eligible) != 1:
        raise ValueError(f"不能唯一确定 PS USB串口，可选 {eligible}；请显式 --uart-port COMx，禁止蓝牙/COM6兜底")
    return eligible[0]

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifact-dir", required=True)
    ap.add_argument("--device")
    ap.add_argument("--read-bps", type=int, default=150)
    ap.add_argument("--bit")
    ap.add_argument("--elf")
    ap.add_argument("--stage", type=Path)
    args = ap.parse_args()
    try:
        result = validate(Path(args.artifact_dir), device=args.device, read_bps=args.read_bps,
                          bit_override=args.bit, elf_override=args.elf)
        ps7 = result.pop("_ps7")
        if args.stage:
            source_root=Path(args.artifact_dir).resolve()
            dest_root=args.stage.resolve()
            try:
                dest_root.relative_to(source_root)
            except ValueError:
                pass
            else:
                raise ValueError("--stage不得等于制品目录或位于其内部")
            if dest_root.exists() and any(dest_root.iterdir()):
                # shell会预先将 stdout 打开为 artifact_selection.out；仅允许此留证文件。
                if any(p.name != "artifact_selection.out" for p in dest_root.iterdir()):
                    raise ValueError("--stage必须是新空run目录，禁止覆盖已有证据")
            args.stage.mkdir(parents=True, exist_ok=True)
            for key, dest in (("bit", "top_bd_wrapper.bit"), ("elf", "dna_lwip_app.elf"), ("xsa", "dna_accel.xsa")):
                shutil.copy2(result["artifacts"][key], args.stage / dest)
            (args.stage / "ps7_init.tcl").write_bytes(ps7)
            (args.stage / "artifact_selection.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            for name in ("manifest.json", "SHA256SUMS"):
                src = Path(args.artifact_dir) / name
                if src.is_file(): shutil.copy2(src, args.stage / name)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile, ET.ParseError) as error:
        print(f"G3 制品门禁失败: {error}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
