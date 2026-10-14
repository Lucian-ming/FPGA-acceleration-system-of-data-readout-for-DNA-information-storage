#!/usr/bin/env bash
# =============================================================================
# tools/test_ldpc_perm.sh —— 在 x86 上逐位核验 PS 侧的置换，**不需要板子**
#
# 为什么要有它
# ------------
# 板端缺解交织这个缺陷，在板上表现为「核不收敛」——信号弱、定位慢，而且每次试错
# 都要走一趟「重编 ELF → 烧录 → 跑 G3」。置换是纯数据变换，**它可以在主机上
# 被穷尽核验**：拿真实的 8,100 字节 buffer 跑一遍 C 实现，与 Python 参考实现
# （clients/python/native_ldpc.py 的 deinterleave）逐位比对。
#
# 本脚本做三件事：
#   1. 重新生成 sw/app/ldpc_perm_table.c 并确认它与源表一致（--check）；
#   2. 编 C 实现（sw/app/ldpc_perm.c + 生成的表）成一个**独立**主机程序，
#      与 Python 在真实样本上逐位比对：deinterleave、interleave、往返、边界模式；
#   3. 任何一项不符即 FAIL。
#
# 边界
# ----
# 本脚本只证明「置换的 C 实现 == Python 参考实现」。
# **不证明**它在板上跑得对——那要 G3 + 串口出现 converged=1（L7 的判据）。
# =============================================================================
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

BUILD="${TMPDIR:-/tmp}/ldpc-perm-test"
mkdir -p "$BUILD"
PASS=0; FAIL=0
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }

echo "=== 0/3 表与源表一致性 ==="
if python3 tools/gen_ldpc_perm_table.py --check; then ok "ldpc_perm_table.c 与 permutation64800 一致"
else bad "ldpc_perm_table.c 不是最新的（跑 python3 tools/gen_ldpc_perm_table.py 重新生成）"; fi

echo
echo "=== 1/3 编主机版 C 实现 ==="
cat > "$BUILD/main.c" <<'EOF'
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ldpc_perm.h"

int main(int argc, char **argv)
{
    const char *mode;
    if (argc != 3) { fprintf(stderr, "用法: perm <deinterleave|interleave|roundtrip> <8100B>\n"); return 2; }
    mode = argv[1];
    FILE *f = fopen(argv[2], "rb");
    unsigned char in[8100], out[8100];
    if (!f) { fprintf(stderr, "打不开 %s\n", argv[2]); return 2; }
    if (fread(in, 1, 8100, f) != 8100) { fprintf(stderr, "输入不足 8100 字节\n"); return 2; }
    fclose(f);

    if (!strcmp(mode, "deinterleave"))      ldpc_perm_deinterleave(in, out);
    else if (!strcmp(mode, "interleave"))   ldpc_perm_interleave(in, out);
    else if (!strcmp(mode, "roundtrip")) {
        ldpc_perm_deinterleave(in, out);
        memcpy(in, out, 8100);
        ldpc_perm_interleave(in, out);
    } else { fprintf(stderr, "未知模式 %s\n", mode); return 2; }

    fwrite(out, 1, 8100, stdout);
    return 0;
}
EOF

if gcc -O2 -Wall -Wextra -Isw/app -o "$BUILD/perm" \
       "$BUILD/main.c" sw/app/ldpc_perm.c sw/app/ldpc_perm_table.c 2> "$BUILD/cc.log"; then
    ok "编译通过（gcc -O2 -Wall -Wextra，无平台依赖）"
else
    bad "编译失败"; sed 's/^/    /' "$BUILD/cc.log"; fi

if grep -qiE "warning" "$BUILD/cc.log"; then bad "有编译告警（按项目口径不得静默带过）"; sed 's/^/    /' "$BUILD/cc.log"; fi

echo
echo "=== 2/3 与 Python 参考实现逐位比对（真实样本 + 边界模式）==="
if [ -x "$BUILD/perm" ]; then
python3 - "$BUILD/perm" "$BUILD" <<'PY'
import subprocess, sys, pathlib, hashlib
import numpy as np
sys.path.insert(0, 'clients/python')
import native_ldpc as L

binary, work = sys.argv[1], pathlib.Path(sys.argv[2])
perm = L.load_permutation(pathlib.Path('clients/python/resources/permutation64800'))
inv = np.empty(perm.size, np.int64); inv[perm] = np.arange(perm.size)

def pack_lsb(bits):                      # 位 k -> byte[k>>3] 的第 (k&7) 位
    return np.packbits(bits.reshape(-1,8), bitorder="little").tobytes()

def unpack_lsb(raw):
    return np.unpackbits(np.frombuffer(raw, np.uint8), bitorder="little")

def run(mode, raw):
    r = subprocess.run([binary, mode, "-"], input=raw, capture_output=True)
    assert r.returncode == 0, r.stderr.decode()

def run_file(mode, raw, tmp):
    tmp.write_bytes(raw)
    r = subprocess.run([binary, mode, str(tmp)], capture_output=True)
    assert r.returncode == 0, r.stderr.decode()
    return r.stdout

tmp = work / "in.bin"
cases = []

# 真实样本：本轮板上那份输入
real = pathlib.Path('/mnt/d/bkb220_board_smoke/g3_runs/20261014T110319Z/dec_input_run1.txt')
if real.is_file():
    rx = np.array([1 if c == '1' else 0 for c in real.read_text().strip()], np.uint8)
    cases.append(("板端真实输入(20261014T110319Z)", rx))
else:
    print("  （跳过板端真实样本：留证目录不可见）")

rng = np.random.default_rng(20261014)
cases.append(("随机 rx", rng.integers(0, 2, 64800, dtype=np.uint8)))
cases.append(("全 0",    np.zeros(64800, np.uint8)))
cases.append(("全 1",    np.ones(64800, np.uint8)))
alt = np.zeros(64800, np.uint8); alt[::2] = 1
cases.append(("交替 01", alt))

fails = 0
for name, rx in cases:
    raw = pack_lsb(rx)
    want_nat  = pack_lsb(L.deinterleave(rx, perm))
    got_nat   = run_file("deinterleave", raw, tmp)
    ok_nat = (got_nat == want_nat)

    # Python 侧没有 interleave 函数，按定义 rx[i] = natural[perm[i]] 直接算
    nat = unpack_lsb(want_nat)
    want_rx = pack_lsb(nat[perm])
    got_rx = run_file("interleave", want_nat, tmp)
    ok_rx = (got_rx == want_rx)

    got_rt = run_file("roundtrip", raw, tmp)
    ok_rt = (got_rt == raw)

    status = ok_nat and ok_rx and ok_rt
    fails += (0 if status else 1)
    print(f"  {'✓' if status else '✗'} {name:34s} deinterleave={'OK' if ok_nat else 'MISMATCH'}"
          f"  interleave={'OK' if ok_rx else 'MISMATCH'}  往返={'OK' if ok_rt else 'MISMATCH'}")
    if not status:
        if not ok_nat:
            d = np.flatnonzero(unpack_lsb(got_nat) != unpack_lsb(want_nat))
            print(f"      deinterleave 首个不符位 {d[0] if d.size else '-'}，不符 {d.size} 位")
        if not ok_rx:
            d = np.flatnonzero(unpack_lsb(got_rx) != unpack_lsb(want_rx))
            print(f"      interleave   首个不符位 {d[0] if d.size else '-'}，不符 {d.size} 位")

print(f"  比对结论：{len(cases)} 组，失败 {fails} 组")
sys.exit(1 if fails else 0)
PY
    if [ $? -eq 0 ]; then ok "C 实现与 Python 参考逐位一致（含往返）"; else bad "与 Python 参考不一致"; fi
fi

echo
echo "=================================================="
if [ "$FAIL" -eq 0 ]; then
    printf '\033[32m置换单元测试 PASS\033[0m（仅证明 C 实现 == Python 参考；板上正确性仍须 L7/G3）\n'
    exit 0
else
    printf '\033[31m置换单元测试 FAIL（%d 项）\033[0m\n' "$FAIL"
    exit 1
fi
