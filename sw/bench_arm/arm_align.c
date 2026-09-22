/******************************************************************************
 * arm_align.c — 同片 ARM 纯软件 Stage1 基线的比对核心，见 arm_align.h
 *
 * 与 tools/align_omp.c 逐行同构（位平面 + 按位置移窗 + popcount），只改两处：
 *   1) 在 ARMv7 + NEON 上用 vcnt 做 popcount（GCC 对 __builtin_popcountll 在 ARMv7
 *      会退化成库调用 __popcountdi2，不是公平的「优化实现」）；
 *   2) 不用 OpenMP：裸机单核。Cortex-A9 双核的第二核留给后续（结论里按单核报告）。
 ******************************************************************************/
#include "arm_align.h"

#if defined(__ARM_NEON) || defined(__ARM_NEON__)
#include <arm_neon.h>
static inline uint32_t aa_popcnt64(uint64_t x)
{
    uint8x8_t  c8  = vcnt_u8(vcreate_u8(x));
    uint16x4_t c16 = vpaddl_u8(c8);
    uint32x2_t c32 = vpaddl_u16(c16);
    uint64x1_t c64 = vpaddl_u32(c32);
    return (uint32_t)vget_lane_u64(c64, 0);
}
#else
static inline uint32_t aa_popcnt64(uint64_t x) { return (uint32_t)__builtin_popcountll(x); }
#endif

static uint64_t rh[AA_NW], rl[AA_NW];

void aa_prepare_ref(const uint8_t *ref_sym)
{
    for (int i = 0; i < AA_NW; i++) { rh[i] = 0; rl[i] = 0; }
    for (int i = 0; i < AA_L; i++) {
        if (ref_sym[i] >> 1) rh[i >> 6] |= 1ULL << (i & 63);
        if (ref_sym[i] & 1)  rl[i >> 6] |= 1ULL << (i & 63);
    }
}

static inline void getwin(const uint64_t *a, int p, uint64_t *o)
{
    int w = p >> 6, s = p & 63;
    for (int k = 0; k < AA_NWD; k++) {
        o[k] = s ? ((a[w + k] >> s) | (a[w + k + 1] << (64 - s))) : a[w + k];
    }
}

static int align_one(const uint64_t *ah, const uint64_t *al, int *bp)
{
    uint64_t th[AA_NWD], tl[AA_NWD];
    int best = -1, b = 0;
    const int rem = AA_RB - 64 * (AA_NWD - 1);
    const uint64_t mlast = (rem == 64) ? ~0ULL : ((1ULL << rem) - 1);

    for (int p = 0; p <= AA_L - AA_RB; p++) {
        getwin(rh, p, th);
        getwin(rl, p, tl);
        int c = 0;
        for (int k = 0; k < AA_NWD; k++) {
            uint64_t m = ~(th[k] ^ ah[k]) & ~(tl[k] ^ al[k]);
            if (k == AA_NWD - 1) m &= mlast;
            c += (int)aa_popcnt64(m);
        }
        if (c > best) { best = c; b = p; }
    }
    *bp = b;
    return best;
}

void aa_align_read(const uint8_t *a, aa_result_t *out)
{
    uint64_t ah[AA_NWD], al[AA_NWD], bh[AA_NWD], bl[AA_NWD];
    for (int k = 0; k < AA_NWD; k++) { ah[k] = al[k] = bh[k] = bl[k] = 0; }
    for (int j = 0; j < AA_RB; j++) {
        if (a[j] >> 1) ah[j >> 6] |= 1ULL << (j & 63);
        if (a[j] & 1)  al[j >> 6] |= 1ULL << (j & 63);
        uint8_t x = a[AA_RB - 1 - j] ^ 1;          /* 反向互补：A0<->T1, G2<->C3 */
        if (x >> 1) bh[j >> 6] |= 1ULL << (j & 63);
        if (x & 1)  bl[j >> 6] |= 1ULL << (j & 63);
    }
    int p1, p2;
    out->s_fwd = align_one(ah, al, &p1); out->p_fwd = p1;
    out->s_rev = align_one(bh, bl, &p2); out->p_rev = p2;
}
