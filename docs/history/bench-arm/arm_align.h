/******************************************************************************
 * arm_align.h — 同片 ARM 纯软件 Stage1 基线（与 tools/align_omp.c 同一算法）
 *
 * 全局暴力滑窗：对 40,500 符号水印的每个位置 p ∈ [0, L-RB] 比对一条读段的
 * 正向与反向互补，取匹配碱基数最大者（并列取最小位置，与 align_omp.c 的 `c > best` 一致）。
 * 同一份代码在主机上编译作参考答案（tools/board/arm_baseline.py），在 Cortex-A9 上
 * 编译作被测对象，两边逐条比对 (s_fwd, p_fwd, s_rev, p_rev)。
 ******************************************************************************/
#ifndef ARM_ALIGN_H
#define ARM_ALIGN_H

#include <stdint.h>

#define AA_L    40500                        /* 水印符号数 */
#ifndef AA_RB
#define AA_RB   150                          /* 读长（SE150） */
#endif
#define AA_NWD  ((AA_RB + 63) / 64)
#define AA_NW   ((AA_L + 63) / 64 + AA_NWD + 1)

typedef struct {
    int32_t s_fwd, p_fwd, s_rev, p_rev;
} aa_result_t;

/* ref_sym: AA_L 个 2-bit 符号（每字节一个，取值 0..3） */
void aa_prepare_ref(const uint8_t *ref_sym);

/* read_sym: AA_RB 个符号；结果写入 *out */
void aa_align_read(const uint8_t *read_sym, aa_result_t *out);

#endif
