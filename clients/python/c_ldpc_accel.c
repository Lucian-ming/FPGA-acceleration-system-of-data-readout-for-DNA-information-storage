/*
 * c_ldpc_accel.c - DVB-S2 R=5/6 高性能 LDPC Min-Sum 硬判决译码 C 语言实现
 *
 * 与 clients/python/native_ldpc.py 算法与判决逻辑 100% 逐位对齐，
 * 利用局部内存布局与 C 原生循环将译码耗时从数秒压缩至数毫秒（>100x 提速）。
 */

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>

#ifdef _WIN32
  #define LDPC_API __declspec(dllexport)
#else
  #define LDPC_API __attribute__((visibility("default")))
#endif

#define LDPC_M_ROWS      10800
#define LDPC_N_BITS      64800
#define LDPC_K_INFO      54000
#define LDPC_PARITY_COLS 10800
#define LDPC_MAX_DEG     32

typedef struct {
    int m_rows;
    int n_bits;
    int k_info;
    int parity_cols;

    /* 校验矩阵行度数及相连的列号 */
    int row_deg[LDPC_M_ROWS];
    int row_cols[LDPC_M_ROWS * LDPC_MAX_DEG];

    /* 解交织置换表 */
    int perm[LDPC_N_BITS];

    /* 工作区数组 */
    double llr0[LDPC_N_BITS];
    double llr_cur[LDPC_N_BITS];
    double llr_next[LDPC_N_BITS];
    uint8_t natural[LDPC_N_BITS];
    uint8_t decoded[LDPC_N_BITS];
} ldpc_decoder_t;

/* 从文件加载 pchk 和 permutation 并初始化解码器 */
LDPC_API ldpc_decoder_t* ldpc_create(const char* pchk_path, const char* perm_path) {
    if (!pchk_path || !perm_path) {
        return NULL;
    }

    FILE* fp_pchk = fopen(pchk_path, "rb");
    if (!fp_pchk) {
        return NULL;
    }
    fseek(fp_pchk, 0, SEEK_END);
    long pchk_size = ftell(fp_pchk);
    fseek(fp_pchk, 0, SEEK_SET);

    if (pchk_size < 12) {
        fclose(fp_pchk);
        return NULL;
    }
    size_t num_int32 = pchk_size / sizeof(int32_t);
    int32_t* pchk_raw = (int32_t*)malloc(pchk_size);
    if (!pchk_raw) {
        fclose(fp_pchk);
        return NULL;
    }
    if (fread(pchk_raw, sizeof(int32_t), num_int32, fp_pchk) != num_int32) {
        free(pchk_raw);
        fclose(fp_pchk);
        return NULL;
    }
    fclose(fp_pchk);

    /* 校验 pchk 头部 */
    if (pchk_raw[0] != 0x5080 || pchk_raw[1] != LDPC_M_ROWS || pchk_raw[2] != LDPC_N_BITS) {
        free(pchk_raw);
        return NULL;
    }

    FILE* fp_perm = fopen(perm_path, "rb");
    if (!fp_perm) {
        free(pchk_raw);
        return NULL;
    }
    fseek(fp_perm, 0, SEEK_END);
    long perm_size = ftell(fp_perm);
    fseek(fp_perm, 0, SEEK_SET);
    if (perm_size != (long)(LDPC_N_BITS * sizeof(uint32_t))) {
        free(pchk_raw);
        fclose(fp_perm);
        return NULL;
    }
    uint32_t* perm_raw = (uint32_t*)malloc(perm_size);
    if (!perm_raw) {
        free(pchk_raw);
        fclose(fp_perm);
        return NULL;
    }
    if (fread(perm_raw, sizeof(uint32_t), LDPC_N_BITS, fp_perm) != (size_t)LDPC_N_BITS) {
        free(pchk_raw);
        free(perm_raw);
        fclose(fp_perm);
        return NULL;
    }
    fclose(fp_perm);

    /* 校验 permutation 是 [0, LDPC_N_BITS) 内的唯一排列，避免后续 natural[] 越界或覆盖。 */
    uint8_t* perm_seen = (uint8_t*)calloc(LDPC_N_BITS, sizeof(uint8_t));
    if (!perm_seen) {
        free(pchk_raw);
        free(perm_raw);
        return NULL;
    }
    for (int i = 0; i < LDPC_N_BITS; i++) {
        uint32_t value = perm_raw[i];
        if (value >= LDPC_N_BITS || perm_seen[value]) {
            free(perm_seen);
            free(pchk_raw);
            free(perm_raw);
            return NULL;
        }
        perm_seen[value] = 1;
    }
    free(perm_seen);

    ldpc_decoder_t* dec = (ldpc_decoder_t*)calloc(1, sizeof(ldpc_decoder_t));
    if (!dec) {
        free(pchk_raw);
        free(perm_raw);
        return NULL;
    }

    dec->m_rows = LDPC_M_ROWS;
    dec->n_bits = LDPC_N_BITS;
    dec->k_info = LDPC_K_INFO;
    dec->parity_cols = LDPC_PARITY_COLS;

    /* 复制置换表 */
    for (int i = 0; i < LDPC_N_BITS; i++) {
        dec->perm[i] = (int)perm_raw[i];
    }
    free(perm_raw);

    /* 解析 pchk 稀疏结构：从索引 3 开始，每行以负数结束 */
    int current_row = 0;
    int current_deg = 0;

    for (size_t i = 3; i < num_int32; i++) {
        int32_t val = pchk_raw[i];
        if (val < 0) {
            /* 遇到第一个负数代表前面空段结束，只有当 current_row >= 1 时才记录行 */
            if (i > 3) {
                dec->row_deg[current_row - 1] = current_deg;
            }
            current_row++;
            current_deg = 0;
            if (current_row > LDPC_M_ROWS) {
                break;
            }
        } else if (val > 0) {
            if (current_row >= 1 && current_row <= LDPC_M_ROWS) {
                int col = val - 1; /* 1-based 转为 0-based */
                if (col >= 0 && col < LDPC_N_BITS && current_deg < LDPC_MAX_DEG) {
                    dec->row_cols[(current_row - 1) * LDPC_MAX_DEG + current_deg] = col;
                    current_deg++;
                }
            }
        }
    }
    if (current_row >= 1 && current_row <= LDPC_M_ROWS) {
        dec->row_deg[current_row - 1] = current_deg;
    }
    free(pchk_raw);

    return dec;
}

/* 释放解码器资源 */
LDPC_API void ldpc_destroy(ldpc_decoder_t* dec) {
    if (dec) {
        free(dec);
    }
}

/* 
 * 核心译码执行函数
 * rx_bits: 64800 字节，每字节为 0 或 1
 * out_info: 输出缓冲区，必须预分配至少 54000 字节
 * max_iter: 最大迭代轮数（如 50）
 * out_initial_failed: 接收初始校验失败数目（可为 NULL）
 * out_iterations: 接收收敛迭代轮数（可为 NULL）
 * 返回值: 0 代表收敛成功，-1 代表达到 max_iter 未收敛，-2 代表输入为空
 */
LDPC_API int ldpc_decode(
    ldpc_decoder_t* dec,
    const uint8_t* rx_bits,
    uint8_t* out_info,
    int max_iter,
    int* out_initial_failed,
    int* out_iterations
) {
    if (!dec || !rx_bits || !out_info) {
        return -2;
    }
    if (max_iter <= 0) {
        max_iter = 50;
    }

    /* 1. 解交织: natural[perm[i]] = rx_bits[i] */
    for (int i = 0; i < LDPC_N_BITS; i++) {
        dec->natural[dec->perm[i]] = rx_bits[i];
    }

    /* 2. 初始化 LLR0 与当前 LLR: 1 -> +3.0, 0 -> -3.0 */
    for (int i = 0; i < LDPC_N_BITS; i++) {
        double v = (dec->natural[i] == 1) ? 3.0 : -3.0;
        dec->llr0[i] = v;
        dec->llr_cur[i] = v;
        dec->decoded[i] = dec->natural[i];
    }

    /* 3. 初始 Syndrome 校验 */
    int initial_failed = 0;
    for (int r = 0; r < LDPC_M_ROWS; r++) {
        int deg = dec->row_deg[r];
        const int* cols = &dec->row_cols[r * LDPC_MAX_DEG];
        int parity = 0;
        for (int j = 0; j < deg; j++) {
            parity ^= dec->decoded[cols[j]];
        }
        if (parity != 0) {
            initial_failed++;
        }
    }
    if (out_initial_failed) {
        *out_initial_failed = initial_failed;
    }
    if (initial_failed == 0) {
        memcpy(out_info, &dec->decoded[LDPC_PARITY_COLS], LDPC_K_INFO);
        if (out_iterations) {
            *out_iterations = 0;
        }
        return 0;
    }

    /* 4. Min-Sum 消息传递迭代 */
    for (int iter = 1; iter <= max_iter; iter++) {
        /* llr_next 初始化为 llr0 */
        memcpy(dec->llr_next, dec->llr0, sizeof(double) * LDPC_N_BITS);

        /* 校验节点遍历 */
        for (int r = 0; r < LDPC_M_ROWS; r++) {
            int deg = dec->row_deg[r];
            const int* cols = &dec->row_cols[r * LDPC_MAX_DEG];

            double min1 = 1e30, min2 = 1e30;
            int min1_idx = -1;
            double row_signs = 1.0;
            double s_arr[LDPC_MAX_DEG];

            /* 第一轮：提取幅值与符号，计算 row_signs、min1 与 min2 */
            for (int j = 0; j < deg; j++) {
                int c = cols[j];
                double v = dec->llr_cur[c];
                double mag = (v >= 0.0) ? v : -v;
                double s = (v > 0.0) ? 1.0 : ((v < 0.0) ? -1.0 : 0.0);
                s_arr[j] = s;
                row_signs *= s;

                if (mag < min1) {
                    min2 = min1;
                    min1 = mag;
                    min1_idx = j;
                } else if (mag < min2) {
                    min2 = mag;
                }
            }

            /* 若该行度数小于最大度数 22 (如 deg == 21)，对齐 Python native_ldpc 的 1e9 虚拟位行为 */
            if (deg < 22) {
                double mag = 1e9;
                /* 虚拟位 sign 为 1.0，row_signs *= 1.0 保持不变 */
                if (mag < min1) {
                    min2 = min1;
                    min1 = mag;
                    min1_idx = deg;
                } else if (mag < min2) {
                    min2 = mag;
                }
            }

            /* 第二轮：计算外信息并累加至相连变量节点 (只发给真实变量节点) */
            for (int j = 0; j < deg; j++) {
                int c = cols[j];
                double msg_sign = row_signs * s_arr[j];
                double msg_mag = (j == min1_idx) ? min2 : min1;
                dec->llr_next[c] += msg_sign * msg_mag;
            }
        }

        /* 硬判决 */
        for (int c = 0; c < LDPC_N_BITS; c++) {
            dec->decoded[c] = (dec->llr_next[c] > 0.0) ? 1 : 0;
        }

        /* 检查 Syndrome */
        int failed = 0;
        for (int r = 0; r < LDPC_M_ROWS; r++) {
            int deg = dec->row_deg[r];
            const int* cols = &dec->row_cols[r * LDPC_MAX_DEG];
            int parity = 0;
            for (int j = 0; j < deg; j++) {
                parity ^= dec->decoded[cols[j]];
            }
            if (parity != 0) {
                failed++;
            }
        }

        if (failed == 0) {
            /* 收敛！拷贝信息位 */
            memcpy(out_info, &dec->decoded[LDPC_PARITY_COLS], LDPC_K_INFO);
            if (out_iterations) {
                *out_iterations = iter;
            }
            return 0;
        }

        /* 将 llr_next 拷贝到 llr_cur 进入下一轮迭代 */
        memcpy(dec->llr_cur, dec->llr_next, sizeof(double) * LDPC_N_BITS);
    }

    /* 达到最大轮数未完全收敛 */
    if (out_iterations) {
        *out_iterations = max_iter;
    }
    return -1;
}
