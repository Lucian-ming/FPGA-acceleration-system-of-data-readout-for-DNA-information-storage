#ifndef __HOSTENV_H__
#define __HOSTENV_H__
/******************************************************************************
 * hostenv.h — 让**未经修改的** sw/app/echo.c 在 x86 主机上跑起来的环境模型
 *
 * 三件事：
 *   1) 假 DDR：用 mmap(MAP_FIXED) 把 0x10000000..0x12000000 映到进程地址空间，
 *      于是 echo.c 里 `memcpy((void *)DDR_WATERMARK_BASE, ...)` 这种**绝对地址**
 *      解引用可以原样工作，不需要改一个字节的固件代码。
 *   2) 设备模型：三个 IP 核 + AXI DMA 的行为模型，节奏由 host_hw_tick() 推进
 *      （一次 tick = 一个 lwIP poll 周期之间硬件干的活）。
 *   3) 轨迹录制：寄存器读写、缓存维护、usleep、DMA 投递/回收、TCP 发送
 *      全部按发生顺序记成文本。**拆分前后这份轨迹必须逐行相同** —— 这就是
 *      sim/host/readme.md 说的「行为等价」判据。
 *
 * 轨迹里刻意**不含** xil_printf 的日志文本：日志措辞可以改，行为不可以。
 ******************************************************************************/
#include <stdio.h>
#include "xil_types.h"

/*==== 假 DDR ================================================================*/
#define HOST_DDR_BASE   0x10000000UL
#define HOST_DDR_SIZE   0x02000000UL   /* 32 MB，覆盖到 RX BD 空间 0x11910000 */

void host_env_init(void);      /* 映射假 DDR、清零、复位设备模型与轨迹 */
void host_env_fini(void);

/*==== 轨迹 ==================================================================*/
void host_trace_enable(int on);
void host_trace_clear(void);
void host_trace_add(const char *fmt, ...);
unsigned long host_trace_lines(void);
int  host_trace_write(const char *path);
/* 与黄金轨迹逐行比对；不同则打印首个差异行并返回非 0 */
int  host_trace_compare(const char *golden_path, const char *what);

/*==== 硬件模型 ==============================================================*/
typedef enum {
    HOST_DEC_FIXED  = 0,   /* B27 修复后的 RTL：只认 wdata[0]=1，且忙时不接受 */
    HOST_DEC_LEGACY = 1    /* B27 之前：对 START 写任何值都启动（用于鉴别力自证） */
} host_dec_mode_e;

typedef struct {
    unsigned result_fifo_depth;  /* DNA 核结果 FIFO 深度（条）。满了就停 MM2S，
                                  * 这是 B21 那条「S2MM Idle → 反压 → 整链锁死」
                                  * 的成因，模型如实复现 */
    unsigned voter_busy_ticks;   /* Voter 从 START 到 DONE 需要几个 poll */
    unsigned dec_busy_ticks;     /* Decoder 从 START 到 DONE 需要几个 poll */
    host_dec_mode_e dec_mode;
} host_hw_cfg_t;

extern host_hw_cfg_t host_hw_cfg;

void host_hw_tick(void);          /* 推进一个 poll 周期的硬件时间 */
void host_time_advance_one_poll(void);   /* 全局定时器前进一个 poll（~300 ms） */
unsigned host_dna_records_made(void);
unsigned host_dna_reads_fed(void);
unsigned host_wm_regions_loaded(void);
int      host_wm_region_len_ok(void);   /* 每个区域收到的符号数是否都等于 REF_LEN */
int      host_dec_start_writes(void);   /* 对 Decoder START 寄存器写了几次 */
int      host_dec_start_pulses(void);   /* 其中真正被核接受为「启动」的有几次 */
int      host_dna_stalled(void);        /* MM2S 是否因结果 FIFO 满而停摆 */

/*==== lwIP 侧观测 ===========================================================*/
struct tcp_pcb;
struct tcp_pcb *host_tcp_client(void);      /* 测试用的「客户端」pcb */
const u8 *host_tcp_txbuf(unsigned long *len);  /* 板端已发出的全部字节 */
void      host_tcp_txbuf_reset(void);

/*==== 日志 ==================================================================*/
const char *host_log_tail(void);   /* 最近的固件日志，失败时打出来定位 */

#endif /* __HOSTENV_H__ */
