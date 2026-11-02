/******************************************************************************
 * reg_timing.h — PS 固件寄存器写序列与时序控制
 *
 * 将散落在各流水级的寄存器读写收敛为具名序列，严格维持原有时序、延时、写序列，
 * 正面回应 B27（START 脉冲语义与beats写入顺序）。
 ******************************************************************************/
#ifndef __REG_TIMING_H__
#define __REG_TIMING_H__

#include "xil_types.h"
#include "echo.h"
#include "sleep.h"

#ifdef __cplusplus
extern "C" {
#endif

/*============================================================================
 * 1. DNA Accelerator (Stage1 比对引擎) 时序序列
 *============================================================================*/

/* 选择水印区域：写 REG1_WMSEL -> usleep(10) */
void dna_select_wm_region(u32 wm_region);

/* 进入预载模式：写 REG0_CTRL(PRELOAD) -> usleep(10) */
void dna_enter_preload(void);

/* 离开预载模式：写 REG0_CTRL(0) -> usleep(10) */
void dna_leave_preload(void);

/* 启动 DNA 比对：写 REG0_CTRL(1) -> usleep(50)（严禁使用死函数 trigger_ip_start 的时序） */
void dna_start(void);

/* 停止/复位 DNA 控制寄存器：写 REG0_CTRL(0) */
void dna_stop(void);

/*============================================================================
 * 2. Differential Voter (Stage2 投票核) 时序序列
 *============================================================================*/

/* 写入 Voter 6 项配置寄存器并延时 usleep(10) */
void voter_write_config(u32 in_addr, u32 in_beats, u32 out_addr, u32 out_beats,
                        u32 total_reads, u32 score_min);

/* 清除 Voter 完成标志：写 START=0x02 -> usleep(500) -> 写 START=0x00 -> usleep(100) */
void voter_clear_done(void);

/* 复位 Voter 寄存器：写 START=0，beats/total_reads 写 0 -> usleep(2000) */
void voter_reset_regs(void);

/* Voter START 前置检查序列：写 0 -> usleep(100) -> 读 STATUS 并返回 */
u32 voter_prestart(void);

/* 发送 Voter START 短脉冲：写 1 -> usleep(100) -> 写 0 -> usleep(100) -> 读 STATUS */
void voter_start_pulse(u32 *status_after);

/* 读取 Voter STATUS 寄存器 */
static inline u32 voter_read_status(void) {
    return read_reg32(VOTER_BASEADDR, VOTER_REG_STATUS);
}

/* 清除 Voter START 寄存器（写 0） */
static inline void voter_clear_start(void) {
    write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x00);
}

/*============================================================================
 * 3. Desparsification Decoder (Stage3 解码核) 时序序列
 *============================================================================*/

/* 复位 Decoder 寄存器：写 START=0，beats 写 0 */
void decoder_reset_regs(void);

/* 预置/确认 Decoder 空闲状态：写 START=0 -> usleep(1000) */
void decoder_confirm_idle_zero(void);

/* 写入 Decoder 配置：
 * 必须按固定时序：写 IN_ADDR -> usleep(100) -> 写 OUT_ADDR -> usleep(100) ->
 * 写 OUT_BEATS -> usleep(100) -> 最后写 IN_BEATS -> usleep(100)（响应 B27） */
void decoder_configure(u32 in_addr, u32 out_addr, u32 out_beats, u32 in_beats);

/* 写入默认 Decoder 配置（DEC_IN_ADDR, DEC_OUT_ADDR, DEC_OUT_BEATS, DEC_IN_BEATS） */
void decoder_configure_default(void);

/* 启动 Decoder 核：只写一次 START=1 -> usleep(100)，期间不再碰 START（正面回应 B27-③） */
void decoder_start_once(void);

/* 读取 Decoder STATUS 寄存器 */
static inline u32 decoder_read_status(void) {
    return read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);
}

/* 清除 Decoder START 寄存器（写 0） */
static inline void decoder_clear_start(void) {
    write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
}

#ifdef __cplusplus
}
#endif

#endif /* __REG_TIMING_H__ */
