// ============================================================================
// tools/align_omp.c —— 高度优化的 CPU 序列滑动比对基准 (支持单核与多核 OpenMP)
// 用于 docs/26 要求的 CPU vs FPGA 公平基准测试 (Eliminating Strawman Comparison)
// ============================================================================
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <time.h>

#ifdef _OPENMP
#include <omp.h>
#endif

#define L 40500
#ifndef RB
#define RB 150
#endif
#define NWD ((RB+63)/64)
#define NW ((L+63)/64 + NWD + 1)

static uint64_t rh[NW], rl[NW];

static inline void getwin(const uint64_t* a, int p, uint64_t* o) {
    int w = p >> 6, s = p & 63;
    for (int k = 0; k < NWD; k++) {
        o[k] = s ? ((a[w + k] >> s) | (a[w + k + 1] << (64 - s))) : a[w + k];
    }
}

static int align(const uint64_t* ah, const uint64_t* al, int* bp) {
    uint64_t th[NWD], tl[NWD]; 
    int best = -1, b = 0;
    const int rem = RB - 64 * (NWD - 1);
    const uint64_t mlast = (rem == 64) ? ~0ULL : ((1ULL << rem) - 1);
    
    for (int p = 0; p <= L - RB; p++) { 
        getwin(rh, p, th); 
        getwin(rl, p, tl); 
        int c = 0;
        for (int k = 0; k < NWD; k++) { 
            uint64_t m = ~(th[k] ^ ah[k]) & ~(tl[k] ^ al[k]);
            if (k == NWD - 1) m &= mlast; 
            c += __builtin_popcountll(m); 
        }
        if (c > best) {
            best = c; 
            b = p;
        } 
    }
    *bp = b; 
    return best;
}

int main(int argc, char** argv) {
    if (argc < 4) {
        fprintf(stderr, "Usage: %s <ref.bin> <reads.bin> <read_count> [threads]\n", argv[0]);
        return 1;
    }

    FILE* f = fopen(argv[1], "rb"); 
    if (!f) { perror("fopen ref"); return 1; }
    static unsigned char rf[L]; 
    if (fread(rf, 1, L, f) != L) { perror("fread ref"); fclose(f); return 1; } 
    fclose(f);

    for (int i = 0; i < L; i++) { 
        if (rf[i] >> 1) rh[i >> 6] |= 1ULL << (i & 63); 
        if (rf[i] & 1)  rl[i >> 6] |= 1ULL << (i & 63); 
    }

    int n = atoi(argv[3]); 
    f = fopen(argv[2], "rb"); 
    if (!f) { perror("fopen reads"); return 1; }
    unsigned char* rd = (unsigned char*)malloc((size_t)n * RB); 
    if (fread(rd, 1, (size_t)n * RB, f) != (size_t)n * RB) { perror("fread reads"); free(rd); fclose(f); return 1; } 
    fclose(f);

    int num_threads = 1;
    if (argc >= 5) {
        num_threads = atoi(argv[4]);
    }
#ifdef _OPENMP
    omp_set_num_threads(num_threads);
#endif

    struct timespec t0, t1; 
    clock_gettime(CLOCK_MONOTONIC, &t0); 
    long chk = 0;

#pragma omp parallel for reduction(+:chk) schedule(dynamic, 64)
    for (int i = 0; i < n; i++) {
        uint64_t ah[NWD], al[NWD], bh[NWD], bl[NWD];
        for (int k = 0; k < NWD; k++) { ah[k] = al[k] = bh[k] = bl[k] = 0; }
        const unsigned char* a = rd + (size_t)i * RB;
        for (int j = 0; j < RB; j++) {
            if (a[j] >> 1) ah[j >> 6] |= 1ULL << (j & 63); 
            if (a[j] & 1)  al[j >> 6] |= 1ULL << (j & 63);
            unsigned char x = a[RB - 1 - j] ^ 1;
            if (x >> 1) bh[j >> 6] |= 1ULL << (j & 63); 
            if (x & 1)  bl[j >> 6] |= 1ULL << (j & 63);
        }
        int p1, p2;
        int s1 = align(ah, al, &p1);
        int s2 = align(bh, bl, &p2); 
        chk += (s1 > s2 ? s1 : s2);
    }

    clock_gettime(CLOCK_MONOTONIC, &t1);
    double dt = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) / 1e9;
    printf("[CPU BENCHMARK] RB=%d | %d 条(双向) | 线程数: %d | 耗时: %.3f s | 吞吐: %.2f 条/s (%.3f ms/条) | 平均分: %.1f/%d\n",
           RB, n, num_threads, dt, n / dt, dt * 1000.0 / n, (double)chk / n, RB);

    free(rd);
    return 0;
}
