/******************************************************************************
 * stage3_decoder.c — PS 固件第三阶段流水线实现
 *
 * 包含 pipeline_step_stage3 与 validate_decoder_written_beats。
 ******************************************************************************/

#include "stage3_decoder.h"
#include "reg_timing.h"
#include "xil_printf.h"
#include "xil_cache.h"
#include "sleep.h"

int validate_decoder_written_beats(u32 out_addr, u32 total_beats, u32 *written_beats)
{
    Xil_DCacheInvalidateRange(out_addr, total_beats * 8);
    u64 *data = (u64*)out_addr;

    u32 sentinel_count = 0;   // 未写入(仍是哨兵值)
    u32 zero_count = 0;       // 已写入但为0
    u32 nonzero_count = 0;    // 已写入且非0

    for (u32 i = 0; i < total_beats; i++) {
        if (data[i] == DECODER_SENTINEL_U64) {
            sentinel_count++;
        } else if (data[i] == 0ULL) {
            zero_count++;
        } else {
            nonzero_count++;
        }
    }

    *written_beats = zero_count + nonzero_count;

    return 0;
}

/*============================================================================
 * 第三阶段(最终修复版本)
 * 核心规模统一：
 *   - 输入：81000 bit → 输入拍数 1266(最后一拍仅 40bit)
 *   - 输出：64800 字节 → 8100 拍(8B/拍)
 *============================================================================*/
#ifdef DECODER_INPUT_BEATS
#undef DECODER_INPUT_BEATS
#endif
#ifdef DECODER_OUTPUT_BEATS
#undef DECODER_OUTPUT_BEATS
#endif
#ifdef DECODER_OUTPUT_BYTES
#undef DECODER_OUTPUT_BYTES
#endif
#define DEC_IN_BITS              (81000u)
#define DECODER_INPUT_BEATS      ((DEC_IN_BITS + 63u)/64u)  /* =1266 */  /* =1266 */
#define DECODER_OUTPUT_BYTES     (8100u)
#define DECODER_OUTPUT_BEATS     ((DECODER_OUTPUT_BYTES + 7u)/8u)  /* =1013 */  /* =8100 */

pipe_step_rc_e pipeline_step_stage3(dna_connection_t *conn)
{
    const u32 DEC_IN_ADDR  = DDR_VOTER_OUT_BASE;
    const u32 DEC_OUT_ADDR = DDR_DECODER_OUT_BASE;
    const u32 DEC_IN_BEATS = 1266;   // 81000位 / 64
    const u32 DEC_OUT_BEATS = 1013;  // 8100字节 / 8

    switch (pipe_state) {

    case PIPE_DECODER_PREP: {
        xil_printf("\n\r========================================\n\r");
        xil_printf("[STAGE3] Decoder Preparation\n\r");
        xil_printf("========================================\n\r");

        // ✅ 关键修复：在做任何操作前先强制清零START和beats
        xil_printf("[STAGE3] Step 0: Ensuring START is cleared...\n\r");
        decoder_reset_regs();
        usleep(10000);  // 等待10ms

        u32 status_before_config = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);
        xil_printf("[STAGE3] Status before config: 0x%02X (IDLE=%d)\n\r",
                   status_before_config, (status_before_config & 0x01) ? 1 : 0);

        if (!(status_before_config & DECODER_STATUS_IDLE)) {
            xil_printf("[STAGE3] ❌ ERROR: Not IDLE before config!\n\r");
            pipeline_set_state(PIPE_FAIL);
            return PIPE_STEP_FAIL;
        }

        // ✅ Cache一致性修复
        xil_printf("[STAGE3] Invalidating input cache...\n\r");
        Xil_DCacheInvalidateRange(DEC_IN_ADDR, DEC_IN_BEATS * 8);
        __asm__ volatile("dsb sy");
        __asm__ volatile("isb");
        usleep(100);
        xil_printf("[STAGE3] ✓ Cache invalidated\n\r");

        /* 验证输入数据 */
        xil_printf("[STAGE3] Input Validation:\n\r");
        const u64 *in_data = (const u64*)DEC_IN_ADDR;
        u32 nonzero_count = 0, bit_ones = 0, bit_zeros = 0;

        for (u32 i = 0; i < DEC_IN_BEATS; i++) {
            u64 val = in_data[i];
            if (val != 0) {
                nonzero_count++;
                for (int b = 0; b < 64; b++) {
                    (val & (1ULL << b)) ? bit_ones++ : bit_zeros++;
                }
            } else {
                bit_zeros += 64;
            }
        }

        xil_printf("  Non-zero u64s: %u/%u (%%)\n\r", nonzero_count, DEC_IN_BEATS);
        xil_printf("  Bit ones:      %u (%%)\n\r", bit_ones);
        xil_printf("  Bit zeros:     %u (%%)\n\r", bit_zeros);

        if (nonzero_count == 0) {
            xil_printf("[STAGE3] ❌ ERROR: Input is all zeros!\n\r");
            pipeline_set_state(PIPE_FAIL);
            return PIPE_STEP_FAIL;
        }

        /* 清空输出区域 */
        xil_printf("[STAGE3] Clearing output area...\n\r");
        u64 *out64 = (u64*)DEC_OUT_ADDR;
        for (u32 i = 0; i < DEC_OUT_BEATS; i++) {
            out64[i] = DECODER_SENTINEL_U64;
        }
        Xil_DCacheFlushRange(DEC_OUT_ADDR, DEC_OUT_BEATS * 8);
        xil_printf("[STAGE3] Output area filled with sentinel values\n\r");

        // ✅ 关键修复：写配置前再次确认START=0
        xil_printf("[STAGE3] Writing configuration (with safety checks)...\n\r");
        decoder_confirm_idle_zero();

        // 按安全顺序写入：先写地址，最后才写beats
        decoder_configure_default();

        /* 回读验证 */
        u32 in_addr_rb  = read_reg32(DECODER_BASEADDR, DECODER_REG_IN_ADDR);
        u32 in_beats_rb = read_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS);
        u32 out_addr_rb = read_reg32(DECODER_BASEADDR, DECODER_REG_OUT_ADDR);
        u32 out_beats_rb= read_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS);

        xil_printf("[STAGE3] Configuration verification:\n\r");
        xil_printf("  IN_ADDR:  0x%08X %s\n\r", in_addr_rb,
                   (in_addr_rb == DEC_IN_ADDR) ? "✓" : "❌");
        xil_printf("  IN_BEATS: %u %s\n\r", in_beats_rb,
                   (in_beats_rb == DEC_IN_BEATS) ? "✓" : "❌");
        xil_printf("  OUT_ADDR: 0x%08X %s\n\r", out_addr_rb,
                   (out_addr_rb == DEC_OUT_ADDR) ? "✓" : "❌");
        xil_printf("  OUT_BEATS:%u %s\n\r", out_beats_rb,
                   (out_beats_rb == DEC_OUT_BEATS) ? "✓" : "❌");

        if (in_addr_rb != DEC_IN_ADDR || in_beats_rb != DEC_IN_BEATS ||
            out_addr_rb != DEC_OUT_ADDR || out_beats_rb != DEC_OUT_BEATS) {
            xil_printf("\n\r[ERROR] Configuration verification failed!\n\r");
            pipeline_set_state(PIPE_FAIL);
            return PIPE_STEP_FAIL;
        }

        // ✅ 关键检查：写完配置后验证是否意外启动
        usleep(5000);  // 等待5ms
        u32 status_after_config = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);
        xil_printf("[STAGE3] Status after config: 0x%02X (IDLE=%d, DONE=%d)\n\r",
                   status_after_config,
                   (status_after_config & 0x01) ? 1 : 0,
                   (status_after_config & 0x02) ? 1 : 0);

        if (!(status_after_config & DECODER_STATUS_IDLE)) {
            xil_printf("[STAGE3] ❌ ERROR: IP started unexpectedly during config!\n\r");
            xil_printf("[STAGE3] This indicates a hardware bug or signal glitch\n\r");

            // 尝试紧急停止
            write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
            write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, 0);
            write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, 0);
            usleep(50000);

            u32 recovery_status = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);
            if (recovery_status & DECODER_STATUS_IDLE) {
                xil_printf("[STAGE3] ✓ Recovered, retrying config...\n\r");
                // 重新开始PREP阶段
                return PIPE_STEP_PROGRESS;
            } else {
                xil_printf("[STAGE3] ❌ Cannot recover from unexpected start\n\r");
                pipeline_set_state(PIPE_FAIL);
                return PIPE_STEP_FAIL;
            }
        }

        xil_printf("========================================\n\r\n\r");

        /* 进入启动状态 */
        pipeline_set_state(PIPE_DECODER_START);
        return PIPE_STEP_PROGRESS;
    }
    /*========================================================================
     * PIPE_DECODER_START: 启动Decoder（保守、无“假任务推进”）
     *========================================================================*/
    case PIPE_DECODER_START: {
        xil_printf("========================================\n\r");
        xil_printf("[STAGE3] Starting Decoder...\n\r");

        u32 status = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);
        xil_printf("[STAGE3] Status before START: 0x%02X (IDLE=%d, DONE=%d)\n\r",
                   status, (status & 0x01) ? 1 : 0, (status & 0x02) ? 1 : 0);

        /* 【B27】START 只能写一次 1，前后都不许再写这个寄存器。
         * 原来的「写 0 → 写 1 → 100 us 后再写 0（脉冲结束）」是致命的：
         * decoder 的 AXI-Lite 把**对 0x10 的任何一次写**都当成 START 脉冲
         * （见 desparsification_decoder_v1_0.v 的 axi_slave_decoder），
         * 所以那句「脉冲结束」在任务跑到一半时把核重启了；而重启不会取消
         * 已经发出去的 AXI 读突发，残留的 R 拍被当成新任务输入流的开头，
         * 整条输入被旋转，Stage3 输出与黄金 49.46% 误码（第四次上板）。
         * RTL 已同时修好（只认 wdata[0]=1，且忙时不接受 START），
         * 这里也一并改成单次脉冲，两边都不再依赖对方。 */
        decoder_start_once();

        xil_printf("[STAGE3] ✓ IP core started (IDLE: 1→0)\n\r");
        xil_printf("[STAGE3] ✓ Started, monitoring progress...\n\r");

        pipeline_set_state(PIPE_DECODER_WAIT);
        return PIPE_STEP_PROGRESS;
    }
    /*========================================================================
     * PIPE_DECODER_WAIT: 等待完成
     *
     * ✓ 关键改进：使用两种方法监控进度
     * 1. 状态寄存器的DONE标志(可靠)
     * 2. 实际写入的beat数(区别0和最后写入)
     *========================================================================*/
    case PIPE_DECODER_WAIT: {
        /* 【B22】本状态由 poll_callback 驱动，实测约 280 ms 走一次
         * （有效间隔 250~500 ms，机理见 S1_NO_PROGRESS_LIMIT 处的说明）。
         * 原实现三处错误，合起来等于「永远等不到、也永远超不了时」：
         *   1) 注释声称用 STATUS 的 DONE 标志判完成，但循环里**从来没读过 STATUS**，
         *      只靠每 1000 次轮询一次的内存启发式 —— 最早也要 1000 x 500 ms = 500 s
         *      才做第一次判断，而上位机 recv_result 的静默上限是 180 s；
         *   2) 那个启发式拿 0 和 0xAAAA... 当「未写」，可 PREP 填的哨兵是
         *      DECODER_SENTINEL_U64 = 0x0A55AA55AA55AA55，压根不在比较之列，
         *      所以它其实分不出写没写；
         *   3) 超时阈值 500000 次轮询 ≈ 69 小时，等于没有超时。
         * 现在与 Stage2 的 PIPE_VOTER_WAIT 对齐：每次轮询都读 STATUS 看 DONE，
         * 内存进度只作旁证（且按真正的哨兵比较），并给一个够得着的超时。 */
        static u32 poll_count = 0;
        poll_count++;

        u32 status = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);

        /* 条件1（主判据）：DONE 标志置位 */
        if (status & DECODER_STATUS_DONE) {
            u32 cyc_tot  = read_reg32(DECODER_BASEADDR, DECODER_REG_CYCLES_TOTAL);
            u32 cyc_rd   = read_reg32(DECODER_BASEADDR, DECODER_REG_CYCLES_RD_BUSY);
            u32 cyc_wr   = read_reg32(DECODER_BASEADDR, DECODER_REG_CYCLES_WR_BUSY);
            u32 cyc_wait = read_reg32(DECODER_BASEADDR, DECODER_REG_CYCLES_RD_WAIT);
            xil_printf("[HW-CYCLES] Stage3 Decoder: total %u cyc (%u.%03u ms), rd_busy %u, wr_busy %u, rd_wait %u\n\r",
                       cyc_tot, cyc_tot / 100000U, (cyc_tot % 100000U) / 100U,
                       cyc_rd, cyc_wr, cyc_wait);
            xil_printf("\n\r[STAGE3] ✓ DONE flag set after %u polls\n\r", poll_count);
            decoder_clear_start();
            poll_count = 0;
            pipeline_set_state(PIPE_DONE_STAGE3);
            return PIPE_STEP_PROGRESS;
        }

        /* 条件2（旁证）：输出区哨兵是否已被全部覆盖。每 20 次轮询（~10 s）看一次 */
        if ((poll_count % 20u) == 0u) {
            Xil_DCacheInvalidateRange(DDR_DECODER_OUT_BASE, DECODER_OUTPUT_BEATS * 8);
            volatile const u64 *p_out = (volatile const u64 *)DDR_DECODER_OUT_BASE;
            u32 written = 0;
            for (u32 i = 0; i < DECODER_OUTPUT_BEATS; i++) {
                if (p_out[i] != DECODER_SENTINEL_U64) written++;
            }
            xil_printf("[STAGE3][POLL #%u] STATUS=0x%02X (IDLE=%u,DONE=%u) 已写 %u/%u 拍\n\r",
                       poll_count, status, (unsigned)(status & 0x1U),
                       (unsigned)((status >> 1) & 0x1U),
                       written, (u32)DECODER_OUTPUT_BEATS);

            if (written >= DECODER_OUTPUT_BEATS) {
                xil_printf("[STAGE3] ⚠️ 输出区 %u/%u 拍已全部写出，但 DONE=0；按完成收尾\n\r",
                           written, (u32)DECODER_OUTPUT_BEATS);
                decoder_clear_start();
                poll_count = 0;
                pipeline_set_state(PIPE_DONE_STAGE3);
                return PIPE_STEP_PROGRESS;
            }
        }

        /* 够得着的超时。原注释写「240 x 500 ms ≈ 120 s，仍在上位机 180 s 之内」，
         * 但每步实测 ~280 ms，**实际预算只有 ≈ 67 s**，乐观了约 2 倍。
         * 不是紧迫故障：Stage3 实测 < 500 ms 就 DONE（全量 103,616 条那轮也一样），
         * 离 67 s 差着两个数量级。同样只改注释不动数值（改了要重建 ELF）。
         * 记在这里是因为：下一个照「500 ms/步」去调这个常数的人一定会算错，
         * 而「拿注释当实现」正是 B22 当年翻车的同一类错误。 */
        if (poll_count > 240u) {
            /* 注意：这句打印的「~120 s」是照错的 500 ms/步算出来的，实际约 67 s。
             * 本轮**刻意不改这个字符串** —— 改了会让编译产物与
             * hw/build/export/ 里已验证的 ELF 不同源，就得整套重建 + 重新上板复验，
             * 而它只在一条从未触发过的失败路径上打印。下次因真实需求重建 ELF 时一并改掉。 */
            xil_printf("\n\r[ERROR] STAGE3 等待 ~120 s 仍未完成\n\r");
            xil_printf("  STATUS=0x%08X IN_ADDR=0x%08X IN_BEATS=%u OUT_ADDR=0x%08X OUT_BEATS=%u\n\r",
                       status,
                       read_reg32(DECODER_BASEADDR, DECODER_REG_IN_ADDR),
                       read_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS),
                       read_reg32(DECODER_BASEADDR, DECODER_REG_OUT_ADDR),
                       read_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS));
            poll_count = 0;
            pipeline_set_state(PIPE_FAIL);
            return PIPE_STEP_FAIL;
        }

        return PIPE_STEP_PROGRESS;
    }

    /*========================================================================
     * PIPE_DONE_STAGE3: 完成
     *========================================================================*/
    case PIPE_DONE_STAGE3: {
        xil_printf("\n\r[STAGE3] ========================================\n\r");
        xil_printf("[STAGE3] ✓ Decoder Stage COMPLETE\n\r");
        xil_printf("[STAGE3] ========================================\n\r");

        // 最终验证
        Xil_DCacheInvalidateRange(DEC_OUT_ADDR, DEC_OUT_BEATS * 8);

        u32 final_written = 0;
        validate_decoder_written_beats(DEC_OUT_ADDR, DEC_OUT_BEATS, &final_written);

        xil_printf("\n[STAGE3] Final Validation:\n\r");
        xil_printf("  Written beats: %u/%u (%.1f%%)\n\r",
                   final_written, DEC_OUT_BEATS,
                   (float)final_written * 100.0f / DEC_OUT_BEATS);

        if (final_written < DEC_OUT_BEATS / 2) {
            xil_printf("[STAGE3] ⚠️  WARNING: Less than 50%% written\n\r");
            xil_printf("[STAGE3] Results may be incomplete\n\r");
        }
        xil_printf("[CLEANUP] Resetting Decoder for next run...\n\r");
        write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
        write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, 0);
        write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, 0);
        usleep(50000);  // 等待50ms让状态机稳定

        u32 cleanup_status = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);
        xil_printf("[CLEANUP] Decoder STATUS: 0x%02X (IDLE=%d)\n\r",
                   cleanup_status, (cleanup_status & 0x01) ? 1 : 0);

        if (!(cleanup_status & 0x01)) {
            xil_printf("[CLEANUP] ⚠️ Not IDLE, forcing dummy run...\n\r");
            // 执行虚拟运行
            write_reg32(DECODER_BASEADDR, DECODER_REG_IN_ADDR,  DDR_VOTER_OUT_BASE);
            write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, 1);
            write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_ADDR, DDR_DECODER_OUT_BASE);
            write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, 1);
            usleep(1000);
            write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x01);
            usleep(5000);
            write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
            usleep(50000);
        }

        xil_printf("[CLEANUP] ✓ Decoder ready for next run\n\r");

        // 准备发送结果
        pipeline_set_state(PIPE_SEND_RESULT);
        return PIPE_STEP_PROGRESS;
    }
    default:
        return PIPE_STEP_PROGRESS;
    }
}
