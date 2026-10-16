/******************************************************************************
 * hostenv.c — 让**未经修改的** sw/app/echo.c 在 x86 主机上跑起来的环境模型。
 * 设计说明见 hostenv.h。
 ******************************************************************************/
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <errno.h>
#include <sys/mman.h>

#include "hostenv.h"
#include "xil_types.h"
#include "xil_io.h"
#include "xil_cache.h"
#include "xaxidma.h"
#include "lwip/tcp.h"
#include "netif/xadapter.h"
#include "ldpc_onchip.h"

/* 基地址来自仓库里那份**真实的** sw/app/xparameters.h（壳层只补了 _ps.h）。 */
#include "xparameters.h"

#define DNA_BASE   ((UINTPTR)XPAR_DNA_ACCELERATOR_CORE_0_S_AXI_LITE_CTRL_BASEADDR)
#define VOT_BASE   ((UINTPTR)XPAR_DIFFERENTIAL_VOTER_0_S00_AXI_BASEADDR)
#define DEC_BASE   ((UINTPTR)XPAR_DESPARSIFICATION_DEC_0_S00_AXI_BASEADDR)
#define DMA_BASE   ((UINTPTR)0x40400000UL)
#define REG_WINDOW 0x10000UL

/* 设备模型自用的尺寸（不参与判据，判据里的数字全部来自固件自己算的） */
#define REC_BYTES      48u
#define READ_BYTES     40u
#define WM_REGIONS     50u
#define WM_REGION_ROWS 957u
#define VOT_OUT_BEATS  1266u
#define DEC_OUT_BEATS  1013u
#define DEC_SENTINEL   0x0A55AA55AA55AA55ULL

/* 主机模型不模拟片上 LDPC 核：保留 Stage3 输出，按未收敛回退路径
 * 将流水线推进到 echo.c 消费的终止状态。返回码遵循 pipe_step_rc_e，
 * 让 run_processing_pipeline() 将其作为一次成功的状态推进处理。 */
pipe_step_rc_e pipeline_step_ldpc(void)
{
    if (pipe_state < PIPE_LDPC_PREP || pipe_state > PIPE_LDPC_READBACK)
        return PIPE_STEP_FAIL;

    pipeline_set_state(PIPE_SEND_RESULT);
    return PIPE_STEP_PROGRESS;
}

host_hw_cfg_t host_hw_cfg = {
    .result_fifo_depth = 16u,
    .voter_busy_ticks  = 2u,
    .dec_busy_ticks    = 2u,
    .dec_mode          = HOST_DEC_FIXED,
};

/*============================================================================
 * 1) 轨迹
 *==========================================================================*/
static char        **g_trc;
static unsigned long  g_trc_n, g_trc_cap;
static int            g_trc_on = 1;

void host_trace_enable(int on) { g_trc_on = on; }

void host_trace_clear(void)
{
    for (unsigned long i = 0; i < g_trc_n; i++) free(g_trc[i]);
    g_trc_n = 0;
}

void host_trace_add(const char *fmt, ...)
{
    char line[512];
    va_list ap;
    if (!g_trc_on) return;
    va_start(ap, fmt);
    vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    if (g_trc_n == g_trc_cap) {
        g_trc_cap = g_trc_cap ? g_trc_cap * 2 : 1024;
        g_trc = (char **)realloc(g_trc, g_trc_cap * sizeof(char *));
        if (!g_trc) { fprintf(stderr, "[hostenv] OOM in trace\n"); exit(2); }
    }
    g_trc[g_trc_n++] = strdup(line);
}

unsigned long host_trace_lines(void) { return g_trc_n; }

int host_trace_write(const char *path)
{
    FILE *f = fopen(path, "w");
    if (!f) return -1;
    for (unsigned long i = 0; i < g_trc_n; i++) fprintf(f, "%s\n", g_trc[i]);
    fclose(f);
    return 0;
}

int host_trace_compare(const char *golden_path, const char *what)
{
    FILE *f = fopen(golden_path, "r");
    char buf[512];
    unsigned long i = 0;
    int bad = 0;

    if (!f) {
        printf("  ✗ %s：黄金轨迹 %s 打不开（%s）\n", what, golden_path, strerror(errno));
        return 1;
    }
    while (fgets(buf, sizeof buf, f)) {
        size_t n = strlen(buf);
        while (n && (buf[n-1] == '\n' || buf[n-1] == '\r')) buf[--n] = 0;
        if (i >= g_trc_n) {
            printf("  ✗ %s：实测轨迹在第 %lu 行就结束了，黄金还有「%s」\n",
                   what, i + 1, buf);
            bad = 1; break;
        }
        if (strcmp(buf, g_trc[i]) != 0) {
            printf("  ✗ %s：第 %lu 行不同\n", what, i + 1);
            printf("      黄金: %s\n", buf);
            printf("      实测: %s\n", g_trc[i]);
            bad = 1; break;
        }
        i++;
    }
    fclose(f);
    if (!bad && i < g_trc_n) {
        printf("  ✗ %s：黄金轨迹在第 %lu 行结束，实测还多出「%s」\n",
               what, i, g_trc[i]);
        bad = 1;
    }
    if (!bad) printf("  ✓ %s：%lu 行轨迹逐行相同\n", what, g_trc_n);
    return bad;
}

/*============================================================================
 * 2) 固件日志（不进轨迹）
 *==========================================================================*/
static char g_log[1 << 16];
static size_t g_log_len;

void xil_printf(const char *fmt, ...)
{
    char line[1024];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    if (getenv("HOSTENV_VERBOSE")) fputs(line, stderr);
    size_t n = strlen(line);
    if (g_log_len + n + 1 >= sizeof g_log) { g_log_len = 0; }  /* 环形丢弃 */
    memcpy(g_log + g_log_len, line, n + 1);
    g_log_len += n;
}

const char *host_log_tail(void) { return g_log; }

/*============================================================================
 * 3) 假 DDR
 *==========================================================================*/
static void *g_ddr = NULL;
static void host_devices_reset(void);
static void host_dma_reset(void);
static void host_tcp_reset(void);

void host_env_init(void)
{
    if (g_ddr == NULL) {
        int flags = MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE;
#ifdef MAP_NORESERVE
        flags |= MAP_NORESERVE;
#endif
        g_ddr = mmap((void *)HOST_DDR_BASE, HOST_DDR_SIZE,
                     PROT_READ | PROT_WRITE, flags, -1, 0);
        if (g_ddr == MAP_FAILED || g_ddr != (void *)HOST_DDR_BASE) {
            fprintf(stderr,
                "[hostenv] 无法把假 DDR 映到 0x%lX（%s）。固件用的是绝对地址，\n"
                "          映不上就没法在「不改 echo.c 一个字节」的前提下测。\n",
                HOST_DDR_BASE, strerror(errno));
            exit(2);
        }
    }
    memset(g_ddr, 0, HOST_DDR_SIZE);
    host_devices_reset();
    host_dma_reset();
    host_tcp_reset();
    host_trace_clear();
    g_log_len = 0; g_log[0] = 0;
}

void host_env_fini(void)
{
    if (g_ddr) { munmap(g_ddr, HOST_DDR_SIZE); g_ddr = NULL; }
}

/*============================================================================
 * 4) 三个 IP 核的寄存器模型
 *==========================================================================*/
typedef struct {
    u32 reg0, reg1;                 /* DNA: ctrl / wm_sel */
    unsigned wm_rows[WM_REGIONS];   /* 每个区域实际收到多少个符号 */
    unsigned wm_regions_done;
    unsigned in_fifo_reads;         /* 输入 FIFO 里排队的读段 */
    unsigned res_fifo;              /* 结果 FIFO 里排队的记录 */
    unsigned reads_fed, records_made, records_out;
    int      stalled;               /* MM2S 因结果 FIFO 满而停摆 */
} dna_model_t;

typedef struct {
    u32 in_addr, in_beats, out_addr, out_beats, total_reads, score_min;
    int busy, done, busy_left;
} voter_model_t;

typedef struct {
    u32 in_addr, in_beats, out_addr, out_beats;
    int busy, done, busy_left;
    int start_writes, start_pulses;
} dec_model_t;

static dna_model_t   g_dna;
static voter_model_t g_vot;
static dec_model_t   g_dec;

static void host_devices_reset(void)
{
    memset(&g_dna, 0, sizeof g_dna);
    memset(&g_vot, 0, sizeof g_vot);
    memset(&g_dec, 0, sizeof g_dec);
    g_vot.done = 0;
    g_dec.done = 0;
}

unsigned host_dna_records_made(void) { return g_dna.records_made; }
unsigned host_dna_reads_fed(void)    { return g_dna.reads_fed; }
unsigned host_wm_regions_loaded(void){ return g_dna.wm_regions_done; }
int      host_dec_start_writes(void) { return g_dec.start_writes; }
int      host_dec_start_pulses(void) { return g_dec.start_pulses; }
int      host_dna_stalled(void)      { return g_dna.stalled; }

int host_wm_region_len_ok(void)
{
    for (unsigned i = 0; i < WM_REGIONS; i++)
        if (g_dna.wm_rows[i] != WM_REGION_ROWS) return 0;
    return 1;
}

/* 地址 → 「设备名 + 偏移」，让轨迹可读且与具体基地址解耦 */
static const char *reg_dev(UINTPTR a, u32 *off)
{
    if (a >= DNA_BASE && a < DNA_BASE + REG_WINDOW) { *off = (u32)(a - DNA_BASE); return "dna"; }
    if (a >= VOT_BASE && a < VOT_BASE + REG_WINDOW) { *off = (u32)(a - VOT_BASE); return "vot"; }
    if (a >= DEC_BASE && a < DEC_BASE + REG_WINDOW) { *off = (u32)(a - DEC_BASE); return "dec"; }
    if (a >= DMA_BASE && a < DMA_BASE + REG_WINDOW) { *off = (u32)(a - DMA_BASE); return "dma"; }
    *off = 0; return NULL;
}

void Xil_Out32(UINTPTR addr, u32 value)
{
    u32 off; const char *dev = reg_dev(addr, &off);

    if (dev == NULL) {                       /* 普通 DDR 写 */
        *(volatile u32 *)addr = value;
        return;
    }
    host_trace_add("REGW %s+0x%02X = 0x%08X", dev, off, value);

    if (strcmp(dev, "dna") == 0) {
        if (off == 0x00) g_dna.reg0 = value;
        if (off == 0x04) g_dna.reg1 = value;
    } else if (strcmp(dev, "vot") == 0) {
        switch (off) {
        case 0x00:
            if (value & 0x2u) g_vot.done = 0;                  /* done_clr */
            if ((value & 0x1u) && !g_vot.busy) {               /* start_pulse=wdata[0] */
                g_vot.busy = 1; g_vot.done = 0;
                g_vot.busy_left = (int)host_hw_cfg.voter_busy_ticks;
            }
            break;
        case 0x04: g_vot.in_addr     = value; break;
        case 0x08: g_vot.in_beats    = value; break;
        case 0x0C: g_vot.out_addr    = value; break;
        case 0x10: g_vot.out_beats   = value; break;
        case 0x14: g_vot.total_reads = value; break;
        case 0x30: g_vot.score_min   = value; break;
        default: break;
        }
    } else if (strcmp(dev, "dec") == 0) {
        switch (off) {
        case 0x00: g_dec.in_addr   = value; break;
        case 0x04: g_dec.in_beats  = value; break;
        case 0x08: g_dec.out_addr  = value; break;
        case 0x0C: g_dec.out_beats = value; break;
        case 0x10: {
            g_dec.start_writes++;
            /* HOST_DEC_FIXED  ：start_eff = wdata[0] & ~core_active（B27 修复后）
             * HOST_DEC_LEGACY ：对本寄存器写**任何值**都启动（B27 之前的 RTL） */
            int fire = (host_hw_cfg.dec_mode == HOST_DEC_LEGACY)
                       ? !g_dec.busy
                       : ((value & 0x1u) && !g_dec.busy);
            if (fire) {
                g_dec.start_pulses++;
                g_dec.busy = 1; g_dec.done = 0;
                g_dec.busy_left = (int)host_hw_cfg.dec_busy_ticks;
            }
            break;
        }
        default: break;
        }
    }
}

u32 Xil_In32(UINTPTR addr)
{
    u32 off; const char *dev = reg_dev(addr, &off);
    u32 v = 0;

    if (dev == NULL) return *(volatile u32 *)addr;

    if (strcmp(dev, "dna") == 0) {
        v = (off == 0x00) ? g_dna.reg0 : (off == 0x04) ? g_dna.reg1 : 0;
    } else if (strcmp(dev, "vot") == 0) {
        switch (off) {
        case 0x00: v = (g_vot.busy ? 0u : 1u) | (g_vot.done ? 2u : 0u); break;
        case 0x04: v = g_vot.in_addr;     break;
        case 0x08: v = g_vot.in_beats;    break;
        case 0x0C: v = g_vot.out_addr;    break;
        case 0x10: v = g_vot.out_beats;   break;
        case 0x14: v = g_vot.total_reads; break;
        case 0x30: v = g_vot.score_min;   break;
        default:   v = 0; break;   /* 0x18/0x24/0x2C 调试寄存器：模型给 0 */
        }
    } else if (strcmp(dev, "dec") == 0) {
        switch (off) {
        case 0x00: v = g_dec.in_addr;   break;
        case 0x04: v = g_dec.in_beats;  break;
        case 0x08: v = g_dec.out_addr;  break;
        case 0x0C: v = g_dec.out_beats; break;
        case 0x18: v = (g_dec.busy ? 0u : 1u) | (g_dec.done ? 2u : 0u); break;
        default:   v = 0; break;
        }
    }
    host_trace_add("REGR %s+0x%02X -> 0x%08X", dev, off, v);
    return v;
}

void Xil_Out8(UINTPTR addr, u8 value) { *(volatile u8 *)addr = value; }
u8   Xil_In8(UINTPTR addr)            { return *(volatile u8 *)addr; }

/*============================================================================
 * 5) 缓存维护 —— 位置与范围是正确性的一部分，逐条进轨迹
 *==========================================================================*/
void Xil_DCacheFlushRange(UINTPTR adr, u32 len)
{ host_trace_add("CACHE FLUSH 0x%08lX +%u", (unsigned long)adr, len); }

void Xil_DCacheInvalidateRange(UINTPTR adr, u32 len)
{ host_trace_add("CACHE INVAL 0x%08lX +%u", (unsigned long)adr, len); }

void Xil_DCacheFlush(void)      { host_trace_add("CACHE FLUSH_ALL"); }
void Xil_DCacheInvalidate(void) { host_trace_add("CACHE INVAL_ALL"); }

/*============================================================================
 * 6) usleep —— 「写 0 → 写 1 → usleep → 写 0」里的 usleep 也是判据的一部分
 *==========================================================================*/
/* 固件在一个 poll 里 usleep 等 DMA 完成时，板上**时间真的在走、DMA 真的在跑**。
 * 所以 usleep 除了记轨迹，还要推进一次数据通路（MM2S/DNA 核/S2MM）。
 * 不这样建模，任何「poll 内忙等 BD 完成」的写法在主机上都会假死 —— 那是模型的
 * 问题，不是固件的问题。三个 IP 核的忙碌时长仍按 poll 计（见 host_hw_tick）。 */
static void host_datapath_run(void);
void host_usleep(unsigned long us)
{
    host_trace_add("SLEEP %luus", us);
    host_datapath_run();
}
void host_sleep_s(unsigned long s) { host_trace_add("SLEEP %lus", s); }

/*============================================================================
 * 7) AXI DMA / BD 环模型
 *==========================================================================*/
static XAxiDma *g_dma_inst = NULL;
static XAxiDma_Config g_dma_cfg = { 0, DMA_BASE, 1 };

static XAxiDma_Bd *ring_bd(XAxiDma_BdRing *r, int idx)
{ return (XAxiDma_Bd *)(r->BaseAddr + (UINTPTR)((idx % r->BdCount) * 64)); }

static int ring_idx(XAxiDma_BdRing *r, XAxiDma_Bd *bd)
{ return (int)(((UINTPTR)bd - r->BaseAddr) / 64) % r->BdCount; }

static void host_dma_reset(void) { g_dma_inst = NULL; }

XAxiDma_Config *XAxiDma_LookupConfig(u16 DeviceId) { (void)DeviceId; return &g_dma_cfg; }

int XAxiDma_CfgInitialize(XAxiDma *InstancePtr, XAxiDma_Config *Config)
{
    memset(InstancePtr, 0, sizeof *InstancePtr);
    InstancePtr->RegBase = Config->BaseAddr;
    InstancePtr->HasSg   = Config->HasSg;
    InstancePtr->TxRing.IsRx = 0; InstancePtr->TxRing.Name = "tx";
    InstancePtr->RxRing.IsRx = 1; InstancePtr->RxRing.Name = "rx";
    g_dma_inst = InstancePtr;
    host_trace_add("DMA INIT base=0x%08lX sg=%d", (unsigned long)Config->BaseAddr, Config->HasSg);
    return XST_SUCCESS;
}

int XAxiDma_HasSg(XAxiDma *InstancePtr) { return InstancePtr->HasSg; }
XAxiDma_BdRing *XAxiDma_GetTxRing(XAxiDma *p) { return &p->TxRing; }
XAxiDma_BdRing *XAxiDma_GetRxRing(XAxiDma *p) { return &p->RxRing; }

u32 XAxiDma_ReadReg(UINTPTR BaseAddress, u32 RegOffset)
{
    /* dump_dma_regs() 用它读 CR/SR/CURDESC/TAILDESC。给一个由环状态推出来的
     * 确定值：不是真硬件，但对「日志里能不能看见证据」这件事足够，
     * 而且是确定性的，不会污染轨迹判据。 */
    XAxiDma_BdRing *r = NULL;
    u32 sub = RegOffset;
    if (g_dma_inst) {
        if (BaseAddress == g_dma_inst->RegBase + XAXIDMA_TX_OFFSET) r = &g_dma_inst->TxRing;
        else if (BaseAddress == g_dma_inst->RegBase + XAXIDMA_RX_OFFSET) r = &g_dma_inst->RxRing;
    }
    if (!r) return 0;
    switch (sub) {
    case XAXIDMA_CR_OFFSET:    return r->started ? 0x00010003u : 0x00010000u;
    case XAXIDMA_SR_OFFSET:    return (r->hw_cnt == 0) ? 0x00000002u : 0x00000000u;
    case XAXIDMA_CDESC_OFFSET: return (u32)(r->BaseAddr + (UINTPTR)(r->hw_head * 64));
    case XAXIDMA_TDESC_OFFSET: return (u32)(r->BaseAddr +
                                  (UINTPTR)(((r->hw_head + r->hw_cnt) % (r->BdCount ? r->BdCount : 1)) * 64));
    default: return 0;
    }
}

int XAxiDma_BdRingCreate(XAxiDma_BdRing *RingPtr, UINTPTR PhysAddr,
                         UINTPTR VirtAddr, u32 Alignment, int BdCount)
{
    const char *name = RingPtr->Name;
    int isrx = RingPtr->IsRx;
    (void)VirtAddr;
    if (BdCount <= 0 || (PhysAddr % Alignment) != 0) return XST_FAILURE;
    memset(RingPtr, 0, sizeof *RingPtr);
    RingPtr->Name = name; RingPtr->IsRx = isrx;
    RingPtr->BaseAddr = PhysAddr;
    RingPtr->BdCount  = BdCount;
    RingPtr->MaxTransferLen = XAXIDMA_HOST_MAX_TRANSFER_LEN;
    RingPtr->free_cnt = BdCount;
    host_trace_add("DMA RING CREATE %s base=0x%08lX n=%d maxlen=%u",
                   name, (unsigned long)PhysAddr, BdCount, RingPtr->MaxTransferLen);
    return XST_SUCCESS;
}

void XAxiDma_BdClear(XAxiDma_Bd *BdPtr) { memset(BdPtr, 0, sizeof *BdPtr); }

int XAxiDma_BdRingClone(XAxiDma_BdRing *RingPtr, XAxiDma_Bd *TemplatePtr)
{
    for (int i = 0; i < RingPtr->BdCount; i++)
        memcpy(ring_bd(RingPtr, i), TemplatePtr, sizeof *TemplatePtr);
    return XST_SUCCESS;
}

void XAxiDma_BdRingIntDisable(XAxiDma_BdRing *RingPtr, u32 Mask) { (void)RingPtr; (void)Mask; }

int XAxiDma_BdRingStart(XAxiDma_BdRing *RingPtr)
{ RingPtr->started = 1; host_trace_add("DMA RING START %s", RingPtr->Name); return XST_SUCCESS; }

int XAxiDma_BdRingGetFreeCnt(XAxiDma_BdRing *RingPtr) { return RingPtr->free_cnt; }

int XAxiDma_BdRingAlloc(XAxiDma_BdRing *RingPtr, int NumBd, XAxiDma_Bd **BdSetPtr)
{
    if (NumBd <= 0 || NumBd > RingPtr->free_cnt) return XST_FAILURE;
    if (RingPtr->pre_cnt == 0) RingPtr->pre_head = RingPtr->free_head;
    *BdSetPtr = ring_bd(RingPtr, RingPtr->free_head);
    RingPtr->free_head = (RingPtr->free_head + NumBd) % RingPtr->BdCount;
    RingPtr->free_cnt -= NumBd;
    RingPtr->pre_cnt  += NumBd;
    return XST_SUCCESS;
}

int XAxiDma_BdRingToHw(XAxiDma_BdRing *RingPtr, int NumBd, XAxiDma_Bd *BdSetPtr)
{
    if (NumBd <= 0 || NumBd > RingPtr->pre_cnt) return XST_FAILURE;
    if (ring_idx(RingPtr, BdSetPtr) != RingPtr->pre_head) return XST_FAILURE;
    if (RingPtr->hw_cnt == 0) RingPtr->hw_head = RingPtr->pre_head;
    RingPtr->pre_head = (RingPtr->pre_head + NumBd) % RingPtr->BdCount;
    RingPtr->pre_cnt -= NumBd;
    RingPtr->hw_cnt  += NumBd;
    host_trace_add("DMA TOHW %s n=%d", RingPtr->Name, NumBd);
    return XST_SUCCESS;
}

int XAxiDma_BdRingFromHw(XAxiDma_BdRing *RingPtr, int BdLimit, XAxiDma_Bd **BdSetPtr)
{
    int n = RingPtr->hw_completed;
    if (BdLimit > 0 && n > BdLimit) n = BdLimit;
    if (n <= 0) { *BdSetPtr = NULL; return 0; }
    if (RingPtr->post_cnt == 0) RingPtr->post_head = RingPtr->hw_head;
    *BdSetPtr = ring_bd(RingPtr, RingPtr->hw_head);
    RingPtr->hw_head = (RingPtr->hw_head + n) % RingPtr->BdCount;
    RingPtr->hw_cnt -= n;
    RingPtr->hw_completed -= n;
    RingPtr->post_cnt += n;
    host_trace_add("DMA FROMHW %s n=%d", RingPtr->Name, n);
    return n;
}

int XAxiDma_BdRingFree(XAxiDma_BdRing *RingPtr, int NumBd, XAxiDma_Bd *BdSetPtr)
{
    if (NumBd <= 0 || NumBd > RingPtr->post_cnt) return XST_FAILURE;
    if (ring_idx(RingPtr, BdSetPtr) != RingPtr->post_head) return XST_FAILURE;
    RingPtr->post_head = (RingPtr->post_head + NumBd) % RingPtr->BdCount;
    RingPtr->post_cnt -= NumBd;
    RingPtr->free_cnt += NumBd;
    return XST_SUCCESS;
}

XAxiDma_Bd *XAxiDma_BdRingNext(XAxiDma_BdRing *RingPtr, XAxiDma_Bd *BdPtr)
{ return ring_bd(RingPtr, ring_idx(RingPtr, BdPtr) + 1); }

void XAxiDma_BdSetBufAddr(XAxiDma_Bd *BdPtr, UINTPTR Addr)
{ BdPtr->w[XAXIDMA_BD_BUFA] = (u32)Addr; }

int XAxiDma_BdSetLength(XAxiDma_Bd *BdPtr, u32 LenBytes, u32 LengthMask)
{
    if (LenBytes == 0 || LenBytes > LengthMask) return XST_FAILURE;
    BdPtr->w[XAXIDMA_BD_CTRL] = (BdPtr->w[XAXIDMA_BD_CTRL] & ~LengthMask) | LenBytes;
    return XST_SUCCESS;
}

void XAxiDma_BdSetCtrl(XAxiDma_Bd *BdPtr, u32 Data)
{ BdPtr->w[XAXIDMA_BD_CTRL] = (BdPtr->w[XAXIDMA_BD_CTRL] & 0x00FFFFFFu) | (Data & 0xFF000000u); }

u32 XAxiDma_BdGetSts(XAxiDma_Bd *BdPtr) { return BdPtr->w[XAXIDMA_BD_STS]; }
u32 XAxiDma_BdGetLength(XAxiDma_Bd *BdPtr, u32 LengthMask)
{ return BdPtr->w[XAXIDMA_BD_CTRL] & LengthMask; }
UINTPTR XAxiDma_BdGetBufAddr(XAxiDma_Bd *BdPtr) { return (UINTPTR)BdPtr->w[XAXIDMA_BD_BUFA]; }

/*============================================================================
 * 8) 硬件时间：一个 tick = 两次 poll 之间硬件干的活
 *
 * 真实节奏是「poll 每 250~500 ms 一次，中间硬件一直在跑」，所以 tick 内
 * 一直推进到**被描述符卡住**为止 —— RX 环空了就停，这正是 B21 的锁死机理。
 *==========================================================================*/
#define DNA_IN_FIFO_READS  256u

static u32 rec_pattern_word(unsigned rec, unsigned w)
{
    /* 确定性伪随机；只要求非零且可复现，内容不参与判据 */
    u64 x = 0x9E3779B97F4A7C15ULL * (rec + 1u) + 0x632BE59BD9B4E019ULL * (w + 1u);
    x ^= x >> 29; x *= 0xBF58476D1CE4E5B9ULL; x ^= x >> 32;
    return (u32)x;
}

static int tx_step(void)
{
    XAxiDma_BdRing *r;
    XAxiDma_Bd *bd;
    u32 len;
    if (!g_dma_inst) return 0;
    r = &g_dma_inst->TxRing;
    if (r->hw_completed >= r->hw_cnt) return 0;         /* 没有待处理的 BD */

    bd  = ring_bd(r, (r->hw_head + r->hw_completed) % r->BdCount);
    len = bd->w[XAXIDMA_BD_CTRL] & r->MaxTransferLen;

    if (g_dna.reg0 & 0x2u) {                            /* 预载模式：写水印 BRAM */
        unsigned sel = g_dna.reg1 % WM_REGIONS;
        g_dna.wm_rows[sel] += len / 4u;
        if (g_dna.wm_rows[sel] >= WM_REGION_ROWS && sel + 1u > g_dna.wm_regions_done)
            g_dna.wm_regions_done = sel + 1u;
    } else {                                            /* 数据模式：进输入 FIFO */
        unsigned reads = len / READ_BYTES;
        if (g_dna.in_fifo_reads + reads > DNA_IN_FIFO_READS) { g_dna.stalled = 1; return 0; }
        g_dna.in_fifo_reads += reads;
        g_dna.reads_fed     += reads;
    }
    bd->w[XAXIDMA_BD_STS] = XAXIDMA_BD_STS_COMPLETE_MASK | len;
    r->hw_completed++;
    return 1;
}

static int core_step(void)
{
    if (!(g_dna.reg0 & 0x1u)) return 0;                 /* 没 START 就不算 */
    if (g_dna.in_fifo_reads == 0) return 0;
    if (g_dna.res_fifo >= host_hw_cfg.result_fifo_depth) { g_dna.stalled = 1; return 0; }
    g_dna.in_fifo_reads--;
    g_dna.res_fifo++;
    g_dna.records_made++;
    return 1;
}

static int rx_step(void)
{
    XAxiDma_BdRing *r;
    XAxiDma_Bd *bd;
    UINTPTR dst;
    if (!g_dma_inst) return 0;
    if (g_dna.res_fifo == 0) return 0;
    r = &g_dma_inst->RxRing;
    if (r->hw_completed >= r->hw_cnt) return 0;         /* S2MM 无描述符 → 停 */

    bd  = ring_bd(r, (r->hw_head + r->hw_completed) % r->BdCount);
    dst = (UINTPTR)bd->w[XAXIDMA_BD_BUFA];
    /* DNA 核每条 48 B 结果一个 AXIS packet（TLAST），一个 BD 只收一条 —— B21 根因 */
    for (unsigned w = 0; w < REC_BYTES / 4u; w++)
        ((volatile u32 *)dst)[w] = rec_pattern_word(g_dna.records_out, w);
    bd->w[XAXIDMA_BD_STS] = XAXIDMA_BD_STS_COMPLETE_MASK | 0x0C000000u | REC_BYTES;
    r->hw_completed++;
    g_dna.res_fifo--;
    g_dna.records_out++;
    return 1;
}

static void voter_step(void)
{
    if (!g_vot.busy) return;
    if (--g_vot.busy_left > 0) return;
    for (u32 i = 0; i < g_vot.out_beats && i < VOT_OUT_BEATS; i++)
        ((volatile u64 *)(UINTPTR)g_vot.out_addr)[i] =
            0x0123456789ABCDEFULL ^ ((u64)(i + 1) * 0x9E3779B97F4A7C15ULL);
    g_vot.busy = 0; g_vot.done = 1;
}

static void dec_step(void)
{
    if (!g_dec.busy) return;
    if (--g_dec.busy_left > 0) return;
    for (u32 i = 0; i < g_dec.out_beats && i < DEC_OUT_BEATS; i++)
        ((volatile u64 *)(UINTPTR)g_dec.out_addr)[i] =
            0x00FF00FF00FF00FFULL ^ ((u64)(i + 1) * 0xD1B54A32D192ED03ULL);
    g_dec.busy = 0; g_dec.done = 1;
}

static void host_datapath_run(void)
{
    int guard = 4000000;
    while (guard-- > 0) {
        int progress = 0;
        progress |= tx_step();
        progress |= core_step();
        progress |= rx_step();
        if (!progress) break;
    }
}

void host_hw_tick(void)
{
    host_time_advance_one_poll();
    host_datapath_run();
    voter_step();
    dec_step();
}

/*============================================================================
 * 9) lwIP 模型
 *==========================================================================*/
static struct tcp_pcb g_listen_pcb, g_client_pcb;
static u8            *g_txbuf;
static unsigned long  g_txlen, g_txcap;

static void host_tcp_reset(void)
{
    memset(&g_listen_pcb, 0, sizeof g_listen_pcb);
    memset(&g_client_pcb, 0, sizeof g_client_pcb);
    g_client_pcb.sndbuf = 8192;
    g_txlen = 0;
}

struct tcp_pcb *host_tcp_client(void) { return &g_client_pcb; }

const u8 *host_tcp_txbuf(unsigned long *len) { if (len) *len = g_txlen; return g_txbuf; }
void host_tcp_txbuf_reset(void) { g_txlen = 0; }

struct tcp_pcb *tcp_new(void) { return &g_listen_pcb; }
err_t tcp_bind(struct tcp_pcb *pcb, void *ip, u16 port) { (void)pcb; (void)ip; (void)port; return ERR_OK; }
struct tcp_pcb *tcp_listen(struct tcp_pcb *pcb) { return pcb; }
void tcp_accept(struct tcp_pcb *pcb, tcp_accept_fn f) { pcb->accept_cb = f; }
void tcp_arg(struct tcp_pcb *pcb, void *arg) { pcb->cb_arg = arg; }
void tcp_recv(struct tcp_pcb *pcb, tcp_recv_fn f) { pcb->recv_cb = f; }
void tcp_poll(struct tcp_pcb *pcb, tcp_poll_fn f, u8 iv) { (void)iv; pcb->poll_cb = f; }
err_t tcp_close(struct tcp_pcb *pcb) { pcb->closed = 1; host_trace_add("TCP CLOSE"); return ERR_OK; }
void tcp_abort(struct tcp_pcb *pcb) { pcb->aborted = 1; host_trace_add("TCP ABORT"); }
void tcp_nagle_disable(struct tcp_pcb *pcb) { pcb->nagle_off = 1; }
void tcp_recved(struct tcp_pcb *pcb, u16 len) { (void)pcb; (void)len; }
u16  tcp_sndbuf(struct tcp_pcb *pcb) { return pcb->sndbuf; }

err_t tcp_write(struct tcp_pcb *pcb, const void *data, u16 len, u8 flags)
{
    (void)flags;
    if (pcb == NULL || pcb->closed) return ERR_ARG;
    if (len > pcb->sndbuf) return ERR_MEM;
    if (g_txlen + len > g_txcap) {
        g_txcap = (g_txlen + len) * 2 + 4096;
        g_txbuf = (u8 *)realloc(g_txbuf, g_txcap);
        if (!g_txbuf) { fprintf(stderr, "[hostenv] OOM in txbuf\n"); exit(2); }
    }
    memcpy(g_txbuf + g_txlen, data, len);
    g_txlen += len;
    pcb->sndbuf = (u16)(pcb->sndbuf - len);
    pcb->unsent = (struct tcp_seg *)1;
    host_trace_add("TCP WRITE %u", (unsigned)len);
    return ERR_OK;
}

err_t tcp_output(struct tcp_pcb *pcb)
{
    if (pcb) {
        pcb->sndbuf = 8192;   /* 模拟窗口被 ACK 打开 */
        pcb->unsent = NULL;
        pcb->unacked = NULL;
    }
    host_trace_add("TCP OUTPUT");
    return ERR_OK;
}

u16 pbuf_copy_partial(const struct pbuf *p, void *dst, u16 len, u16 off)
{
    if (off >= p->tot_len) return 0;
    if (len > p->tot_len - off) len = (u16)(p->tot_len - off);
    memcpy(dst, (const u8 *)p->payload + off, len);
    return len;
}

void pbuf_free(struct pbuf *p) { (void)p; }

/*============================================================================
 * 10) 网卡喂食
 *==========================================================================*/
static struct netif g_netif;
struct netif *echo_netif = &g_netif;
void xemacif_input(struct netif *n) { (void)n; host_trace_add("NETIF INPUT"); }

/*============================================================================
 * 11) 全局定时器：确定性时间（每次 host_hw_tick() 前进 300 ms，
 *     贴近实测的 250~500 ms poll 间隔）。轨迹不记时间值，只有固件日志会用到。
 *==========================================================================*/
#include "xtime_l.h"
static XTime g_xtime = 0;
void XTime_GetTime(XTime *t) { if (t) *t = g_xtime; }
void host_time_advance_one_poll(void) { g_xtime += (XTime)(COUNTS_PER_SECOND * 3U / 10U); }
