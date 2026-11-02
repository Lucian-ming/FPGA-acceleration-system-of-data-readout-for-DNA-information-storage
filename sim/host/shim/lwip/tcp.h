#ifndef __LWIP_TCP_H__
#define __LWIP_TCP_H__
/* 主机侧壳层：只提供 sw/app/echo.c 用到的那部分 lwIP 接口。
 * 语义按真实 lwIP 取**保守**近似：tcp_write 拷贝进发送队列并可返回 ERR_MEM，
 * tcp_sndbuf 有上限 —— send_result() 的重试路径因此是真的被走到的。 */
#include "lwip/err.h"
#include "xil_types.h"

struct netif { int dummy; };
struct pbuf {
    struct pbuf *next;
    void  *payload;
    u16    tot_len;
    u16    len;
};

struct tcp_pcb;
struct tcp_seg;
typedef err_t (*tcp_recv_fn)(void *arg, struct tcp_pcb *tpcb, struct pbuf *p, err_t err);
typedef err_t (*tcp_poll_fn)(void *arg, struct tcp_pcb *tpcb);
typedef err_t (*tcp_accept_fn)(void *arg, struct tcp_pcb *newpcb, err_t err);

struct tcp_pcb {
    void          *cb_arg;
    tcp_recv_fn    recv_cb;
    tcp_poll_fn    poll_cb;
    tcp_accept_fn  accept_cb;
    u32            so_options;
    u32            keep_idle;
    int            closed;
    int            aborted;
    int            nagle_off;
    u16            sndbuf;      /* 剩余发送窗口，tcp_output 后恢复 */
    u32            remote_ip;  /* 主机模型只需提供可取地址 */
    struct tcp_seg *unsent;
    struct tcp_seg *unacked;
};

#define SOF_KEEPALIVE        0x08U
#define TCP_WRITE_FLAG_COPY  0x01
#define IP_ADDR_ANY          ((void *)0)

struct tcp_pcb *tcp_new(void);
err_t  tcp_bind(struct tcp_pcb *pcb, void *ipaddr, u16 port);
struct tcp_pcb *tcp_listen(struct tcp_pcb *pcb);
void   tcp_accept(struct tcp_pcb *pcb, tcp_accept_fn accept);
void   tcp_arg(struct tcp_pcb *pcb, void *arg);
void   tcp_recv(struct tcp_pcb *pcb, tcp_recv_fn recv);
void   tcp_poll(struct tcp_pcb *pcb, tcp_poll_fn poll, u8 interval);
err_t  tcp_close(struct tcp_pcb *pcb);
void   tcp_abort(struct tcp_pcb *pcb);
void   tcp_nagle_disable(struct tcp_pcb *pcb);
err_t  tcp_write(struct tcp_pcb *pcb, const void *data, u16 len, u8 apiflags);
err_t  tcp_output(struct tcp_pcb *pcb);
void   tcp_recved(struct tcp_pcb *pcb, u16 len);
u16    tcp_sndbuf(struct tcp_pcb *pcb);

u16    pbuf_copy_partial(const struct pbuf *p, void *dataptr, u16 len, u16 offset);
void   pbuf_free(struct pbuf *p);

#endif
