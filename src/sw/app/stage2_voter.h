/******************************************************************************
 * stage2_voter.h — PS 固件第二阶段流水线 (差分投票器与共识水印差分)
 ******************************************************************************/
#ifndef __STAGE2_VOTER_H__
#define __STAGE2_VOTER_H__

#include "xil_types.h"
#include "pipeline.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Voter 寄存器偏移 fallback */
#ifndef VOTER_REG_DBG_STATE
#define VOTER_REG_DBG_STATE     0x18u
#endif
#ifndef VOTER_REG_DBG_WRITE
#define VOTER_REG_DBG_WRITE     0x24u
#endif
#ifndef VOTER_REG_ERR_FLAGS
#define VOTER_REG_ERR_FLAGS     0x2Cu
#endif
#ifndef VOTER_DBG_ERROR_STATE
#define VOTER_DBG_ERROR_STATE   16u
#endif
#ifndef VOTER_ERR_FLAGS_MASK
#define VOTER_ERR_FLAGS_MASK    0x3u
#endif

int voter_configure_and_verify(const dna_connection_t *conn);
pipe_step_rc_e pipeline_step_stage2(dna_connection_t *conn);
int apply_watermark_differential(void);

#ifdef __cplusplus
}
#endif

#endif /* __STAGE2_VOTER_H__ */
