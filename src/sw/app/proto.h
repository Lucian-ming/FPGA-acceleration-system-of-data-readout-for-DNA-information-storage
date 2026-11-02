/******************************************************************************
 * proto.h — PS 固件网络协议层 (Packet Framing & Protocol Dispatch)
 *
 * 封装 parse_header、send_framed_pkt、send_ack_byte、board_caps、
 * process_caps 以及 process_config。
 ******************************************************************************/
#ifndef __PROTO_H__
#define __PROTO_H__

#include "xil_types.h"
#include "lwip/err.h"
#include "lwip/tcp.h"
#include "echo.h"
#include "task_config.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 喂 lwIP 网络接口 */
void keep_tcp_alive(void);

/* 【B29 根除加固】刷新 ARP 与网络链路保活 */
void arp_keepalive(const void *remote_ip);

/* 解析 8B 协议头（BEEF magic + type + 4B 大端长度） */
int parse_header(u8 *buf, u16 *magic, u8 *pkt_type, u32 *payload_len);

/* 当前板端能力（如实反映综合参数） */
task_caps_t board_caps(void);

/* 发送带 8B 包头的小包（CONFIG_OK / CAPS_INFO） */
err_t send_framed_pkt(struct tcp_pcb *tpcb, u8 type,
                      const u8 *payload, u32 len);

/* 发送单字节 ACK */
err_t send_ack_byte(struct tcp_pcb *tpcb, u8 ack_type);

/* 处理 PKT_CAPS 请求 */
void process_caps(dna_connection_t *conn);

/* 处理 PKT_CONFIG 配置包 */
void process_config(dna_connection_t *conn, u8 *data, u32 len);

#ifdef __cplusplus
}
#endif

#endif /* __PROTO_H__ */
