/******************************************************************************
 * test_wm_expand.c — 在主机上用黄金向量单元测试 PS 侧的水印展开逻辑
 *
 * 直接包含固件用的 sw/app/wm_expand.h（同一份代码，不是重新实现），
 * 输入是上位机会发送的打包水印，期望是 ../sim/golden/wm_regions.hex。
 * 水印的位序或区域几何一旦错了，Stage1 的比对结果就全无意义，
 * 而这种错误在板上极难定位——所以必须在这里钉死。
 *
 *   gcc -O2 -I sw/app -o /tmp/test_wm tools/test_wm_expand.c
 *   /tmp/test_wm ../sim/golden/watermark_packed.bin ../sim/golden/wm_regions.hex
 ******************************************************************************/
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "wm_expand.h"

#define NUM_LC   50u
#define STRIDE   807u
#define REF_LEN  957u
#define SYMBOLS  (NUM_LC * STRIDE + 150u)     /* 40,500 */
#define PACKED   ((SYMBOLS * 2u + 7u) / 8u)   /* 10,125 */

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "用法: %s <watermark_packed.bin> <wm_regions.hex>\n", argv[0]);
        return 2;
    }

    static unsigned char wm[PACKED + 16];
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror(argv[1]); return 2; }
    size_t n = fread(wm, 1, sizeof(wm), f);
    fclose(f);
    if (n < PACKED) {
        fprintf(stderr, "打包水印只有 %zu 字节，需要 %u 字节\n", n, PACKED);
        return 2;
    }
    printf("打包水印 %zu 字节（需要 %u），符号数 %u\n", n, PACKED, SYMBOLS);

    f = fopen(argv[2], "r");
    if (!f) { perror(argv[2]); return 2; }

    unsigned long total = 0, bad = 0;
    unsigned lc, row;
    for (lc = 0; lc < NUM_LC; lc++) {
        for (row = 0; row < REF_LEN; row++) {
            unsigned expect;
            if (fscanf(f, "%x", &expect) != 1) {
                fprintf(stderr, "期望文件在第 %lu 项处提前结束\n", total);
                fclose(f);
                return 2;
            }
            unsigned got = wm_region_symbol(wm, lc, row, STRIDE, SYMBOLS);
            if (got != expect) {
                if (bad < 8) {
                    printf("  ✗ 区域 %u 行 %u（符号 %u）: 得到 %u，期望 %u\n",
                           lc, row, lc * STRIDE + row, got, expect);
                }
                bad++;
            }
            total++;
        }
    }
    fclose(f);

    printf("--------------------------------------------------\n");
    if (bad == 0) {
        printf("✓ PASS  %lu 个符号全部与黄金向量一致（%u 区域 × %u 行）\n",
               total, NUM_LC, REF_LEN);
    } else {
        printf("✗ FAIL  %lu/%lu 个符号不符\n", bad, total);
    }
    printf("--------------------------------------------------\n");
    return bad == 0 ? 0 : 1;
}
