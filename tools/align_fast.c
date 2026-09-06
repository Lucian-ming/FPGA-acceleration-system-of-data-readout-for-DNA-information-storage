// ============================================================================
// tools/align_fast.c —— 高性能 C 语言滑窗比对动态库 (支持 OpenMP 多核并发)
// 供 Python 侧快速进行大规模鲁棒性测试、参数扫描与黄金流水线比对
// ============================================================================
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

#ifdef _OPENMP
#include <omp.h>
#endif

static inline void getwin(const uint64_t* a, int p, int nwd, uint64_t* o) {
    int w = p >> 6, s = p & 63;
    for (int k = 0; k < nwd; k++) {
        o[k] = s ? ((a[w + k] >> s) | (a[w + k + 1] << (64 - s))) : a[w + k];
    }
}

void align_reads_fast(
    const uint8_t* ref_sym, int L,
    const uint8_t* reads_sym, int n, int rb,
    int num_threads,
    int* out_dir, int* out_pos, int* out_score
) {
    int nwd = (rb + 63) / 64;
    int nw = (L + 63) / 64 + nwd + 1;
    uint64_t* rh = (uint64_t*)calloc(nw, sizeof(uint64_t));
    uint64_t* rl = (uint64_t*)calloc(nw, sizeof(uint64_t));

    for (int i = 0; i < L; i++) {
        if (ref_sym[i] >> 1) rh[i >> 6] |= 1ULL << (i & 63);
        if (ref_sym[i] & 1)  rl[i >> 6] |= 1ULL << (i & 63);
    }

    const int rem = rb - 64 * (nwd - 1);
    const uint64_t mlast = (rem == 64) ? ~0ULL : ((1ULL << rem) - 1);

#ifdef _OPENMP
    if (num_threads > 0) {
        omp_set_num_threads(num_threads);
    }
#endif

#pragma omp parallel for schedule(dynamic, 64)
    for (int i = 0; i < n; i++) {
        uint64_t ah[8], al[8], bh[8], bl[8];
        for (int k = 0; k < nwd; k++) {
            ah[k] = al[k] = bh[k] = bl[k] = 0;
        }
        const uint8_t* a = reads_sym + (size_t)i * rb;
        for (int j = 0; j < rb; j++) {
            if (a[j] >> 1) ah[j >> 6] |= 1ULL << (j & 63);
            if (a[j] & 1)  al[j >> 6] |= 1ULL << (j & 63);
            uint8_t x = a[rb - 1 - j] ^ 1;
            if (x >> 1) bh[j >> 6] |= 1ULL << (j & 63);
            if (x & 1)  bl[j >> 6] |= 1ULL << (j & 63);
        }

        uint64_t th[8], tl[8];
        int best1 = -1, pos1 = 0;
        for (int p = 0; p <= L - rb; p++) {
            getwin(rh, p, nwd, th);
            getwin(rl, p, nwd, tl);
            int c = 0;
            for (int k = 0; k < nwd; k++) {
                uint64_t m = ~(th[k] ^ ah[k]) & ~(tl[k] ^ al[k]);
                if (k == nwd - 1) m &= mlast;
                c += __builtin_popcountll(m);
            }
            if (c > best1) {
                best1 = c;
                pos1 = p;
            }
        }

        int best2 = -1, pos2 = 0;
        for (int p = 0; p <= L - rb; p++) {
            getwin(rh, p, nwd, th);
            getwin(rl, p, nwd, tl);
            int c = 0;
            for (int k = 0; k < nwd; k++) {
                uint64_t m = ~(th[k] ^ bh[k]) & ~(tl[k] ^ bl[k]);
                if (k == nwd - 1) m &= mlast;
                c += __builtin_popcountll(m);
            }
            if (c > best2) {
                best2 = c;
                pos2 = p;
            }
        }

        if (best1 >= best2) {
            out_dir[i] = 0;
            out_pos[i] = pos1;
            out_score[i] = best1;
        } else {
            out_dir[i] = 1;
            out_pos[i] = pos2;
            out_score[i] = best2;
        }
    }

    free(rh);
    free(rl);
}
