#ifndef __DDR_LAYOUT_H__
#define __DDR_LAYOUT_H__
/******************************************************************************
 * ddr_layout.h — 按本次任务的实际记录数计算 DDR 区间并校验（C2/C3 的纯计算部分）
 *
 * 刻意不依赖任何 Xilinx 头文件，同一份代码既能编进 PS 固件，也能在主机上
 * 单元测试（tools/test_ddr_layout.c）。地址与容量都以参数传入，避免与
 * echo.h 的宏形成两份常量。
 *
 * 校验内容（docs/05-interfaces.md 的 DDR 布局）：
 *   - 记录数非零，且为 FRAME_READS(64) 的整数倍（C2：尾批整帧，补零由
 *     上位机完成，补零记录经 Voter 的 SCORE_MIN 过滤，不参与投票）；
 *   - 记录数不超过预留容量 TOTAL_READS；
 *   - 读段区 [reads_base, reads_limit) 与 Stage1 输出区 [stage1_base,
 *     stage1_limit) 都装得下本次任务的实际数据，不越过下一区的起点。
 *
 * 返回：0 = 合法；负数 = 错误码（见函数体）。
 ******************************************************************************/

static inline int ddr_layout_validate(unsigned long records,
                                       unsigned long frame_reads,
                                       unsigned long max_records,
                                       unsigned long reads_base,
                                       unsigned long reads_limit,
                                       unsigned long stage1_base,
                                       unsigned long stage1_limit,
                                       unsigned long bytes_per_read,
                                       unsigned long bytes_per_result)
{
    if (records == 0u)
        return -1;                       /* 空任务 */
    if ((records % frame_reads) != 0u)
        return -2;                       /* C2：非整帧尾批 */
    if (records > max_records)
        return -3;                       /* 超出 DDR 预留容量 */
    if (reads_base + records * bytes_per_read > reads_limit)
        return -4;                       /* 读段区越界 */
    if (stage1_base + records * bytes_per_result > stage1_limit)
        return -5;                       /* Stage1 输出区越界 */
    return 0;
}

/* 便捷接口：读段区 / Stage1 输出区的实际字节数（cache 操作范围用它，
 * 不要再用 TOTAL_READS 宏算——那是预留容量，不是本次任务的大小）。 */
static inline unsigned long ddr_layout_reads_bytes(unsigned long records,
                                                   unsigned long bytes_per_read)
{
    return records * bytes_per_read;
}

static inline unsigned long ddr_layout_stage1_bytes(unsigned long records,
                                                    unsigned long bytes_per_result)
{
    return records * bytes_per_result;
}

#endif /* __DDR_LAYOUT_H__ */
