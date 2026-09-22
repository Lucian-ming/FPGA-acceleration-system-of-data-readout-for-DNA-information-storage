/******************************************************************************
 * main_host.c — 同片 ARM 基线的主机参考入口：与 main_bm.c 用同一份 arm_align.c，
 * 在 x86 上算出每条读段的 (s_fwd, p_fwd, s_rev, p_rev) 作逐条比对的参考答案。
 *   用法: arm_align_host <ref.bin> <reads.bin> <n_reads> <out.bin>
 ******************************************************************************/
#include <stdio.h>
#include <stdlib.h>
#include "arm_align.h"

int main(int argc, char **argv)
{
    if (argc < 5) { fprintf(stderr, "usage: %s ref.bin reads.bin n out.bin\n", argv[0]); return 2; }
    static uint8_t ref[AA_L];
    FILE *f = fopen(argv[1], "rb");
    if (!f || fread(ref, 1, AA_L, f) != AA_L) { perror("ref"); return 1; }
    fclose(f);
    int n = atoi(argv[3]);
    uint8_t *rd = malloc((size_t)n * AA_RB);
    aa_result_t *res = malloc((size_t)n * sizeof(aa_result_t));
    f = fopen(argv[2], "rb");
    if (!f || fread(rd, 1, (size_t)n * AA_RB, f) != (size_t)n * AA_RB) { perror("reads"); return 1; }
    fclose(f);
    aa_prepare_ref(ref);
    for (int i = 0; i < n; i++) aa_align_read(rd + (size_t)i * AA_RB, &res[i]);
    f = fopen(argv[4], "wb");
    if (!f || fwrite(res, sizeof(aa_result_t), (size_t)n, f) != (size_t)n) { perror("out"); return 1; }
    fclose(f);
    free(rd); free(res);
    return 0;
}
