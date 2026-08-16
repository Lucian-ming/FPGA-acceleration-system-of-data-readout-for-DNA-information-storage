/* =============================================================
 * test_ddr_layout.c — ddr_layout.h 的主机单元测试（C2/C3 判据）
 *
 * 与固件共用 sw/app/ddr_layout.h；地址与容量按 docs/05-interfaces.md
 * 的 DDR 布局取黄金值，钉死四类边界：空任务、非整帧、超容量、区间越界。
 *
 *   gcc -O2 -I sw/app -o /tmp/test_ddr tools/test_ddr_layout.c && /tmp/test_ddr
 * ============================================================= */
#include <stdio.h>
#include "ddr_layout.h"

/* 与 sw/app/echo.h 一致的布局（此处为测试黄金值，固件侧以宏传入） */
#define READS_BASE   0x10100000UL
#define READS_LIMIT  0x10600000UL   /* = Stage1 输出区起点 */
#define STAGE1_BASE  0x10600000UL
#define STAGE1_LIMIT 0x11000000UL   /* = Voter 输出区起点 */
#define BYTES_PER_READ    40UL
#define BYTES_PER_RESULT  48UL
#define FRAME_READS       64UL
#define MAX_RECORDS       108000UL

static int check(unsigned long records, int expect_rc)
{
    int rc = ddr_layout_validate(records, FRAME_READS, MAX_RECORDS,
                                 READS_BASE, READS_LIMIT,
                                 STAGE1_BASE, STAGE1_LIMIT,
                                 BYTES_PER_READ, BYTES_PER_RESULT);
    int ok = (rc == expect_rc);
    printf("  records=%-7lu  rc=%-3d  期望=%-3d  %s\n",
           records, rc, expect_rc, ok ? "✓" : "✗");
    return ok;
}

int main(void)
{
    int fail = 0;

    printf("== ddr_layout 校验（方案B 调试流 / 全量流 / 非法输入）==\n");
    /* 合法任务 */
    fail += !check(4096UL,    0);   /* 调试流：2,048 读段 × 2 方向 */
    fail += !check(6400UL,    0);   /* SE250 调试流规模 */
    fail += !check(103616UL,  0);   /* 全量 51,781×2 补齐到 64 倍数 */
    fail += !check(107968UL,  0);   /* 预留容量内最大的 64 对齐条数（64×1687） */
    /* 非法任务 */
    fail += !check(0UL,       -1);  /* 空任务 */
    fail += !check(100UL,     -2);  /* 非 64 整数倍（C2） */
    fail += !check(103562UL,  -2);  /* 全量未补零的原始条数 */
    fail += !check(108000UL,  -2);  /* 历史 TOTAL_READS 宏本身不是 64 的倍数
                                       （108000 = 64×1687 + 32），只当容量上限用 */
    fail += !check(108032UL,  -3);  /* 64 对齐但超出预留容量（64×1688） */
    fail += !check(135168UL,  -3);  /* 远超容量 */

    printf("== 字节数计算 ==\n");
    unsigned long b1 = ddr_layout_reads_bytes(4096UL, BYTES_PER_READ);
    unsigned long b2 = ddr_layout_stage1_bytes(4096UL, BYTES_PER_RESULT);
    printf("  4,096 条：读段 %lu B，Stage1 输出 %lu B %s\n", b1, b2,
           (b1 == 163840UL && b2 == 196608UL) ? "✓" : "✗");
    if (b1 != 163840UL || b2 != 196608UL) fail++;

    printf("--------------------------------------------------\n");
    if (fail == 0)
        printf("✓ PASS  ddr_layout 全部判据通过\n");
    else
        printf("✗ FAIL  %d 项不符\n", fail);
    return fail ? 1 : 0;
}
