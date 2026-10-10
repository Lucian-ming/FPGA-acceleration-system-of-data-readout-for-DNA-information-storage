/* =============================================================
 * test_task_config.c — task_config.h 的主机单元测试（P3 判据）
 *
 * 与固件共用 sw/app/task_config.h。协议黄金值来自 docs/04-interfaces.md：
 *   CRC-32/IEEE 与 zlib.crc32 一致（独立交叉验证）：
 *     "123456789" -> 0xCBF43926
 *     黄金 config(v1/150/50/807/40500/4096/67) 前 40 B -> 0xD5BC6633
 *   合法配置接受；逐项破坏得到拒绝码 1..7。
 *
 *   gcc -O2 -Wall -I sw/app -o /tmp/test_tcfg tools/test_task_config.c && /tmp/test_tcfg
 * ============================================================= */
#include <stdio.h>
#include <string.h>
#include "task_config.h"

/* 与 echo.h / docs/04-interfaces.md 1.3 节一致的黄金能力值 */
#define CAPS_V      1
#define CAPS_BPS    150
#define CAPS_NUMLC  50
#define CAPS_STRIDE 807
#define CAPS_SYMS   40500
#define CAPS_MAXRD  107968
#define READS_BASE   0x10100000UL
#define READS_LIMIT  0x10600000UL
#define STAGE1_BASE  0x10600000UL
#define STAGE1_LIMIT 0x11000000UL
#define B_PER_READ   40UL
#define B_PER_RESULT 48UL

static task_caps_t golden_caps(void)
{
    task_caps_t c;
    memset(&c, 0, sizeof c);
    c.version = CAPS_V; c.read_bps = CAPS_BPS;
    c.num_lc = CAPS_NUMLC; c.stride = CAPS_STRIDE;
    c.max_symbols = CAPS_SYMS; c.max_reads = CAPS_MAXRD;
    c.features = 1u;
    return c;
}

static void build_payload(uint8_t *p, uint8_t ver, uint8_t bps, uint32_t lc,
                          uint32_t stride, uint32_t syms, uint32_t reads,
                          uint32_t smin)
{
    memset(p, 0, TASK_CONFIG_PAYLOAD_LEN);
    p[0] = ver; p[1] = bps;
    wr_u32_be(p + 4, lc);
    wr_u32_be(p + 8, stride);
    wr_u32_be(p + 12, syms);
    wr_u32_be(p + 16, reads);
    wr_u32_be(p + 20, smin);
    wr_u32_be(p + 40, crc32_ieee(p, 40));
}

static int check(const char *name, uint8_t *p, int expect_rc,
                 task_caps_t *caps, task_config_t *out)
{
    int rc = task_config_parse(p, caps, 64,
                               READS_BASE, READS_LIMIT, STAGE1_BASE, STAGE1_LIMIT,
                               B_PER_READ, B_PER_RESULT, out);
    int ok = (rc == expect_rc);
    printf("  %-28s rc=%-2d 期望=%-2d  %s\n", name, rc, expect_rc, ok ? "✓" : "✗");
    return !ok;
}

int main(void)
{
    int fail = 0;
    task_caps_t caps = golden_caps();
    task_config_t cfg;
    uint8_t p[TASK_CONFIG_PAYLOAD_LEN];

    printf("== CRC-32/IEEE 独立黄金向量 ==\n");
    uint32_t c1 = crc32_ieee((const uint8_t *)"123456789", 9);
    printf("  \"123456789\" -> 0x%08X（期望 0xCBF43926） %s\n",
           c1, c1 == 0xCBF43926u ? "✓" : "✗");
    if (c1 != 0xCBF43926u) fail++;

    /* 与 Python zlib.crc32 交叉验证的黄金 config */
    build_payload(p, 1, 150, 50, 807, 40500, 4096, 67);
    uint32_t c2 = rd_u32_be(p + 40);
    printf("  黄金config前40B -> 0x%08X（期望 0xD5BC6633） %s\n",
           c2, c2 == 0xD5BC6633u ? "✓" : "✗");
    if (c2 != 0xD5BC6633u) fail++;

    printf("== 合法配置接受 + 字段回读 ==\n");
    fail += check("黄金config(4096条/67)", p, 0, &caps, &cfg);
    if (cfg.version != 1 || cfg.read_bps != 150 || cfg.num_lc != 50 ||
        cfg.stride != 807 || cfg.symbols != 40500 ||
        cfg.total_reads != 4096 || cfg.score_min != 67) {
        printf("  ✗ 字段回读不符\n"); fail++;
    } else {
        printf("  字段回读 7/7 ✓\n");
    }
    /* 序列化-解析往返 */
    uint8_t q[TASK_CONFIG_PAYLOAD_LEN];
    task_config_serialize(&cfg, q);
    fail += check("serialize→parse 往返", q, 0, &caps, &cfg);

    /* 全量任务 103,616 条 + 阈值 0（不过滤） */
    build_payload(p, 1, 150, 50, 807, 40500, 103616, 0);
    fail += check("全量103616条/score=0", p, 0, &caps, &cfg);

    printf("== 逐项拒绝（严格模式） ==\n");
    build_payload(p, 2, 150, 50, 807, 40500, 4096, 67);
    fail += check("版本=2", p, 1, &caps, &cfg);
    build_payload(p, 1, 250, 50, 807, 68250, 4096, 67);
    fail += check("read_bps=250(SE250)", p, 2, &caps, &cfg);
    build_payload(p, 1, 150, 49, 807, 40500, 4096, 67);
    fail += check("num_lc=49", p, 3, &caps, &cfg);
    build_payload(p, 1, 150, 50, 808, 40500, 4096, 67);
    fail += check("stride=808", p, 3, &caps, &cfg);
    build_payload(p, 1, 150, 50, 807, 40499, 4096, 67);
    fail += check("symbols=40499", p, 3, &caps, &cfg);
    /* 契约破坏：几何与 caps 一致时 symbols 已被码 3 拦住；单独构造
     * caps 允许范围内的契约违规（v1 几何固定，仅在未来放开时可达）。 */
    build_payload(p, 1, 150, 50, 807, 40501, 4096, 67);
    fail += check("symbols=40501", p, 3, &caps, &cfg);
    build_payload(p, 1, 150, 50, 807, 40500, 100, 67);
    fail += check("条数100(非64倍)", p, 5, &caps, &cfg);
    build_payload(p, 1, 150, 50, 807, 40500, 0, 67);
    fail += check("条数0", p, 5, &caps, &cfg);
    build_payload(p, 1, 150, 50, 807, 40500, 108032, 67);
    fail += check("条数108032(超容)", p, 5, &caps, &cfg);
    build_payload(p, 1, 150, 50, 807, 40500, 4096, 1024);
    fail += check("score_min=1024", p, 6, &caps, &cfg);
    build_payload(p, 1, 150, 50, 807, 40500, 4096, 67);
    p[10] ^= 0x01;                     /* 破坏 stride 中间一个 bit，CRC 失效 */
    fail += check("CRC 破坏", p, 7, &caps, &cfg);

    printf("== CAPS_INFO 序列化 ==\n");
    uint8_t ci[TASK_CAPS_INFO_LEN];
    task_caps_serialize(&caps, ci);
    int ci_ok = ci[0] == 1 && ci[1] == 150 &&
                rd_u32_be(ci + 4) == 50 && rd_u32_be(ci + 8) == 807 &&
                rd_u32_be(ci + 12) == 40500 && rd_u32_be(ci + 16) == 107968 &&
                rd_u32_be(ci + 20) == 1;
    printf("  24B 能力包字段 7/7 %s\n", ci_ok ? "✓" : "✗");
    if (!ci_ok) fail++;

    printf("--------------------------------------------------\n");
    if (fail == 0)
        printf("✓ PASS  task_config 全部判据通过\n");
    else
        printf("✗ FAIL  %d 项不符\n", fail);
    return fail ? 1 : 0;
}
