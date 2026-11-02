/******************************************************************************
 * pipeline.c — PS 固件流水线状态全局变量
 ******************************************************************************/
#include "pipeline.h"

volatile pipe_state_e pipe_state = PIPE_IDLE;
u32 pipe_poll_steps = 0;
XTime pipe_t_start = 0;
