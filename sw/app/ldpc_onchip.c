/******************************************************************************
 * ldpc_onchip.c — 通过 AXI4-Lite 装载并轮询片上 LDPC 译码器
 ******************************************************************************/
#include "ldpc_onchip.h"

#include "echo.h"
#include "xparameters.h"
#include "xil_cache.h"
#include "xil_io.h"
#include "xil_printf.h"
#include "dna_time.h"

#ifndef XPAR_LDPC_DECODER_0_BASEADDR
#error "当前 XSA 的 BSP 未生成 XPAR_LDPC_DECODER_0_BASEADDR"
#endif

#define LDPC_BASEADDR              ((UINTPTR)XPAR_LDPC_DECODER_0_BASEADDR)
#define LDPC_REG_CONTROL           0x00U
#define LDPC_REG_STATUS            0x04U
#define LDPC_REG_LOAD_WORD_ADDR    0x08U
#define LDPC_REG_LOAD_WORD_DATA    0x0CU
#define LDPC_REG_RESULT_WORD_ADDR  0x10U
#define LDPC_REG_RESULT_WORD_DATA  0x14U

#define LDPC_CONTROL_START         (1U << 0)
#define LDPC_CONTROL_RESET         (1U << 1)
#define LDPC_STATUS_BUSY           (1U << 0)
#define LDPC_STATUS_DONE           (1U << 1)
#define LDPC_STATUS_CONVERGED      (1U << 2)
#define LDPC_STATUS_ERROR          (1U << 3)
#define LDPC_STATUS_LOADING        (1U << 4)
#define LDPC_STATUS_READBACK       (1U << 5)
#define LDPC_STATUS_ITER_SHIFT     8U
#define LDPC_STATUS_ITER_MASK      0xFFU

#define LDPC_CODEWORD_BYTES       DECODER_OUTPUT_BYTES
#define LDPC_CODEWORD_WORDS       (LDPC_CODEWORD_BYTES / 4U)
#define LDPC_WORDS_PER_STEP       32U
#define LDPC_RUN_TIMEOUT_SECONDS  120U

#if (LDPC_CODEWORD_BYTES != 8100U) || ((LDPC_CODEWORD_BYTES % 4U) != 0U)
#error "片上 LDPC 接口要求 8100 字节（2025 个完整 32 位字）"
#endif

typedef enum {
    LDPC_PHASE_LOAD = 0,
    LDPC_PHASE_WAIT
} ldpc_phase_e;

static ldpc_phase_e ldpc_phase;
static u32 ldpc_word_index;
static s32 ldpc_iterations;
static XTime ldpc_start_time;

static s32 ldpc_status_iterations(u32 status)
{
    u32 raw = (status >> LDPC_STATUS_ITER_SHIFT) & LDPC_STATUS_ITER_MASK;
    return (raw & 0x80U) ? ((s32)raw - 0x100) : (s32)raw;
}

static u32 ldpc_load_word(const volatile u8 *bytes, u32 word_index)
{
    u32 offset = word_index * 4U;
    return ((u32)bytes[offset]) |
           ((u32)bytes[offset + 1U] << 8) |
           ((u32)bytes[offset + 2U] << 16) |
           ((u32)bytes[offset + 3U] << 24);
}

static void ldpc_write_result_word(volatile u8 *bytes, u32 word_index,
                                   u32 value)
{
    u32 offset = word_index * 4U;
    bytes[offset]       = (u8)(value & 0xFFU);
    bytes[offset + 1U] = (u8)((value >> 8) & 0xFFU);
    bytes[offset + 2U] = (u8)((value >> 16) & 0xFFU);
    bytes[offset + 3U] = (u8)((value >> 24) & 0xFFU);
}

static void ldpc_keep_original_and_finish(u32 status, u32 timed_out)
{
    u32 error = (status & LDPC_STATUS_ERROR) != 0U;
    u32 converged = ((status & LDPC_STATUS_CONVERGED) != 0U) &&
                    !error && !timed_out;

    ldpc_iterations = ldpc_status_iterations(status);
    xil_printf("[LDPC] converged=%u iterations=%d error=%u timeout=%u; 保留 Stage3 原码字\n\r",
               converged, ldpc_iterations, error, timed_out);
    pipeline_set_state(PIPE_SEND_RESULT);
}

pipe_step_rc_e pipeline_step_ldpc(void)
{
    switch (pipe_state) {
    case PIPE_LDPC_PREP: {
        Xil_DCacheInvalidateRange((INTPTR)DDR_DECODER_OUT_BASE,
                                  LDPC_CODEWORD_BYTES);
        __asm__ volatile("dsb sy" ::: "memory");

        /* reset 是单次脉冲，同时清除上一次的 sticky done。 */
        Xil_Out32(LDPC_BASEADDR + LDPC_REG_CONTROL, LDPC_CONTROL_RESET);
        ldpc_word_index = 0U;
        ldpc_iterations = 0;
        ldpc_phase = LDPC_PHASE_LOAD;
        xil_printf("[LDPC] loading %u bytes as %u LSB-first words\n\r",
                   (u32)LDPC_CODEWORD_BYTES, (u32)LDPC_CODEWORD_WORDS);
        pipeline_set_state(PIPE_LDPC_RUN);
        return PIPE_STEP_PROGRESS;
    }

    case PIPE_LDPC_RUN: {
        if (ldpc_phase == LDPC_PHASE_LOAD) {
            const volatile u8 *source =
                (const volatile u8 *)DDR_DECODER_OUT_BASE;
            u32 words_this_step = 0U;

            while ((ldpc_word_index < LDPC_CODEWORD_WORDS) &&
                   (words_this_step < LDPC_WORDS_PER_STEP)) {
                u32 value = ldpc_load_word(source, ldpc_word_index);
                Xil_Out32(LDPC_BASEADDR + LDPC_REG_LOAD_WORD_ADDR,
                          ldpc_word_index);
                /* 此写响应在硬件完成该字的 32 次核心装载后才返回。 */
                Xil_Out32(LDPC_BASEADDR + LDPC_REG_LOAD_WORD_DATA, value);
                ldpc_word_index++;
                words_this_step++;
            }

            if (ldpc_word_index == LDPC_CODEWORD_WORDS) {
                Xil_Out32(LDPC_BASEADDR + LDPC_REG_CONTROL,
                          LDPC_CONTROL_START);
                XTime_GetTime(&ldpc_start_time);
                ldpc_phase = LDPC_PHASE_WAIT;
            }
            return PIPE_STEP_PROGRESS;
        }

        {
            u32 status = Xil_In32(LDPC_BASEADDR + LDPC_REG_STATUS);
            u32 done = (status & LDPC_STATUS_DONE) != 0U;
            u32 converged = (status & LDPC_STATUS_CONVERGED) != 0U;
            u32 error = (status & LDPC_STATUS_ERROR) != 0U;
            u32 inactive = (status & (LDPC_STATUS_BUSY |
                                      LDPC_STATUS_LOADING |
                                      LDPC_STATUS_READBACK)) == 0U;
            XTime now;

            if (done && inactive && converged && !error) {
                ldpc_iterations = ldpc_status_iterations(status);
                ldpc_word_index = 0U;
                xil_printf("[LDPC] converged=1 iterations=%d; reading corrected codeword\n\r",
                           ldpc_iterations);
                pipeline_set_state(PIPE_LDPC_READBACK);
                return PIPE_STEP_PROGRESS;
            }

            if (error || (done && inactive && !converged)) {
                ldpc_keep_original_and_finish(status, 0U);
                return PIPE_STEP_PROGRESS;
            }

            XTime_GetTime(&now);
            if ((now - ldpc_start_time) >
                DNA_TIMEOUT_TICKS(LDPC_RUN_TIMEOUT_SECONDS)) {
                ldpc_keep_original_and_finish(status, 1U);
            }
            return PIPE_STEP_PROGRESS;
        }
    }

    case PIPE_LDPC_READBACK: {
        volatile u8 *destination = (volatile u8 *)DDR_DECODER_OUT_BASE;
        u32 words_this_step = 0U;

        while ((ldpc_word_index < LDPC_CODEWORD_WORDS) &&
               (words_this_step < LDPC_WORDS_PER_STEP)) {
            u32 value;

            Xil_Out32(LDPC_BASEADDR + LDPC_REG_RESULT_WORD_ADDR,
                      ldpc_word_index);
            /* 读数据寄存器触发硬件同步读回本字的 32 个结果位。 */
            value = Xil_In32(LDPC_BASEADDR + LDPC_REG_RESULT_WORD_DATA);
            ldpc_write_result_word(destination, ldpc_word_index, value);
            ldpc_word_index++;
            words_this_step++;
        }

        if (ldpc_word_index == LDPC_CODEWORD_WORDS) {
            Xil_DCacheFlushRange((INTPTR)DDR_DECODER_OUT_BASE,
                                 LDPC_CODEWORD_BYTES);
            __asm__ volatile("dsb sy" ::: "memory");
            xil_printf("[LDPC] converged=1 iterations=%d; wrote back %u words\n\r",
                       ldpc_iterations, (u32)LDPC_CODEWORD_WORDS);
            pipeline_set_state(PIPE_SEND_RESULT);
        }
        return PIPE_STEP_PROGRESS;
    }

    default:
        return PIPE_STEP_PROGRESS;
    }
}
