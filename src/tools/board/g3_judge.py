#!/usr/bin/env python3
"""复算 G3 的架构、系统与旧口径诊断判据。

在线调用由 tools/run_g3.sh 保存所有输出；``--offline-recheck`` 只读既有留证，
中间文件写入临时目录，不修改历史 run 目录，也不访问硬件。

三层语义（2026-10-14 main 更正后）：**架构判据与系统判据都须通过**才判 PASS。
架构判据回答「板端到底纠对了没有」（syndrome 是否全零），它挡住主机译码兜底；
系统判据回答「板端载荷出来的就是期望的那一份吗」，它挡住「合法但错误的码字」。
诊断层（主机译码 + SHA 的旧口径）只作记录，任何情况下都不参与裁决。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
CLIENT_DIR = REPO / "clients" / "python"
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))

from ldpc_pipeline import BoardCodeRejected, verify_board_result  # noqa: E402

DEFAULT_EXPECT_SHA = "fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_bits(run_dir: Path) -> Path:
    for name in ("dec_input_run1.txt", "dec_input.txt"):
        candidate = run_dir / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"{run_dir} 内没有 dec_input_run1.txt 或 dec_input.txt"
    )


def analyze(
    bits_path: Path,
    output_dir: Path,
    expect_sha: str,
    input_bytes: int | None,
    host_bits_out: Path | None = None,
    host_payload_out: Path | None = None,
    host_log_out: Path | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    board_dir = output_dir / "board"
    host_dir = output_dir / "host"
    host_dir.mkdir(parents=True, exist_ok=True)

    board_payload: Path | None = None
    failed_rows: int | None = None
    total_rows: int | None = None
    try:
        verified = verify_board_result(
            bits_path,
            board_dir,
            input_bytes=input_bytes,
            log=lambda _message: None,
        )
        architecture_status = "PASS"
        failed_rows = verified.failed_rows
        total_rows = verified.total_rows
        board_payload = verified.payload_path
    except BoardCodeRejected as rejected:
        architecture_status = "FAIL"
        failed_rows = rejected.failed_rows
        total_rows = rejected.total_rows

    host_bits = host_bits_out or (host_dir / "decoded_bits.txt")
    host_payload = host_payload_out or (
        host_dir / ("decoded_payload.bin" if input_bytes is not None else "decoded.jpg")
    )
    host_log = host_log_out or (host_dir / "ldpc_decode.log")
    host_bits.parent.mkdir(parents=True, exist_ok=True)
    host_payload.parent.mkdir(parents=True, exist_ok=True)
    host_log.parent.mkdir(parents=True, exist_ok=True)

    decode_args = [
        sys.executable,
        str(REPO / "tools" / "ldpc_decode.py"),
        "decode",
        str(bits_path),
        "-o",
        str(host_bits),
    ]
    if input_bytes is None:
        decode_args.extend(["--image", str(host_payload)])
    else:
        decode_args.extend(
            ["--payload", str(host_payload), "--input-bytes", str(input_bytes)]
        )
    with host_log.open("w", encoding="utf-8") as log_stream:
        host_process = subprocess.run(
            decode_args,
            cwd=REPO,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            check=False,
        )

    host_decode_ok = host_process.returncode == 0 and host_payload.is_file()
    host_sha = sha256(host_payload) if host_decode_ok else None
    host_log_text = host_log.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"起始失败校验\s*(\d+)[，,]\s*(\d+)\s*轮收敛", host_log_text)
    decoder_note = (
        f"起始 syndrome={match.group(1)}，主机译码迭代={match.group(2)}"
        if match
        else f"主机译码退出码={host_process.returncode}"
    )

    # 合法码字的系统载荷直接从 FPGA 回传码字提取。架构失败时，只为保留旧口径
    # 可比性，记录主机诊断译码能否得到目标 SHA；这个结果绝不改变架构裁决。
    if architecture_status == "PASS" and board_payload is not None:
        system_payload = board_payload
        system_source = "板端合法码字直接提取"
    elif host_decode_ok:
        system_payload = host_payload
        system_source = "PC 诊断译码输出（旧口径兜底，仅供比较）"
    else:
        system_payload = None
        system_source = "无可比较载荷"

    system_sha = sha256(system_payload) if system_payload is not None else None
    system_status = "PASS" if system_sha == expect_sha else "FAIL"
    legacy_status = "PASS" if host_decode_ok and host_sha == expect_sha else "FAIL"
    fallback_used = architecture_status == "FAIL" and host_decode_ok
    fallback_recovered = fallback_used and legacy_status == "PASS"

    # 【2026-10-14 main 更正：三层裁决 = 架构判据 **且** 系统判据】
    # 早先的写法只让架构判据决定裁决。那会放过一种**真实**错误：板端回传的是一个
    # **合法但错误**的码字——syndrome 全零（架构 PASS），可是从它载荷出来的字节
    # SHA 对不上期望（系统 FAIL）。结果是错的，却会被判 PASS。
    # 旧口径（run_g3.sh 开头的「只对译码后的板端回传作判定」）在这种情形下判 FAIL，
    # 所以「架构单独决定」是**比旧判据更宽**，不能接受。
    # 反过来，系统判据也**不能**在架构 FAIL 时独自救场——那正是要杜绝的 PC 兜底。
    # ⇒ 两者都过才是 PASS；诊断层（主机译码）任何情况下都不参与裁决。
    verdict = "PASS" if (architecture_status == "PASS" and system_status == "PASS") else "FAIL"

    return {
        "bits_path": str(bits_path),
        "architecture_status": architecture_status,
        "syndrome_failed_rows": failed_rows,
        "syndrome_total_rows": total_rows,
        "system_status": system_status,
        "system_sha256": system_sha,
        "system_source": system_source,
        "expect_sha256": expect_sha,
        "diagnostic_decoder": decoder_note,
        "diagnostic_exit_code": host_process.returncode,
        "diagnostic_sha256": host_sha,
        "legacy_status": legacy_status,
        "pc_fallback_used": fallback_used,
        "pc_fallback_recovered_expected_sha": fallback_recovered,
        "verdict": verdict,
    }


def render_report(result: dict[str, Any], title: str = "G3 三层判据") -> str:
    arch = result["architecture_status"]
    arch_note = (
        f"syndrome 非零行 {result['syndrome_failed_rows']}/{result['syndrome_total_rows']}"
        if arch == "FAIL"
        else f"syndrome 全零 {result['syndrome_failed_rows']}/{result['syndrome_total_rows']}"
    )
    system_sha = result["system_sha256"] or "无载荷"
    diagnostic_sha = result["diagnostic_sha256"] or "不可用"
    lines = [
        title,
        f"板端回传     : {result['bits_path']}",
        f"架构判据     : {arch} — {arch_note}",
        f"系统判据     : {result['system_status']} — SHA-256 {system_sha}；期望 {result['expect_sha256']}",
        f"系统载荷来源 : {result['system_source']}",
        f"诊断层       : {result['diagnostic_decoder']}；主机输出 SHA-256 {diagnostic_sha}",
        f"旧口径       : {result['legacy_status']} — 主机译码 + SHA-256",
    ]
    if result["pc_fallback_recovered_expected_sha"]:
        lines.append("PC 兜底标记  : 发生；系统 SHA 通过但架构判据未过，板端未纠对，整体判 FAIL")
    elif result["pc_fallback_used"]:
        lines.append("PC 兜底标记  : 已尝试主机译码，但未恢复期望 SHA；架构判据仍判 FAIL")
    else:
        lines.append("PC 兜底标记  : 未发生")
    if arch != "PASS":
        verdict_note = "架构判据未过：板端未纠对"
    elif result["system_status"] != "PASS":
        verdict_note = "系统判据未过：板端码字合法，但它载荷出的不是期望的那一份"
    else:
        verdict_note = "架构判据与系统判据均通过"
    lines.append(
        f"本次裁决     : {result['verdict']}（{verdict_note}；诊断层不参与裁决）"
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline-recheck", type=Path, help="只读复算已有 G3 留证目录")
    parser.add_argument("--bits", type=Path, help="板端回传 64,800 bit 文本")
    parser.add_argument("--expect-sha", default=DEFAULT_EXPECT_SHA)
    parser.add_argument("--input-bytes", type=int)
    parser.add_argument("--output-dir", type=Path, help="在线运行时三层产物目录")
    parser.add_argument("--json-out", type=Path, help="写入供 run_g3.sh 汇总的 JSON")
    parser.add_argument("--host-bits-out", type=Path)
    parser.add_argument("--host-payload-out", type=Path)
    parser.add_argument("--host-log-out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    expect_sha = args.expect_sha.lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expect_sha):
        print("--expect-sha 必须是 64 位十六进制 SHA-256", file=sys.stderr)
        return 2

    if args.offline_recheck is not None:
        if any(
            value is not None
            for value in (
                args.bits,
                args.output_dir,
                args.json_out,
                args.host_bits_out,
                args.host_payload_out,
                args.host_log_out,
            )
        ):
            print("--offline-recheck 不接受输出路径参数；复算产物会写入临时目录", file=sys.stderr)
            return 2
        run_dir = args.offline_recheck.resolve()
        try:
            bits_path = find_bits(run_dir)
        except (FileNotFoundError, OSError) as exc:
            print(f"离线留证不可用：{exc}", file=sys.stderr)
            return 2
        with tempfile.TemporaryDirectory(prefix="g3-offline-recheck-") as temp_dir:
            result = analyze(
                bits_path,
                Path(temp_dir),
                expect_sha,
                args.input_bytes,
            )
        print(render_report(result, f"G3 三层离线复算：{run_dir.name}"))
        return 0 if result["verdict"] == "PASS" else 1

    if args.bits is None or args.output_dir is None or args.json_out is None:
        print("在线分析需要 --bits、--output-dir 和 --json-out", file=sys.stderr)
        return 2
    try:
        result = analyze(
            args.bits.resolve(),
            args.output_dir.resolve(),
            expect_sha,
            args.input_bytes,
            args.host_bits_out,
            args.host_payload_out,
            args.host_log_out,
        )
    except Exception as exc:
        print(f"G3 三层判据计算失败：{exc}", file=sys.stderr)
        return 2

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(render_report(result))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
