/******************************************************************************
 * fw_log.c — PS 固件诊断打印与内存/寄存器 dump 工具实现
 ******************************************************************************/
#include "fw_log.h"
#include "echo.h"
#include "xil_printf.h"
#include "xil_cache.h"
#include "xaxidma.h"

/* 打印一个 48B 的 read（Stage1/Stage2 输入），索引按 read 计数 */
void fw_dump_read48(const void *base_addr, u32 read_index)
{
    const UINTPTR addr = (UINTPTR)base_addr + (UINTPTR)read_index * 48U;
    Xil_DCacheInvalidateRange(addr, 48U);
    __asm__ volatile("dsb sy"); __asm__ volatile("isb");

    const volatile u8 *p = (const volatile u8 *)addr;
    xil_printf("[READ #%u] 48 bytes @ 0x%08X\n\r", read_index, (u32)addr);
    xil_printf("  [00-15]: "); for (int i = 0; i < 16; i++) xil_printf("%02X ", p[i]);
    xil_printf("\n\r  [16-31]: "); for (int i = 16; i < 32; i++) xil_printf("%02X ", p[i]);
    xil_printf("\n\r  [32-47]: "); for (int i = 32; i < 48; i++) xil_printf("%02X ", p[i]);
    xil_printf("\n\r");
}

/* 打印 8B 对齐的 u64 数组的若干元素（Stage2/Decoder 的 8B beats） */
void fw_dump_u64(const void *base_addr, u32 start_index, u32 count, const char *label)
{
    const UINTPTR addr = (UINTPTR)base_addr + ((UINTPTR)start_index * 8U);
    Xil_DCacheInvalidateRange(addr, 8U * count);
    __asm__ volatile("dsb sy"); __asm__ volatile("isb");

    const volatile u8 *p = (const volatile u8 *)addr;
    xil_printf("%s (index %u..%u):\n\r", label ? label : "[DUMP]", start_index, start_index + count - 1);
    for (u32 i = 0; i < count; i++) {
        const volatile u8 *b = p + (i * 8U);
        xil_printf("  [%4u]: ", start_index + i);
        for (int k = 0; k < 8; k++) xil_printf("%02X ", b[k]);
        xil_printf("\n\r");
    }
}

/* 打印 DMA 寄存器状态 */
void fw_dump_dma(const XAxiDma *dma, const char *tag)
{
    if (!dma) return;
    UINTPTR tx = dma->RegBase + XAXIDMA_TX_OFFSET;
    UINTPTR rx = dma->RegBase + XAXIDMA_RX_OFFSET;

    u32 tx_cr = XAxiDma_ReadReg(tx, XAXIDMA_CR_OFFSET);
    u32 tx_sr = XAxiDma_ReadReg(tx, XAXIDMA_SR_OFFSET);
    u32 tx_cur= XAxiDma_ReadReg(tx, XAXIDMA_CDESC_OFFSET);
    u32 tx_tal= XAxiDma_ReadReg(tx, XAXIDMA_TDESC_OFFSET);

    u32 rx_cr = XAxiDma_ReadReg(rx, XAXIDMA_CR_OFFSET);
    u32 rx_sr = XAxiDma_ReadReg(rx, XAXIDMA_SR_OFFSET);
    u32 rx_cur= XAxiDma_ReadReg(rx, XAXIDMA_CDESC_OFFSET);
    u32 rx_tal= XAxiDma_ReadReg(rx, XAXIDMA_TDESC_OFFSET);

    xil_printf("\n\r[DMA] %s\n\r", tag);
    /* 【B21】原实现读完寄存器却一行都没打印，等于哑巴看门狗：
     * 上一轮板上卡死时即使触发了 dump 也看不到任何证据。 */
    xil_printf("  MM2S: DMACR=0x%08X DMASR=0x%08X CURDESC=0x%08X TAILDESC=0x%08X\n\r",
               tx_cr, tx_sr, tx_cur, tx_tal);
    xil_printf("  S2MM: DMACR=0x%08X DMASR=0x%08X CURDESC=0x%08X TAILDESC=0x%08X\n\r",
               rx_cr, rx_sr, rx_cur, rx_tal);
    xil_printf("  MM2S halted=%u idle=%u err=0x%X | S2MM halted=%u idle=%u err=0x%X\n\r",
               (unsigned)(tx_sr & 1U), (unsigned)((tx_sr >> 1) & 1U),
               (unsigned)((tx_sr >> 4) & 0x7U),
               (unsigned)(rx_sr & 1U), (unsigned)((rx_sr >> 1) & 1U),
               (unsigned)((rx_sr >> 4) & 0x7U));
}

/* 【B21】DNA 核控制寄存器回读（reg0=start/preload/softrst，reg1=wm_sel） */
void fw_dump_dna(const char *tag)
{
    xil_printf("[DNA] %s reg0=0x%08X reg1=0x%08X\n\r", tag,
               read_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG0_CTRL),
               read_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG1_WMSEL));
}
