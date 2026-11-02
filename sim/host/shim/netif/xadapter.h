#ifndef __XADAPTER_H__
#define __XADAPTER_H__
#include "lwip/tcp.h"
/* 主机侧壳层：喂 lwIP 的入口，记一次轨迹即可。 */
void xemacif_input(struct netif *netif);
#endif
