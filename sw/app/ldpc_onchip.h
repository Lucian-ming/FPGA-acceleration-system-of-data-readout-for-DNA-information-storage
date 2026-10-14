/******************************************************************************
 * ldpc_onchip.h — PS 侧片上 LDPC 译码器轮询流程
 ******************************************************************************/
#ifndef __LDPC_ONCHIP_H__
#define __LDPC_ONCHIP_H__

#include "pipeline.h"

#ifdef __cplusplus
extern "C" {
#endif

pipe_step_rc_e pipeline_step_ldpc(void);

#ifdef __cplusplus
}
#endif

#endif /* __LDPC_ONCHIP_H__ */
