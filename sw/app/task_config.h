#ifndef __TASK_CONFIG_H__
#define __TASK_CONFIG_H__
/******************************************************************************
 * task_config.h — PKT_CONFIG 的解析与校验（P3 任务配置化的纯计算部分）
 *
 * 刻意不依赖任何 Xilinx 头文件（只用 <stdint.h>），同一份代码既能编进 PS
 * 固件，也能在主机上单元测试（tools/test_task_config.c）。协议定义见
 * docs/05-interfaces.md 第 1.1~1.3 节——改这里必须同步改文档。
 *
 * 语义（2026-08-16 三项决策）：
 *   - 严格拒绝：任一项不符即返回拒绝码，无降级/无默认值；
 *   - 强制 CONFIG：未配置前 WM/BATCH/POST 一律拒绝（顺序由连接层执行，
 *     对应错误码 8/9，不在本头文件里判）；
 *   - v1 只支持 SE150：read_bps 必须等于能力值。
 *
 * 拒绝码与文档 1.2 节一致：
 *   0=接受 1=版本 2=read_bps 3=几何不匹配 4=symbols 契约
 *   5=total_reads 6=score_min 7=CRC
 ******************************************************************************/

#include <stdint.h>

#include "ddr_layout.h"   /* 复用按实际条数的 DDR 区间校验（同为纯计算） */

#define TASK_CONFIG_PAYLOAD_LEN 44u
#define TASK_CAPS_INFO_LEN      24u
#define TASK_CFG_SCORE_MAX      1023u   /* 比对分是 10 bit */

typedef struct {
    uint8_t  version;      /* 协议版本 */
    uint8_t  read_bps;     /* 比特流支持的读段长度（当前 150） */
    uint16_t reserved;
    uint32_t num_lc;       /* 比特流综合参数（当前 50） */
    uint32_t stride;       /* 比特流综合参数（当前 807） */
    uint32_t max_symbols;  /* 当前几何的水印符号数（当前 40,500） */
    uint32_t max_reads;    /* 容量内最大 64 对齐条数（当前 107,968） */
    uint32_t features;     /* bit0: 支持 SCORE_MIN 寄存器 */
} task_caps_t;

typedef struct {
    uint8_t  version;
    uint8_t  read_bps;
    uint32_t num_lc;
    uint32_t stride;
    uint32_t symbols;      /* 水印符号数 L */
    uint32_t total_reads;  /* 声明的本任务条数（含补零尾批） */
    uint32_t score_min;
} task_config_t;

/* CRC-32/IEEE（zlib.crc32 兼容：反射、多项式 0xEDB88320、初值/终值 0xFFFFFFFF）。
 * 黄金判据："123456789" -> 0xCBF43926（见 test_task_config.c）。 */
static uint32_t crc32_ieee(const uint8_t *data, uint32_t len)
{
    static uint32_t table[256];
    static int table_ready = 0;
    uint32_t crc;

    if (!table_ready) {
        for (uint32_t i = 0; i < 256; i++) {
            uint32_t c = i;
            for (int k = 0; k < 8; k++)
                c = (c & 1u) ? (0xEDB88320u ^ (c >> 1)) : (c >> 1);
            table[i] = c;
        }
        table_ready = 1;
    }
    crc = 0xFFFFFFFFu;
    for (uint32_t i = 0; i < len; i++)
        crc = table[(crc ^ data[i]) & 0xFFu] ^ (crc >> 8);
    return crc ^ 0xFFFFFFFFu;
}

static uint32_t rd_u32_be(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

static void wr_u32_be(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);  p[3] = (uint8_t)v;
}

/* 解析并校验 PKT_CONFIG 的 44 B 负载。
 * 返回 0（接受，*out 已填充）或 1..7 拒绝码；8/9（连接层顺序错误）不在此判。
 * DDR 参数原样传给 ddr_layout_validate（见其注释）。 */
static int task_config_parse(const uint8_t *payload,
                             const task_caps_t *caps,
                             unsigned long frame_reads,
                             unsigned long reads_base, unsigned long reads_limit,
                             unsigned long stage1_base, unsigned long stage1_limit,
                             unsigned long bytes_per_read,
                             unsigned long bytes_per_result,
                             task_config_t *out)
{
    /* 1) CRC 优先：CRC 不对时其余字段不可信 */
    if (crc32_ieee(payload, TASK_CONFIG_PAYLOAD_LEN - 4u) != rd_u32_be(payload + 40))
        return 7;

    task_config_t c;
    c.version     = payload[0];
    c.read_bps    = payload[1];
    c.num_lc      = rd_u32_be(payload + 4);
    c.stride      = rd_u32_be(payload + 8);
    c.symbols     = rd_u32_be(payload + 12);
    c.total_reads = rd_u32_be(payload + 16);
    c.score_min   = rd_u32_be(payload + 20);

    /* 2) 版本与读段长度 */
    if (c.version != caps->version)
        return 1;
    if (c.read_bps != caps->read_bps)
        return 2;

    /* 3) 几何必须与比特流一致（v1：PL 参数是综合期常量） */
    if (c.num_lc != caps->num_lc || c.stride != caps->stride ||
        c.symbols != caps->max_symbols)
        return 3;

    /* 4) 水印契约：L = num_lc × stride + read_bps（docs/02-data-contract.md） */
    if (c.symbols != c.num_lc * c.stride + c.read_bps)
        return 4;

    /* 5) 条数：非零、整帧、容量、DDR 区间 */
    if (c.total_reads == 0u || c.total_reads % frame_reads != 0u ||
        c.total_reads > caps->max_reads)
        return 5;
    if (ddr_layout_validate(c.total_reads, frame_reads, caps->max_reads,
                            reads_base, reads_limit,
                            stage1_base, stage1_limit,
                            bytes_per_read, bytes_per_result) != 0)
        return 5;

    /* 6) 阈值范围（比对分 10 bit；0=不过滤） */
    if (c.score_min > TASK_CFG_SCORE_MAX)
        return 6;

    *out = c;
    return 0;
}

/* 把任务配置序列化成 44 B 负载（上位机语义参考/测试用；PS 固件不用）。 */
static void task_config_serialize(const task_config_t *c, uint8_t *payload)
{
    payload[0] = c->version;
    payload[1] = c->read_bps;
    payload[2] = 0; payload[3] = 0;
    wr_u32_be(payload + 4,  c->num_lc);
    wr_u32_be(payload + 8,  c->stride);
    wr_u32_be(payload + 12, c->symbols);
    wr_u32_be(payload + 16, c->total_reads);
    wr_u32_be(payload + 20, c->score_min);
    wr_u32_be(payload + 24, 0);
    wr_u32_be(payload + 28, 0);
    wr_u32_be(payload + 32, 0);
    wr_u32_be(payload + 36, 0);
    wr_u32_be(payload + 40, crc32_ieee(payload, 40));
}

/* 把能力描述序列化成 24 B 负载（CAPS_INFO）。 */
static void task_caps_serialize(const task_caps_t *caps, uint8_t *payload)
{
    payload[0] = caps->version;
    payload[1] = caps->read_bps;
    payload[2] = 0; payload[3] = 0;
    wr_u32_be(payload + 4,  caps->num_lc);
    wr_u32_be(payload + 8,  caps->stride);
    wr_u32_be(payload + 12, caps->max_symbols);
    wr_u32_be(payload + 16, caps->max_reads);
    wr_u32_be(payload + 20, caps->features);
}

#endif /* __TASK_CONFIG_H__ */
