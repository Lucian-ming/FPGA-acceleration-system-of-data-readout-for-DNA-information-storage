/******************************************************************************
 * pipeline.h — PS 固件处理流水线核心状态与接口定义
 ******************************************************************************/
#ifndef __PIPELINE_H__
#define __PIPELINE_H__

#include "xil_types.h"
#include "echo.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 流水线状态枚举 */
typedef enum {
    PIPE_IDLE = 0,
    PIPE_WM_PREP,
    /* 【WM 批量化】原来这里还有一个 PIPE_WM_WAIT：PIPE_WM_TX 提交 DMA、下一个 poll 才由
     * PIPE_WM_WAIT 回收 BD，于是 50 个区域各占 2 个 poll 周期 ≈ 100 步。
     * 现在 PIPE_WM_TX 一次 poll 批量走 WM_REGIONS_PER_POLL 个区域、区域内有界忙等，
     * WM_WAIT 变成死状态，直接删掉，见 pipeline_step_stage1() 的 PIPE_WM_TX 分支。 */
    PIPE_WM_TX,
    PIPE_RX_PREP,
    PIPE_TX_PREFILL,
    PIPE_START_IP,
    PIPE_TX_STREAM,
    PIPE_PROGRESS,
    PIPE_DONE_STAGE1,

    /* 第二级: Voter */
    PIPE_VOTER_PREP,
    PIPE_VOTER_START,
    PIPE_VOTER_WAIT,
    PIPE_DONE_STAGE2,
    PIPE_SEND_RESULT,
    /* 第三级: Decoder */
    PIPE_DECODER_PREP,
    PIPE_DECODER_START,
    PIPE_DECODER_WAIT,
    PIPE_DONE_STAGE3,

    PIPE_FAIL
} pipe_state_e;

typedef enum {
    PIPE_STEP_PROGRESS = 1,
    PIPE_STEP_DONE     = 0,
    PIPE_STEP_FAIL     = -1
} pipe_step_rc_e;

extern volatile pipe_state_e pipe_state;

static inline void pipeline_set_state(pipe_state_e st)
{
    pipe_state = st;
}

#ifdef __cplusplus
}
#endif

#endif /* __PIPELINE_H__ */
