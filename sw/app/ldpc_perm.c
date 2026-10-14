/******************************************************************************
 * ldpc_perm.c — 见 ldpc_perm.h 的说明（语义、位序约定、为什么需要它）
 *
 * 两个方向都按**自然序计数器 c 递增**查表，所以访问模式是可预测的：
 *   - 表 g_ldpc_nat_to_rx 是顺序读（每字 2 字节，64,800 项 = 126.6 KiB，流式）；
 *   - deinterleave 从 rx 聚读、向 natural 顺序写（写侧完全顺序）；
 *   - interleave 向 rx 散写，但散写范围只有 8,100 字节，装得进 L1。
 * 没有浮点、没有除法、没有不可预测的分支。
 ******************************************************************************/
#include "ldpc_perm.h"

#include <string.h>

#define LDPC_PERM_BITS   64800u
#define LDPC_PERM_BYTES  8100u

void ldpc_perm_deinterleave(const uint8_t *rx, uint8_t *natural)
{
    uint32_t d;

    for (d = 0; d < LDPC_PERM_BYTES; d++) {
        uint32_t byte = 0u;
        uint32_t j;

        for (j = 0; j < 8u; j++) {
            uint32_t c = (d << 3) | j;
            uint32_t s = (uint32_t)g_ldpc_nat_to_rx[c];

            byte |= ((uint32_t)((rx[s >> 3] >> (s & 7u)) & 1u)) << j;
        }
        /* 逐个字节整写，不必预先清零输出。 */
        natural[d] = (uint8_t)byte;
    }
}

void ldpc_perm_interleave(const uint8_t *natural, uint8_t *rx)
{
    uint32_t c;

    /* 散写要按位或，所以必须先清零输出。 */
    memset(rx, 0, LDPC_PERM_BYTES);

    for (c = 0; c < LDPC_PERM_BITS; c++) {
        uint32_t s;

        if (((natural[c >> 3] >> (c & 7u)) & 1u) == 0u)
            continue;
        s = (uint32_t)g_ldpc_nat_to_rx[c];
        rx[s >> 3] |= (uint8_t)(1u << (s & 7u));
    }
}
