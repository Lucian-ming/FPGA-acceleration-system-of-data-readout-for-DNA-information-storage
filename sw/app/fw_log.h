/******************************************************************************
 * fw_log.h — PS 固件诊断打印与内存/寄存器 dump 工具
 ******************************************************************************/
#ifndef __FW_LOG_H__
#define __FW_LOG_H__

#include "xil_types.h"
#include "xaxidma.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 打印一个 48B 的 read（Stage1/Stage2 输入），索引按 read 计数 */
void fw_dump_read48(const void *base_addr, u32 read_index);

/* 打印 8B 对齐的 u64 数组的若干元素（Stage2/Decoder 的 8B beats） */
void fw_dump_u64(const void *base_addr, u32 start_index, u32 count, const char *label);

/* 打印 DMA 寄存器状态 */
void fw_dump_dma(const XAxiDma *dma, const char *tag);

/* 打印 DNA 核控制寄存器回读 */
void fw_dump_dna(const char *tag);

/* 兼容原有命名的别名 */
#define dump_read_48            fw_dump_read48
#define dump_u64_bytes_window   fw_dump_u64
#define dump_dna_regs           fw_dump_dna

#ifdef __cplusplus
}
#endif

#endif /* __FW_LOG_H__ */
