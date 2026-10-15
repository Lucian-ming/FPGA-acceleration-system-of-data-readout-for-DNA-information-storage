/******************************************************************************
 * proto.c — PS 固件网络协议层实现
 *
 * 实现 parse_header、send_framed_pkt、send_ack_byte、board_caps、
 * process_caps 以及 process_config。
 ******************************************************************************/

#include "proto.h"
#include "xil_printf.h"
#include "fw_diag.h"
#include "sleep.h"
#include <string.h>
#include "netif/xadapter.h"

#ifndef HOST_TEST
#include "netif/etharp.h"
#endif

extern struct netif *echo_netif;

/* 喂 lwIP */
void keep_tcp_alive(void)
{
    if (echo_netif) {
        xemacif_input(echo_netif);
    }
}

/* 【B29 根除加固】单播刷新对端 ARP，避免长任务结束时首包命中陈旧表项。 */
void arp_keepalive(const void *remote_ip)
{
#ifndef HOST_TEST
    if (echo_netif) {
        if (remote_ip) {
            etharp_request(echo_netif, (const ip4_addr_t *)remote_ip);
        }
        xemacif_input(echo_netif);
    }
#else
    (void)remote_ip;
#endif
}

/*============================================================================
 * TCP / 协议头解析
 *============================================================================*/
int parse_header(u8 *buf, u16 *magic, u8 *pkt_type, u32 *payload_len)
{
    *magic = (buf[0] << 8) | buf[1];
    *pkt_type = buf[2];
    *payload_len = (buf[4] << 24) | (buf[5] << 16) | (buf[6] << 8) | buf[7];
    if (*magic != PROTOCOL_MAGIC) return -1;
    return 0;
}

/*============================================================================
 * 【P3】任务配置化：PKT_CONFIG / PKT_CAPS（docs/04-interfaces.md 1.1~1.3）
 * 语义：严格拒绝（无降级）、强制 CONFIG（WM/BATCH/POST 前必须配置）、
 *       v1 只支持 SE150。校验逻辑在 sw/app/task_config.h（主机可测）。
 *============================================================================*/

/* 当前比特流的能力（如实反映综合参数） */
task_caps_t board_caps(void)
{
    task_caps_t c;
    memset(&c, 0, sizeof c);
    c.version     = 1;
    c.read_bps    = READ_BASES_PER_READ;
    c.num_lc      = WM_NUM_LC;
    c.stride      = WM_STRIDE;
    c.max_symbols = WM_SYMBOLS;
    c.max_reads   = TASK_MAX_READS;
    c.features    = 1u;              /* bit0：SCORE_MIN 寄存器可用 */
    return c;
}

/* 发送一个带 8B 包头的小包（CONFIG_OK / CAPS_INFO）。
 * 单次 tcp_write 保证“包头+负载”要么整体入队，要么整体失败。 */
err_t send_framed_pkt(struct tcp_pcb *tpcb, u8 type,
                      const u8 *payload, u32 len)
{
    u8 frame[PROTOCOL_HDR_SIZE + TASK_CAPS_INFO_LEN];
    if (tpcb == NULL || len > TASK_CAPS_INFO_LEN || (len != 0u && payload == NULL)) {
        return ERR_ARG;
    }

    frame[0] = (PROTOCOL_MAGIC >> 8) & 0xFF;
    frame[1] = PROTOCOL_MAGIC & 0xFF;
    frame[2] = type;
    frame[3] = 0;
    frame[4] = (len >> 24) & 0xFF; frame[5] = (len >> 16) & 0xFF;
    frame[6] = (len >> 8) & 0xFF;  frame[7] = len & 0xFF;
    if (len != 0u) memcpy(frame + PROTOCOL_HDR_SIZE, payload, len);

    for (int attempt = 0; attempt < 100; attempt++) {
        err_t e = tcp_write(tpcb, frame, PROTOCOL_HDR_SIZE + len,
                            TCP_WRITE_FLAG_COPY);
        if (e == ERR_OK) {
            tcp_output(tpcb);
            return ERR_OK;
        }
        if (e != ERR_MEM && e != ERR_WOULDBLOCK) return e;
        tcp_output(tpcb);
        keep_tcp_alive();
        usleep(1000);
    }
    xil_printf("[PKT] send_framed_pkt(%02X) giving up\n\r", type);
    return ERR_MEM;
}

/* 发送单字节 ACK */
err_t send_ack_byte(struct tcp_pcb *tpcb, u8 ack_type)
{
    u8 ack = ack_type;
    err_t e = tcp_write(tpcb, &ack, 1, TCP_WRITE_FLAG_COPY);
    if (e == ERR_OK) tcp_output(tpcb);
    return e;
}

void process_caps(dna_connection_t *conn)
{
    task_caps_t caps = board_caps();
    u8 payload[TASK_CAPS_INFO_LEN];
    task_caps_serialize(&caps, payload);
    xil_printf("[CAPS] version=%u read_bps=%u num_lc=%u stride=%u "
               "max_symbols=%u max_reads=%u features=%u\n\r",
               (u32)caps.version, (u32)caps.read_bps, caps.num_lc, caps.stride,
               caps.max_symbols, caps.max_reads, caps.features);
    if (conn->tpcb && send_framed_pkt(conn->tpcb, PKT_CAPS_INFO,
                                      payload, sizeof payload) != ERR_OK)
        xil_printf("[CAPS] ERROR: response enqueue failed\n\r");
}

void process_config(dna_connection_t *conn, u8 *data, u32 len)
{
    u8 ok[4];

    if (len != TASK_CONFIG_PAYLOAD_LEN) {
        xil_printf("[CONFIG] ERROR: payload %u != %u\n\r",
                   len, (u32)TASK_CONFIG_PAYLOAD_LEN);
        if (conn->tpcb) send_ack_byte(conn->tpcb, PKT_ERROR);
        return;
    }

    if (conn->configured) {                    /* 拒绝码 8：重复配置 */
        xil_printf("[CONFIG] rejected: already configured\n\r");
        wr_u32_be(ok, 8u);
        if (conn->tpcb && send_framed_pkt(conn->tpcb, PKT_CONFIG_OK,
                                          ok, sizeof ok) != ERR_OK)
            xil_printf("[CONFIG] ERROR: response enqueue failed\n\r");
        return;
    }
    if (conn->watermark_size != 0u || conn->total_reads_received != 0u) {
        wr_u32_be(ok, 9u);                      /* 拒绝码 9：顺序非法 */
        xil_printf("[CONFIG] rejected: data already received\n\r");
        if (conn->tpcb && send_framed_pkt(conn->tpcb, PKT_CONFIG_OK,
                                          ok, sizeof ok) != ERR_OK)
            xil_printf("[CONFIG] ERROR: response enqueue failed\n\r");
        return;
    }

    task_caps_t caps = board_caps();
    task_config_t cfg;
    int rc = task_config_parse(data, &caps, FRAME_READS,
                               DDR_READS_BASE, DDR_DNA_ACC_OUT_BASE,
                               DDR_DNA_ACC_OUT_BASE, DDR_VOTER_OUT_BASE,
                               READ_SIZE_BYTES, DNA_ACC_RESULT_PACKED_BYTES,
                               &cfg);
    if (rc != 0) {                              /* 严格拒绝：1..7 */
        static const char *why[] = {
            "", "version", "read_bps", "geometry", "symbols contract",
            "total_reads", "score_min", "CRC32"
        };
        xil_printf("[CONFIG] rejected (%d): %s\n\r", rc,
                   (rc >= 1 && rc <= 7) ? why[rc] : "?");
        wr_u32_be(ok, (u32)rc);
        if (conn->tpcb && send_framed_pkt(conn->tpcb, PKT_CONFIG_OK,
                                          ok, sizeof ok) != ERR_OK)
            xil_printf("[CONFIG] ERROR: response enqueue failed\n\r");
        return;
    }

    conn->cfg = cfg;
    conn->configured = 1;
    xil_printf("[CONFIG] accepted: v%u %ubp L=%u (%ux%u) reads=%u score_min=%u\n\r",
               (u32)cfg.version, (u32)cfg.read_bps, cfg.symbols,
               cfg.num_lc, cfg.stride, cfg.total_reads, cfg.score_min);
    wr_u32_be(ok, 0u);
    if (conn->tpcb && send_framed_pkt(conn->tpcb, PKT_CONFIG_OK,
                                      ok, sizeof ok) != ERR_OK)
        xil_printf("[CONFIG] ERROR: response enqueue failed\n\r");
}
