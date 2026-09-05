/******************************************************************************
 * stage2_voter.c — PS 固件第二阶段流水线实现
 *
 * 包含 voter_configure_and_verify、pipeline_step_stage2、apply_watermark_differential。
 ******************************************************************************/

#include "stage2_voter.h"
#include "reg_timing.h"
#include "fw_log.h"
#include "ddr_layout.h"
#include "xil_printf.h"
#include "xil_cache.h"
#include "sleep.h"

int voter_configure_and_verify(const dna_connection_t *conn)
{
    const u32 in_addr = DDR_VOTER_IN_BASE;
    const u32 out_addr = DDR_VOTER_OUT_BASE;
    const u32 total_reads = conn->total_reads_received;
    const u32 in_beats = total_reads * (VOTER_INPUT_BYTES_PER_READ / 8u);
    const u32 out_beats = VOTER_OUTPUT_BEATS;
    const u32 score_min = conn->cfg.score_min;

    xil_printf("[STAGE2] Configuration:\n\r");
    xil_printf("  IN_ADDR:     0x%08X\n\r", in_addr);
    xil_printf("  IN_BEATS:    %u (%u beats/read)\n\r", in_beats, (VOTER_INPUT_BYTES_PER_READ / 8u));
    xil_printf("  OUT_ADDR:    0x%08X\n\r", out_addr);
    xil_printf("  OUT_BEATS:   %u\n\r", out_beats);
    xil_printf("  TOTAL_READS: %u\n\r", total_reads);
    xil_printf("  SCORE_MIN:   %u\n\r", score_min);

    voter_write_config(in_addr, in_beats, out_addr, out_beats, total_reads, score_min);

    const u32 in_addr_rb = read_reg32(VOTER_BASEADDR, VOTER_REG_IN_ADDR);
    const u32 in_beats_rb = read_reg32(VOTER_BASEADDR, VOTER_REG_IN_BEATS);
    const u32 out_addr_rb = read_reg32(VOTER_BASEADDR, VOTER_REG_OUT_ADDR);
    const u32 out_beats_rb = read_reg32(VOTER_BASEADDR, VOTER_REG_OUT_BEATS);
    const u32 total_reads_rb = read_reg32(VOTER_BASEADDR, VOTER_REG_TOTAL_READS);
    const u32 score_min_rb = read_reg32(VOTER_BASEADDR, VOTER_REG_SCORE_MIN);

    if (in_addr_rb != in_addr || in_beats_rb != in_beats ||
        out_addr_rb != out_addr || out_beats_rb != out_beats ||
        total_reads_rb != total_reads || score_min_rb != score_min) {
        xil_printf("[ERROR] Voter configuration readback mismatch:\n\r");
        xil_printf("  IN_ADDR     0x%08X != 0x%08X\n\r", in_addr_rb, in_addr);
        xil_printf("  IN_BEATS    %u != %u\n\r", in_beats_rb, in_beats);
        xil_printf("  OUT_ADDR    0x%08X != 0x%08X\n\r", out_addr_rb, out_addr);
        xil_printf("  OUT_BEATS   %u != %u\n\r", out_beats_rb, out_beats);
        xil_printf("  TOTAL_READS %u != %u\n\r", total_reads_rb, total_reads);
        xil_printf("  SCORE_MIN   %u != %u\n\r", score_min_rb, score_min);
        return XST_FAILURE;
    }

    xil_printf("[STAGE2] Configuration readback verified\n\r");
    return XST_SUCCESS;
}

pipe_step_rc_e pipeline_step_stage2(dna_connection_t *conn)
{
    switch (pipe_state) {

    /* ========================================================================
     * PIPE_VOTER_PREP: Voter准备阶段
     * ======================================================================== */
    case PIPE_VOTER_PREP: {
        xil_printf("\n\r========================================\n\r");
        xil_printf("[STAGE2] Voter Preparation\n\r");
        xil_printf("========================================\n\r");
        // clear_voter_out_region();

        /* 【C1】本次任务的实际记录数：含上位机补零的尾批记录。
         * 补零记录 score=0，会被 SCORE_MIN 过滤，不参与投票。 */
        const u32 task_reads = conn->total_reads_received;
        const u32 task_in_bytes = (u32)ddr_layout_stage1_bytes(task_reads,
                                                    DNA_ACC_RESULT_PACKED_BYTES);

        // ✅ Cache一致性修复: Invalidate输入区域cache（按实际大小，不按预留容量）
        xil_printf("[STAGE2] Invalidating input cache (%u bytes)...\n\r", task_in_bytes);
        const u32 VOTER_IN_TEMP = DDR_VOTER_IN_BASE;
        const u32 INV_CHUNK = 256*1024;
        u32 inv_done = 0;

        while (inv_done < task_in_bytes) {
            u32 chunk = (task_in_bytes - inv_done > INV_CHUNK)
                        ? INV_CHUNK
                        : (task_in_bytes - inv_done);
            Xil_DCacheInvalidateRange(VOTER_IN_TEMP + inv_done, chunk);
            inv_done += chunk;
        }

        __asm__ volatile("dsb sy");
        __asm__ volatile("isb");
        usleep(1000);

        xil_printf("[STAGE2] ✓ Cache invalidated (%u bytes)\n\r", inv_done);

        pipeline_set_state(PIPE_VOTER_START);
        return PIPE_STEP_PROGRESS;
    }
    /* ========================================================================
     * PIPE_VOTER_START: 配置并启动Voter IP核
     * ======================================================================== */
    case PIPE_VOTER_START: {
        xil_printf("\n\r========================================\n\r");
        xil_printf("[STAGE2] Starting Voter IP Core\n\r");
        xil_printf("========================================\n\r");

        const u32 voter_in_addr      = DDR_DNA_ACC_OUT_BASE;
        const u32 voter_total_reads  = conn->total_reads_received;  /* [C1] 实际条数 */

        /* -------------------- Pre-start Input Validation（全部字节视图） -------------------- */
        xil_printf("\n\r[STAGE2] Pre-start Input Validation:\n\r");
        Xil_DCacheInvalidateRange(voter_in_addr, VOTER_INPUT_BYTES_PER_READ * 10U);
        __asm__ volatile("dsb sy"); __asm__ volatile("isb");
        usleep(1000);

        /* 统计前 10 个 read 的非零字节 */
        const volatile u8 *vin = (const volatile u8 *)voter_in_addr;
        u32 nz = 0;
        for (u32 i = 0; i < 10U * VOTER_INPUT_BYTES_PER_READ; i++) if (vin[i] != 0) nz++;
        xil_printf("  Non-zero bytes: %u / %u\n\r", nz, 10U * VOTER_INPUT_BYTES_PER_READ);

        /* 打印第 0 个 read 的字节视图 */
        xil_printf("\n\r[DEBUG] First read (%u bytes):\n\r", VOTER_INPUT_BYTES_PER_READ);
        dump_read_48((const void*)voter_in_addr, 0);

        /* 如需：从字节解析 score/position（示例，与你的位域注释一致） */
        const u8 *src = (const u8*)voter_in_addr;
        u16 score = (u16)(src[0] | ((src[1] & 0x03) << 8));                                   /* bits[9:0]  */
        u32 position = ((src[1] >> 2) & 0x3F) | ((u32)src[2] << 6) | ((src[3] & 0x03) << 14); /* bits[25:10] */
        xil_printf("  Parsed Score: %u\n\r", score);
        xil_printf("  Parsed Position: %u\n\r", position);

        if (nz == 0) {
            xil_printf("\n\r[ERROR] ❌ CRITICAL: Stage1→Stage2 input appears all-zero!\n\r");
            xil_printf("[ERROR] Check DMA, IP configuration, or endian conversion.\n\r");
            pipeline_set_state(PIPE_FAIL);
            return PIPE_STEP_FAIL;
        }

        xil_printf("\n\r[STAGE2] ✓ Input validation passed\n\r");
        xil_printf("[STAGE2] Configuration:\n\r");
        xil_printf("  Input format: %u bytes/read (%u beats/read)\n\r",
                   VOTER_INPUT_BYTES_PER_READ, (VOTER_INPUT_BYTES_PER_READ / 8u));
        xil_printf("  TOTAL_READS : %u (HW will auto-read %u beats per read)\n\r",
                   voter_total_reads, (VOTER_INPUT_BYTES_PER_READ / 8u));

        /* -------------------- Step 1: 读取初始状态 -------------------- */
        u32 status_init = read_reg32(VOTER_BASEADDR, VOTER_REG_STATUS);
        xil_printf("\n\r[STAGE2] Initial status: 0x%02X (IDLE=%d, DONE=%d)\n\r",
                   status_init,
                   (status_init & VOTER_STATUS_IDLE) ? 1 : 0,
                   (status_init & VOTER_STATUS_DONE) ? 1 : 0);

        /* -------------------- Step 2: 若 DONE=1，则清一次 DONE -------------------- */
        if (status_init & VOTER_STATUS_DONE) {
            xil_printf("[STAGE2] DONE set at init, clearing...\n\r");
            voter_clear_done();

            u32 st = read_reg32(VOTER_BASEADDR, VOTER_REG_STATUS);
            xil_printf("[STAGE2] Status after clear: 0x%02X (IDLE=%d, DONE=%d)\n\r",
                       st, (st & VOTER_STATUS_IDLE) ? 1 : 0, (st & VOTER_STATUS_DONE) ? 1 : 0);
            if (st & VOTER_STATUS_DONE) {
                xil_printf("[STAGE2] ❌ ERROR: Failed to clear DONE flag!\n\r");
                pipeline_set_state(PIPE_FAIL);
                return PIPE_STEP_FAIL;
            }
            status_init = st;
        }

        /* -------------------- Step 3: 若非 IDLE，则做一次轻量复位 -------------------- */
        if (!(status_init & VOTER_STATUS_IDLE)) {
            xil_printf("[STAGE2] WARNING: Voter not IDLE, resetting config...\n\r");
            voter_reset_regs();

            u32 st = read_reg32(VOTER_BASEADDR, VOTER_REG_STATUS);
            if (!(st & VOTER_STATUS_IDLE)) {
                xil_printf("[STAGE2] ❌ ERROR: Cannot reset Voter to IDLE!\n\r");
                pipeline_set_state(PIPE_FAIL);
                return PIPE_STEP_FAIL;
            }
            xil_printf("[STAGE2] ✓ Reset successful\n\r");
        }

        /* -------------------- Step 4: 唯一配置入口 + 回读校验 -------------------- */
        if (voter_configure_and_verify(conn) != XST_SUCCESS) {
            pipeline_set_state(PIPE_FAIL);
            return PIPE_STEP_FAIL;
        }

        /* -------------------- Step 5: 发送 START 脉冲（简洁稳定版） -------------------- */
        xil_printf("\n\r[START] Sending START pulse to Voter IP core...\n\r");

        u32 status_before_start = voter_prestart();
        xil_printf("[START] Status before START: 0x%02X (IDLE=%d, DONE=%d)\n\r",
                   status_before_start,
                   (status_before_start & VOTER_STATUS_IDLE) ? 1 : 0,
                   (status_before_start & VOTER_STATUS_DONE) ? 1 : 0);

        if (!(status_before_start & VOTER_STATUS_IDLE)) {
            xil_printf("[START] ❌ ERROR: IP core not IDLE before START!\n\r");
            pipeline_set_state(PIPE_FAIL);
            return PIPE_STEP_FAIL;
        }

        /* 发送短脉冲：bit0=1（start），bit1=0（不清done） */
        u32 status_after_start;
        voter_start_pulse(&status_after_start);
        xil_printf("[START] Status after START: 0x%02X (IDLE=%d, DONE=%d)\n\r",
                   status_after_start,
                   (status_after_start & VOTER_STATUS_IDLE) ? 1 : 0,
                   (status_after_start & VOTER_STATUS_DONE) ? 1 : 0);

        if (status_after_start & VOTER_STATUS_IDLE) {
            xil_printf("[START] ⚠️ NOTE: Still IDLE after START (could be ultra-fast or not started)\n\r");
        } else {
            xil_printf("[START] ✓ IP core started (IDLE: 1→0)\n\r");
        }

        xil_printf("[START] ✓ START pulse issued\n\r");
        xil_printf("[STAGE2] Waiting for completion...\n\r");
        xil_printf("[STAGE2] ==========================================\n\r\n\r");

        /* 进入等待状态 */
        pipeline_set_state(PIPE_VOTER_WAIT);
        return PIPE_STEP_PROGRESS;
    }

    /* ========================================================================
     * PIPE_VOTER_WAIT: 轮询等待Voter完成
     * ======================================================================== */
    case PIPE_VOTER_WAIT: {
        static u32 poll_count = 0;
        static u32 poll_cnt = 0;

        /* 读取状态寄存器 */
        u32 status = read_reg32(VOTER_BASEADDR, VOTER_REG_STATUS);
        u32 dbg_state = read_reg32(VOTER_BASEADDR, VOTER_REG_DBG_STATE);
        u32 err_flags = read_reg32(VOTER_BASEADDR, VOTER_REG_ERR_FLAGS);

        /* ERROR/S_ERROR 是硬件失败，不允许依赖 DONE 或输出区哨兵继续向下游走。 */
        if ((status & VOTER_STATUS_ERROR) ||
            dbg_state == VOTER_DBG_ERROR_STATE ||
            (err_flags & VOTER_ERR_FLAGS_MASK) != 0u) {
            xil_printf("\n\r[ERROR] Voter hardware failure: STATUS=0x%02X "
                       "DBG_STATE=%u ERR_FLAGS=0x%08X\n\r",
                       status, dbg_state, err_flags);
            voter_clear_start();
            poll_count = 0;
            poll_cnt = 0;
            pipeline_set_state(PIPE_FAIL);
            return PIPE_STEP_FAIL;
        }

        /* ===== 追加：DONE 之外的“写进度守卫” ===== */
        poll_cnt++;

        if ((poll_cnt % 2000u) == 0u) {  // 每 2000 次轮询做一次内存侧进度检查，避免串口过载
            /* 统计已写拍数：哨兵值被覆盖即视为已写 */
            Xil_DCacheInvalidateRange(DDR_VOTER_OUT_BASE, VOTER_OUTPUT_BEATS * 8u);
            volatile const u64 *p64 = (volatile const u64 *)DDR_VOTER_OUT_BASE;
            u32 written = 0;
            for (u32 i = 0; i < VOTER_OUTPUT_BEATS; ++i) {
                if (p64[i] != 0x55AA55AA55AA550AULL)  /* 你前面清区时的哨兵值 */
                    written++;
            }

            /* ---- 追加：读取硬件调试寄存器，判定所处阶段 ---- */
            if ((poll_cnt % 1000u) == 0u) {
                const u32 dbg_wcnt = read_reg32(VOTER_BASEADDR, VOTER_REG_DBG_WRITE);   // 0x24

                xil_printf("[DBG] STATUS=0x%02X (IDLE=%u,DONE=%u)  FSM=%u  WCOUNT=%u  ERR=0x%X\n\r",
                           status, status & 0x1, (status>>1)&0x1, dbg_state, dbg_wcnt, err_flags);

                /* 小抄：FSM 编码（见我们定义）
                   0:IDLE 1:INIT 2:R_SETUP 3:R_DATA 4:PARSE 5:CALC 6:V_READ 7:V_UPD
                   8:NEXT 9:OUT_PREF 10:OUT_ADDR 11:OUT_PACK 12:OUT_SETUP 13:OUT_WRITE
                   14:WAIT_BRESP 15:DONE 16:ERROR
                */
            }

            if (written >= VOTER_OUTPUT_BEATS) {
                xil_printf("\n\r[ERROR] Memory shows %u/%u beats written (100%%), but DONE=0.\n\r",
                           written, VOTER_OUTPUT_BEATS);
                xil_printf("[ERROR] Voter completion protocol violated; refusing stale/partial output.\n\r");
                voter_clear_start();
                poll_count = 0;
                poll_cnt = 0;
                pipeline_set_state(PIPE_FAIL);
                return PIPE_STEP_FAIL;
            } else {
                xil_printf("[POLL #%u] Progress: %u/%u beats written\n\r",
                           poll_cnt, written, VOTER_OUTPUT_BEATS);
            }
        }

        /* 条件1: DONE标志位置位 */
        if (status & VOTER_STATUS_DONE) {
            xil_printf("\n\r[STAGE2] ========================================\n\r");
            xil_printf("[STAGE2] ✓ DONE flag set after %u polls\n\r", poll_count);
            xil_printf("[STAGE2] ========================================\n\r");

            /* 清除START信号 */
            voter_clear_start();

            /* 重置轮询计数 */
            poll_count = 0;
            poll_cnt = 0;

            /* 进入完成状态 */
            pipeline_set_state(PIPE_DONE_STAGE2);
            return PIPE_STEP_PROGRESS;
        }

        /* 超时检查 */
        poll_count++;
        if (poll_count >= 100000) {  // 10万次轮询超时
            xil_printf("\n\r[ERROR] Voter timeout after %u polls\n\r", poll_count);
            xil_printf("[ERROR] Final status: 0x%02X\n\r", status);

            /* ✓ 新增：输出详细诊断信息 */
            xil_printf("[ERROR] Diagnostic information:\n\r");
            xil_printf("  - Voter may be stuck in processing\n\r");
            xil_printf("  - Check if START signal was captured\n\r");
            xil_printf("  - Verify input data format\n\r");

            /* 清除START信号并失败 */
            voter_clear_start();
            poll_count = 0;
            poll_cnt = 0;
            pipeline_set_state(PIPE_FAIL);
            return PIPE_STEP_FAIL;
        }

        return PIPE_STEP_PROGRESS;
    }
    /* ========================================================================
     * PIPE_DONE_STAGE2: Voter完成,验证输出并准备进入Stage3
     * ======================================================================== */
    case PIPE_DONE_STAGE2: {
        xil_printf("\n\r[STAGE2] ========================================\n\r");
        xil_printf("[STAGE2] ✓ Voter stage COMPLETE\n\r");
        xil_printf("[STAGE2] ========================================\n\r");
        /* PIPE_DONE_STAGE2 分支内： */
        u32 voter_out_addr = DDR_VOTER_OUT_BASE;

        // ✅ 硬件写完后，只需要 Invalidate，让CPU丢弃旧缓存行，从DDR重取真值
        xil_printf("[STAGE2] Making HW-written output visible to CPU (invalidate only)...\n\r");
        Xil_DCacheInvalidateRange(voter_out_addr, VOTER_OUTPUT_BYTES);   // [FIX] 改为仅 Invalidate
        __asm__ volatile("dsb sy");
        __asm__ volatile("isb");
        usleep(100);

        xil_printf("[STAGE2] Verifying output...\n\r");
        // 这里即可直接读/统计，不再需要前面的 Flush

        Xil_DCacheInvalidateRange(voter_out_addr, VOTER_OUTPUT_BYTES);
        __asm__ volatile("dsb sy");
        usleep(100);

        /* 验证输出数据 */
        xil_printf("[STAGE2] Verifying output data...\n\r");
        u64 *out_ptr = (u64*)voter_out_addr;
        u32 zero_count = 0, nonzero_count = 0;

        // ⭐ 扩大检查范围到前1000个u64
        u32 check_count = (1000 < VOTER_OUTPUT_BEATS) ? 1000 : VOTER_OUTPUT_BEATS;

        for (u32 i = 0; i < check_count; i++) {
            if (out_ptr[i] == 0) {
                zero_count++;
            } else {
                nonzero_count++;
            }
        }

        xil_printf("[STAGE2] Data statistics (first %u u64s):\n\r", check_count);
        xil_printf("  Zero count    : %u (%.1f%%)\n\r",
                   zero_count, (float)zero_count * 100.0f / check_count);
        xil_printf("  Non-zero count: %u (%.1f%%)\n\r",
                   nonzero_count, (float)nonzero_count * 100.0f / check_count);
        /* 警告：如果输出全为0 */
        if (nonzero_count == 0) {
            xil_printf("\n\r[WARNING] Voter output is all zeros!\n\r");
            xil_printf("[WARNING] This may indicate:\n\r");
            xil_printf("  1. Input data format mismatch between Stage1 and Voter\n\r");
            xil_printf("  2. Voter parsing logic error (codeword extraction)\n\r");
            xil_printf("  3. Voting algorithm produced all-zero result\n\r");
            xil_printf("  4. AXI write channel issue (writes not reaching DDR)\n\r");
            xil_printf("  5. BRAM initialization problem\n\r");
            xil_printf("[WARNING] Stage3 (Decoder) will likely fail or produce garbage.\n\r");
            xil_printf("[WARNING] Proceeding anyway for debugging...\n\r");
        } else {
            xil_printf("\n\r[STAGE2] ✓ Output contains valid data\n\r");
            xil_printf("[STAGE2] Non-zero ratio: %.1f%%\n\r",
                       (float)nonzero_count * 100.0f / check_count);
        }

        // ✅ 给 Stage3 使用时，保持“硬件写→CPU读”的一致性策略：仅 Invalidate 即可
        xil_printf("[STAGE2] Preparing output for Stage3 (invalidate only)...\n\r");
        Xil_DCacheInvalidateRange(voter_out_addr, VOTER_OUTPUT_BYTES);   // [FIX] 只 Invalidate
        __asm__ volatile("dsb sy");
        __asm__ volatile("isb");
        usleep(100);

        __asm__ volatile("dsb sy");
        __asm__ volatile("isb");
        usleep(2000);
        xil_printf("[STAGE2] ✓ Flush complete\n\r");

        /* 【修订 B3】Stage2 输出的是共识 DNA 序列，必须先与水印做差分
           才是 Stage3 期望的稀疏流。原来整条链路缺了这一级。 */
        if (apply_watermark_differential() != 0) {
            pipeline_set_state(PIPE_FAIL);
            return PIPE_STEP_FAIL;
        }

        xil_printf("\n\r[PIPELINE] Proceeding to Stage3 (Decoder)...\n\r");
        pipeline_set_state(PIPE_DECODER_PREP);
        return PIPE_STEP_PROGRESS;
    }

    default:
        xil_printf("[ERROR] Unknown state in pipeline_step_stage2: %d\n\r",
                   pipe_state);
        return PIPE_STEP_FAIL;
    }
}

/*==========================================================================
 * 水印差分：共识 DNA 序列 ⊕ 水印序列 → 稀疏流（Stage3 输入）
 *
 * 两侧都是「码流顺序 + 字节内 LSB-first」打包，因此逐字节异或即可。
 * 这里先用 PS 软件实现（10,125 B，一次几十微秒），把端到端链路打通；
 * 是否下沉到 Voter 里做，等链路验证通过后再决定。
 *==========================================================================*/
int apply_watermark_differential(void)
{
    volatile u8 *cons = (volatile u8 *)DDR_VOTER_OUT_BASE;
    const volatile u8 *wm = (const volatile u8 *)DDR_WATERMARK_BASE;
    u32 i;

    Xil_DCacheInvalidateRange(DDR_VOTER_OUT_BASE, VOTER_OUTPUT_BYTES);
    Xil_DCacheInvalidateRange(DDR_WATERMARK_BASE, WM_PACKED_BYTES);
    __asm__ volatile("dsb sy");

    for (i = 0; i < WM_PACKED_BYTES; i++) {
        cons[i] = (u8)(cons[i] ^ wm[i]);
    }
    /* 81,000 bit 不是 8 的整数倍余数为 0（10,125*8 = 81,000），无需处理尾部 */

    Xil_DCacheFlushRange(DDR_VOTER_OUT_BASE, VOTER_OUTPUT_BYTES);
    __asm__ volatile("dsb sy");
    __asm__ volatile("isb");
    xil_printf("[DIFF] Consensus XOR watermark done (%u bytes)\n\r",
               (u32)WM_PACKED_BYTES);
    return 0;
}
