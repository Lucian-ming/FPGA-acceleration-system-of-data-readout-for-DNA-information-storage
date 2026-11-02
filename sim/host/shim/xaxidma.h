#ifndef __XAXIDMA_H__
#define __XAXIDMA_H__
/******************************************************************************
 * 主机侧壳层：AXI DMA（SG 模式）BD 环模型
 *
 * 只提供 sw/app/echo.c 真正用到的接口，语义按 Xilinx 驱动的**指针纪律**建模：
 *
 *     free → pre(Alloc 之后) → hw(ToHw 之后) → post(FromHw 之后) → free(Free 之后)
 *
 * 四个组在环上首尾相接、各自连续，因此 **Alloc/FromHw 返回的一批 BD 会跨过环尾
 * 回绕** —— 这正是 B21 第 3 条（线性索引 `&BdPtr[i]` 读到环外内存）的成因。
 * 本模型如实回绕，所以固件里那两处「必须沿 BdRingNext 走」的修复在主机上是
 * **可判定**的：改回线性索引，判据会红。
 *
 * 建模边界（写清楚，不要当成真硬件）：
 *   - `sizeof(XAxiDma_Bd)` 取 64 B，与 echo.h 的 BD_SPACE_SIZE_* / BD_ALIGNMENT
 *     一致；真实 Xilinx 驱动是 20 words = 80 B。轨迹里 BD 的 flush 长度因此是 64。
 *   - 不建模 AXI 错误响应、不建模 SG 描述符预取，只建模「投递 / 完成 / 回收」。
 *   - 完成节奏由 hostenv 的加速器模型驱动（见 hostenv.h 的 host_hw_tick）。
 ******************************************************************************/
#include "xil_types.h"

#define XAXIDMA_TX_OFFSET       0x00000000U
#define XAXIDMA_RX_OFFSET       0x00000030U
#define XAXIDMA_CR_OFFSET       0x00000000U
#define XAXIDMA_SR_OFFSET       0x00000004U
#define XAXIDMA_CDESC_OFFSET    0x00000008U
#define XAXIDMA_TDESC_OFFSET    0x00000010U

#define XAXIDMA_IRQ_ALL_MASK    0x00007000U

#define XAXIDMA_BD_CTRL_TXSOF_MASK  0x08000000U
#define XAXIDMA_BD_CTRL_TXEOF_MASK  0x04000000U
#define XAXIDMA_BD_STS_COMPLETE_MASK 0x80000000U
#define XAXIDMA_BD_STS_DEC_ERR_MASK  0x40000000U
#define XAXIDMA_BD_STS_SLV_ERR_MASK  0x20000000U
#define XAXIDMA_BD_STS_INT_ERR_MASK  0x10000000U
#define XAXIDMA_BD_STS_ALL_ERR_MASK  0x70000000U

/* 14 bit 长度域：align_down(16383, 8) = 16376，与板上 B21 现场
 * 「ceil(196608 / 16376) = 13 个 BD」精确吻合，不要随便改这个数。 */
#define XAXIDMA_HOST_MAX_TRANSFER_LEN  0x3FFFU

#define XAXIDMA_BD_NUM_WORDS    16U      /* 见上文建模边界：64 B/BD */

typedef struct { u32 w[XAXIDMA_BD_NUM_WORDS]; } XAxiDma_Bd;

/* BD 字偏移（与真实硬件 BD 同序，便于对着板上 dump 读） */
#define XAXIDMA_BD_NDESC     0
#define XAXIDMA_BD_BUFA      2
#define XAXIDMA_BD_CTRL      6
#define XAXIDMA_BD_STS       7

typedef struct {
    UINTPTR     BaseAddr;       /* BD 空间基址（= 物理地址，主机上由 mmap 落到同一地址） */
    int         BdCount;
    u32         MaxTransferLen;
    int         IsRx;
    const char *Name;

    /* 四个组：每组用「起点 + 长度」表示，起点是环上的 BD 序号 */
    int free_head, free_cnt;
    int pre_head,  pre_cnt;
    int hw_head,   hw_cnt;
    int post_head, post_cnt;

    int hw_completed;           /* hw 组前端已被硬件完成的 BD 数 */
    int started;
} XAxiDma_BdRing;

typedef struct {
    u16     DeviceId;
    UINTPTR BaseAddr;
    int     HasSg;
} XAxiDma_Config;

typedef struct {
    UINTPTR         RegBase;
    int             HasSg;
    XAxiDma_BdRing  TxRing;
    XAxiDma_BdRing  RxRing;
} XAxiDma;

XAxiDma_Config *XAxiDma_LookupConfig(u16 DeviceId);
int  XAxiDma_CfgInitialize(XAxiDma *InstancePtr, XAxiDma_Config *Config);
int  XAxiDma_HasSg(XAxiDma *InstancePtr);
XAxiDma_BdRing *XAxiDma_GetTxRing(XAxiDma *InstancePtr);
XAxiDma_BdRing *XAxiDma_GetRxRing(XAxiDma *InstancePtr);
u32  XAxiDma_ReadReg(UINTPTR BaseAddress, u32 RegOffset);

int  XAxiDma_BdRingCreate(XAxiDma_BdRing *RingPtr, UINTPTR PhysAddr,
                          UINTPTR VirtAddr, u32 Alignment, int BdCount);
void XAxiDma_BdClear(XAxiDma_Bd *BdPtr);
int  XAxiDma_BdRingClone(XAxiDma_BdRing *RingPtr, XAxiDma_Bd *TemplatePtr);
void XAxiDma_BdRingIntDisable(XAxiDma_BdRing *RingPtr, u32 Mask);
int  XAxiDma_BdRingStart(XAxiDma_BdRing *RingPtr);
int  XAxiDma_BdRingGetFreeCnt(XAxiDma_BdRing *RingPtr);
int  XAxiDma_BdRingAlloc(XAxiDma_BdRing *RingPtr, int NumBd, XAxiDma_Bd **BdSetPtr);
int  XAxiDma_BdRingToHw(XAxiDma_BdRing *RingPtr, int NumBd, XAxiDma_Bd *BdSetPtr);
int  XAxiDma_BdRingFromHw(XAxiDma_BdRing *RingPtr, int BdLimit, XAxiDma_Bd **BdSetPtr);
int  XAxiDma_BdRingFree(XAxiDma_BdRing *RingPtr, int NumBd, XAxiDma_Bd *BdSetPtr);
XAxiDma_Bd *XAxiDma_BdRingNext(XAxiDma_BdRing *RingPtr, XAxiDma_Bd *BdPtr);

void XAxiDma_BdSetBufAddr(XAxiDma_Bd *BdPtr, UINTPTR Addr);
int  XAxiDma_BdSetLength(XAxiDma_Bd *BdPtr, u32 LenBytes, u32 LengthMask);
void XAxiDma_BdSetCtrl(XAxiDma_Bd *BdPtr, u32 Data);
u32  XAxiDma_BdGetSts(XAxiDma_Bd *BdPtr);
u32  XAxiDma_BdGetLength(XAxiDma_Bd *BdPtr, u32 LengthMask);
UINTPTR XAxiDma_BdGetBufAddr(XAxiDma_Bd *BdPtr);

#endif /* __XAXIDMA_H__ */
