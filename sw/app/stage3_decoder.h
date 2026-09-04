/******************************************************************************
 * stage3_decoder.h — PS 固件第三阶段流水线 (5b4b 解码与反稀疏化)
 ******************************************************************************/
#ifndef __STAGE3_DECODER_H__
#define __STAGE3_DECODER_H__

#include "xil_types.h"
#include "pipeline.h"

#ifdef __cplusplus
extern "C" {
#endif

int validate_decoder_written_beats(u32 out_addr, u32 total_beats, u32 *written_beats);

pipe_step_rc_e pipeline_step_stage3(dna_connection_t *conn);

#ifdef __cplusplus
}
#endif

#endif /* __STAGE3_DECODER_H__ */
