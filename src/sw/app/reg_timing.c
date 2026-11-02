/******************************************************************************
 * reg_timing.c — PS 固件寄存器写序列与时序控制实现
 ******************************************************************************/
#include "reg_timing.h"
#include "echo.h"
#include "sleep.h"

/*============================================================================
 * 1. DNA Accelerator (Stage1 比对引擎)
 *============================================================================*/

void dna_select_wm_region(u32 wm_region)
{
    write_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG1_WMSEL, wm_region);
    usleep(10);
}

void dna_enter_preload(void)
{
    write_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG0_CTRL, DNA_ACC_CTRL_BIT_PRELOAD);
    usleep(10);
}

void dna_leave_preload(void)
{
    write_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG0_CTRL, 0x00);
    usleep(10);
}

void dna_start(void)
{
    write_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG0_CTRL, 0x01);
    usleep(50);
}

void dna_stop(void)
{
    write_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG0_CTRL, 0x00);
}

/*============================================================================
 * 2. Differential Voter (Stage2 投票核)
 *============================================================================*/

void voter_write_config(u32 in_addr, u32 in_beats, u32 out_addr, u32 out_beats,
                        u32 total_reads, u32 score_min)
{
    write_reg32(VOTER_BASEADDR, VOTER_REG_IN_ADDR, in_addr);
    write_reg32(VOTER_BASEADDR, VOTER_REG_IN_BEATS, in_beats);
    write_reg32(VOTER_BASEADDR, VOTER_REG_OUT_ADDR, out_addr);
    write_reg32(VOTER_BASEADDR, VOTER_REG_OUT_BEATS, out_beats);
    write_reg32(VOTER_BASEADDR, VOTER_REG_TOTAL_READS, total_reads);
    write_reg32(VOTER_BASEADDR, VOTER_REG_SCORE_MIN, score_min);
    __asm__ volatile("dsb sy");
    __asm__ volatile("isb");
    usleep(10);
}

void voter_clear_done(void)
{
    write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x02);  /* bit1=1: done_clr */
    usleep(500);                                         /* 短延时足够 */
    write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x00);  /* 拉回0 */
    usleep(100);
}

void voter_reset_regs(void)
{
    write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x00);
    write_reg32(VOTER_BASEADDR, VOTER_REG_IN_BEATS, 0);
    write_reg32(VOTER_BASEADDR, VOTER_REG_OUT_BEATS, 0);
    write_reg32(VOTER_BASEADDR, VOTER_REG_TOTAL_READS, 0);
    usleep(2000);
}

u32 voter_prestart(void)
{
        write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x00);
        usleep(100);

        u32 status_before_start = read_reg32(VOTER_BASEADDR, VOTER_REG_STATUS);
    return status_before_start;
}

void voter_start_pulse(u32 *status_after)
{
    write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x01);
    usleep(100);
    write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x00);
    usleep(100);

    u32 status_after_start = read_reg32(VOTER_BASEADDR, VOTER_REG_STATUS);
    if (status_after) *status_after = status_after_start;
}

/*============================================================================
 * 3. Desparsification Decoder (Stage3 解码核)
 *============================================================================*/

void decoder_reset_regs(void)
{
    write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
    write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, 0);
    write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, 0);
}

void decoder_confirm_idle_zero(void)
{
    write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);  // 再次确认
    usleep(1000);
}

void decoder_configure(u32 in_addr, u32 out_addr, u32 out_beats, u32 in_beats)
{
    write_reg32(DECODER_BASEADDR, DECODER_REG_IN_ADDR,  in_addr);
    usleep(100);
    write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_ADDR, out_addr);
    usleep(100);
    write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, out_beats);
    usleep(100);
    write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, in_beats);
    __asm__ volatile("dsb sy");
    __asm__ volatile("isb");
    usleep(10);
}

static const u32 DEC_IN_ADDR  = DDR_VOTER_OUT_BASE;
static const u32 DEC_OUT_ADDR = DDR_DECODER_OUT_BASE;
static const u32 DEC_IN_BEATS = DECODER_INPUT_BEATS;
static const u32 DEC_OUT_BEATS = DECODER_OUTPUT_BEATS;

void decoder_configure_default(void)
{
    write_reg32(DECODER_BASEADDR, DECODER_REG_IN_ADDR,  DEC_IN_ADDR);
    usleep(100);
    write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_ADDR, DEC_OUT_ADDR);
    usleep(100);
	        write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, DEC_OUT_BEATS);
	        usleep(100);
	        write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, DEC_IN_BEATS);  // 最后写
    __asm__ volatile("dsb sy");
    __asm__ volatile("isb");
    usleep(10);
}

void decoder_start_once(void)
{
	        write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x01);
	        usleep(100);  /* 只是让 START 在 M 域被采样，期间不再碰这个寄存器 */
}
