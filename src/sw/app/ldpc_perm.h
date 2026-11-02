/******************************************************************************
 * ldpc_perm.h — 结果缓冲「交织序 rx」与译码核「自然序 natural」之间的位级置换
 *
 * 为什么需要
 * ----------
 * 板端结果缓冲里那 8,100 B 是**交织序**的接收流 rx，而片上译码核的 H 矩阵寻址
 * 是**自然序** natural（校验位在前）。两者差一个位级置换：
 *
 *     natural[perm[i]] = rx[i]        等价于     natural[c] = rx[inv[c]]
 *
 * 直接拿 rx 喂核，核就是在错误的 H 上做 min-sum —— 板上实测「跑满 50 轮不收敛」
 * 就是这个原因（docs/benchmarks/ldpc-onchip-l7-board.md）。
 *
 * 位序约定（与结果缓冲一致，必须一致）
 * ------------------------------------
 * **每字节 LSB 先**：位 k 落在 byte[k >> 3] 的第 (k & 7) 位。
 * 依据 clients/python/fast_readout.py 的 fast_unpack_result 用
 * np.unpackbits(raw, bitorder="little")。
 * ⚠️ native_ldpc.py 的 bits_to_bytes 是 MSB 先，那是**载荷输出**那条路，别混。
 *
 * 本文件**不依赖任何 Xilinx 头**，所以同一份代码能在 x86 上被单元测试
 * （见 tools/test_ldpc_perm.sh）——核验不靠板子。
 ******************************************************************************/
#ifndef __LDPC_PERM_H__
#define __LDPC_PERM_H__

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* 自然序第 c 位取自交织序的第 g_ldpc_nat_to_rx[c] 位。定义在 ldpc_perm_table.c（生成文件）。 */
extern const uint16_t g_ldpc_nat_to_rx[64800];

/**
 * 交织序 -> 自然序：natural[c] = rx[inv[c]]，按 c 递增顺序查表、从 rx 聚读。
 * @param rx       输入，8100 字节交织序（每字节 LSB 先）
 * @param natural  输出，8100 字节自然序（每字节 LSB 先）
 */
void ldpc_perm_deinterleave(const uint8_t *rx, uint8_t *natural);

/**
 * 自然序 -> 交织序：rx[inv[c]] = natural[c]，按 c 递增顺序查表、向 rx 散写。
 * 是 ldpc_perm_deinterleave 的逆。
 * @param natural  输入，8100 字节自然序（每字节 LSB 先）
 * @param rx       输出，8100 字节交织序（每字节 LSB 先）
 */
void ldpc_perm_interleave(const uint8_t *natural, uint8_t *rx);

#ifdef __cplusplus
}
#endif

#endif /* __LDPC_PERM_H__ */
