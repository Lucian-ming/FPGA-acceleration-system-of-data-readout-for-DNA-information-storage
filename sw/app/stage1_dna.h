/******************************************************************************
 * stage1_dna.h — PS 固件第一阶段流水线 (DNA 加速器、水印展开预载与滑动窗)
 ******************************************************************************/
#ifndef __STAGE1_DNA_H__
#define __STAGE1_DNA_H__

#include "xil_types.h"
#include "pipeline.h"

#ifdef __cplusplus
extern "C" {
#endif

void pipeline_reset_counters(void);
pipe_step_rc_e pipeline_step_stage1(dna_connection_t *conn);

#ifdef __cplusplus
}
#endif

#endif /* __STAGE1_DNA_H__ */
