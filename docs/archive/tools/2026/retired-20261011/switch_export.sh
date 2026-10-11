#!/usr/bin/env bash
# =============================================================================
# tools/switch_export.sh
#
# 在 SE150 与 SE250 导出制品之间一键快速切换，并同步更新头文件参数与校验和。
# =============================================================================
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

TARGET="${1:-}"

if [[ "$TARGET" != "se150" && "$TARGET" != "se250" ]]; then
    echo "用法: $0 {se150|se250}"
    exit 1
fi

SRC_DIR="hw/build/export/archive/${TARGET}"
if [[ ! -d "$SRC_DIR" ]]; then
    echo "错误: 归档目录 ${SRC_DIR} 不存在！"
    exit 1
fi

echo "=== 正在切换至 ${TARGET} 规格制品 ==="

# 1. 拷贝归档制品覆盖到 export/ 顶层
cp -a "${SRC_DIR}/BOOT.bin" hw/build/export/
cp -a "${SRC_DIR}/top_bd_wrapper.bit" hw/build/export/
cp -a "${SRC_DIR}/dna_lwip_app_b27.elf" hw/build/export/
cp -a "${SRC_DIR}/dna_accel.xsa" hw/build/export/
cp -a "${SRC_DIR}/fsbl.elf" hw/build/export/
cp -a "${SRC_DIR}/SHA256SUMS" hw/build/export/
if [[ -d "${SRC_DIR}/reports" ]]; then
    cp -a "${SRC_DIR}/reports" hw/build/export/
fi

# 2. 切换 echo.h 参数
if [[ "$TARGET" == "se150" ]]; then
    sed -i 's/#define READ_BASES_PER_READ     250U/#define READ_BASES_PER_READ     150U/' sw/app/echo.h
    sed -i 's/#define READ_SIZE_BYTES         64U/#define READ_SIZE_BYTES         40U/' sw/app/echo.h
    sed -i 's/#define TOTAL_READS             129600U/#define TOTAL_READS             108000U/' sw/app/echo.h
    sed -i 's/#define WM_STRIDE               805U/#define WM_STRIDE               807U/' sw/app/echo.h
    sed -i 's/#define WM_REF_LEN              1055U/#define WM_REF_LEN              957U/' sw/app/echo.h
    sed -i 's/#define WM_SYMBOLS              (WM_NUM_LC \* WM_STRIDE + 250U)/#define WM_SYMBOLS              (WM_NUM_LC * WM_STRIDE + 150U)/' sw/app/echo.h
    sed -i 's/#define DDR_DNA_ACC_OUT_BASE    0x10900000U/#define DDR_DNA_ACC_OUT_BASE    0x10600000U/' sw/app/echo.h
    sed -i 's/#define DDR_VOTER_OUT_BASE      0x11200000U/#define DDR_VOTER_OUT_BASE      0x11000000U/' sw/app/echo.h
    sed -i 's/#define DDR_DECODER_OUT_BASE    0x11300000U/#define DDR_DECODER_OUT_BASE    0x11100000U/' sw/app/echo.h
    sed -i 's/#define DNA_ACC_RESULT_PACKED_BYTES  72U/#define DNA_ACC_RESULT_PACKED_BYTES  48U/' sw/app/echo.h
    sed -i 's/#define VOTER_INPUT_BYTES_PER_READ   72U/#define VOTER_INPUT_BYTES_PER_READ   48U/' sw/app/echo.h
    sed -i 's/#define VOTER_SCORE_MIN         112U/#define VOTER_SCORE_MIN         67U/' sw/app/echo.h
else
    sed -i 's/#define READ_BASES_PER_READ     150U/#define READ_BASES_PER_READ     250U/' sw/app/echo.h
    sed -i 's/#define READ_SIZE_BYTES         40U/#define READ_SIZE_BYTES         64U/' sw/app/echo.h
    sed -i 's/#define TOTAL_READS             108000U/#define TOTAL_READS             129600U/' sw/app/echo.h
    sed -i 's/#define WM_STRIDE               807U/#define WM_STRIDE               805U/' sw/app/echo.h
    sed -i 's/#define WM_REF_LEN              957U/#define WM_REF_LEN              1055U/' sw/app/echo.h
    sed -i 's/#define WM_SYMBOLS              (WM_NUM_LC \* WM_STRIDE + 150U)/#define WM_SYMBOLS              (WM_NUM_LC * WM_STRIDE + 250U)/' sw/app/echo.h
    sed -i 's/#define DDR_DNA_ACC_OUT_BASE    0x10600000U/#define DDR_DNA_ACC_OUT_BASE    0x10900000U/' sw/app/echo.h
    sed -i 's/#define DDR_VOTER_OUT_BASE      0x11000000U/#define DDR_VOTER_OUT_BASE      0x11200000U/' sw/app/echo.h
    sed -i 's/#define DDR_DECODER_OUT_BASE    0x11100000U/#define DDR_DECODER_OUT_BASE    0x11300000U/' sw/app/echo.h
    sed -i 's/#define DNA_ACC_RESULT_PACKED_BYTES  48U/#define DNA_ACC_RESULT_PACKED_BYTES  72U/' sw/app/echo.h
    sed -i 's/#define VOTER_INPUT_BYTES_PER_READ   48U/#define VOTER_INPUT_BYTES_PER_READ   72U/' sw/app/echo.h
    sed -i 's/#define VOTER_SCORE_MIN         67U/#define VOTER_SCORE_MIN         112U/' sw/app/echo.h
fi

cp -a sw/app/echo.h sw/workspace/dna_lwip_app_b27/src/echo.h

# 3. 校验 export/ 下 SHA256SUMS
(cd hw/build/export && sha256sum -c SHA256SUMS)

echo "=== 切换完成：当前已激活 ${TARGET} 规格制品与固件配置 ==="

