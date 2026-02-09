/******************************************************************************
 * @file main.c
 * @brief DNA Accelerator Main - 完整三阶段流水线主程序
 ******************************************************************************/

#include <stdio.h>
#include "xparameters.h"
#include "netif/xadapter.h"
#include "platform.h"
#include "platform_config.h"
#include "xil_printf.h"
#include "xil_cache.h"

/* lwIP */
#include "lwip/init.h"
#include "lwip/tcp.h"
#include "lwip/dhcp.h"
#include "lwip/timeouts.h"

/* 应用层 */
#include "echo.h"
#include "sleep.h"

/* 若 BSP 未提供 sleep(),提供一个基于 usleep 的弱符号 */
void sleep(unsigned int seconds) __attribute__((weak));
void sleep(unsigned int seconds) {
    usleep(seconds * 1000000U);
}

/* 这两个 Flag 通常由 BSP 的定时器 ISR 置位 */
extern volatile int TcpFastTmrFlag;
extern volatile int TcpSlowTmrFlag;

/* 网络接口全局 */
static struct netif server_netif;
struct netif *echo_netif;

/* MAC 地址(按需修改) */
static unsigned char mac_ethernet_address[] = {0x00, 0x0a, 0x35, 0x00, 0x01, 0x02};
int force_decoder_to_idle(void) {
    xil_printf("\n\r[RESET] Forcing Decoder to IDLE state...\n\r");

    // 方法1：清零START并等待
    xil_printf("[RESET] Method 1: Clear START and wait...\n\r");
    write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
    usleep(100000);  // 100ms

    u32 status = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);
    xil_printf("[RESET] After Method 1: STATUS=0x%02X (IDLE=%d)\n\r",
               status, (status & 0x01) ? 1 : 0);

    if (status & 0x01) {
        xil_printf("[RESET] ✓ Method 1 succeeded\n\r");
        return 0;
    }

    // 方法2：发送最小任务快速完成
    xil_printf("[RESET] Method 2: Running minimal dummy task...\n\r");

    // 准备一个小的测试区域（使用Stage2的输出区域末尾）
    u32 dummy_in_addr  = 0x11002000;  // Stage2输出末尾
    u32 dummy_out_addr = 0x11003000;  // Stage2输出末尾+4K

    // 清空这些区域
    volatile u64 *p_in  = (volatile u64 *)dummy_in_addr;
    volatile u64 *p_out = (volatile u64 *)dummy_out_addr;
    for (int i = 0; i < 16; i++) {
        p_in[i] = 0xAAAAAAAAAAAAAAAAULL;  // 填充测试数据
        p_out[i] = 0;
    }
    Xil_DCacheFlushRange(dummy_in_addr, 128);
    Xil_DCacheFlushRange(dummy_out_addr, 128);

    // 配置最小任务（64位地址）
    write_reg32(DECODER_BASEADDR, DECODER_REG_IN_ADDR_H,  (u32)(((u64)dummy_in_addr) >> 32));
    write_reg32(DECODER_BASEADDR, DECODER_REG_IN_ADDR_L,  (u32)(dummy_in_addr & 0xFFFFFFFF));
    write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_ADDR_H, (u32)(((u64)dummy_out_addr) >> 32));
    write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_ADDR_L, (u32)(dummy_out_addr & 0xFFFFFFFF));
    usleep(1000);

    // 启动
    write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x01);
    usleep(50000);  // 等待50ms完成
    write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
    usleep(50000);  // 再等50ms

    status = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);
    xil_printf("[RESET] After Method 2: STATUS=0x%02X (IDLE=%d, DONE=%d)\n\r",
               status, (status & 0x01) ? 1 : 0, (status & 0x02) ? 1 : 0);

    if (status & 0x01) {
        xil_printf("[RESET] ✓ Method 2 succeeded\n\r");
        return 0;
    }

    // 方法3：多次尝试推进状态机
    xil_printf("[RESET] Method 3: Multiple dummy cycles...\n\r");
    for (int attempt = 0; attempt < 5; attempt++) {
        xil_printf("[RESET] Attempt %d/5...\n\r", attempt + 1);

        write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x01);
        usleep(20000);
        write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
        usleep(50000);

        status = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);
        if (status & 0x01) {
            xil_printf("[RESET] ✓ Method 3 succeeded on attempt %d\n\r", attempt + 1);
            return 0;
        }
    }

    xil_printf("[RESET] ❌ All methods failed\n\r");
    xil_printf("[RESET] Hardware requires:\n\r");
    xil_printf("  1. Power cycle the board, OR\n\r");
    xil_printf("  2. Reload bitstream, OR\n\r");
    xil_printf("  3. Toggle ARESETN via GPIO (if available)\n\r");
    return -1;
}
void reset_all_ip_cores(void) {
    xil_printf("\n\r========================================\n\r");
    xil_printf("[INIT] Enhanced IP Core Reset Sequence\n\r");
    xil_printf("========================================\n\r");

    // DNA Accelerator (IP1)
    xil_printf("[INIT] Resetting DNA Accelerator...\n\r");
    write_reg32(DNA_ACCELERATOR_BASEADDR, DNA_ACC_REG0_CTRL, 0x00);
    usleep(5000);

    // Voter (IP2)
    xil_printf("[INIT] Resetting Voter...\n\r");
    write_reg32(VOTER_BASEADDR, VOTER_REG_START, 0x00);
    write_reg32(VOTER_BASEADDR, VOTER_REG_IN_BEATS, 0);
    write_reg32(VOTER_BASEADDR, VOTER_REG_OUT_BEATS, 0);
    write_reg32(VOTER_BASEADDR, VOTER_REG_TOTAL_READS, 0);
    usleep(10000);

    // Decoder (IP3) - 使用增强复位
    xil_printf("[INIT] Resetting Decoder (enhanced)...\n\r");
    if (force_decoder_to_idle() != 0) {
        xil_printf("[INIT] ⚠️⚠️⚠️ DECODER RESET FAILED ⚠️⚠️⚠️\n\r");
        xil_printf("[INIT] System may not function correctly!\n\r");
        xil_printf("[INIT] Please power cycle the board.\n\r");
        // 不要直接退出，让用户决定
    } else {
        xil_printf("[INIT] ✓ Decoder reset successful\n\r");
    }

    // 最终验证
    u32 v_st = read_reg32(VOTER_BASEADDR, VOTER_REG_STATUS);
    u32 d_st = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);
    xil_printf("\n\r[INIT] Final Status:\n\r");
    xil_printf("  Voter   IDLE=%d, DONE=%d\n\r",
               (v_st & 0x01) ? 1 : 0, (v_st & 0x02) ? 1 : 0);
    xil_printf("  Decoder IDLE=%d, DONE=%d\n\r",
               (d_st & 0x01) ? 1 : 0, (d_st & 0x02) ? 1 : 0);

    if ((d_st & 0x01) == 0) {
        xil_printf("\n\r");
        xil_printf("========================================\n\r");
        xil_printf("⚠️  WARNING: Decoder not in IDLE state  ⚠️\n\r");
        xil_printf("========================================\n\r");
        xil_printf("Hardware reset is REQUIRED.\n\r");
        xil_printf("Options:\n\r");
        xil_printf("  1. Press board reset button\n\r");
        xil_printf("  2. Power cycle the board\n\r");
        xil_printf("  3. Reload bitstream in Vivado\n\r");
        xil_printf("========================================\n\r");
    } else {
        xil_printf("\n\r[INIT] ✓ All IP cores ready\n\r");
    }

    xil_printf("========================================\n\r");
}

static void print_app_header(void)
{
    xil_printf("====================================\n\r");
    xil_printf("DNA Accelerator Complete Pipeline\n\r");
    xil_printf("====================================\n\r");

}

static void print_ip(char *msg, ip_addr_t *ip)
{
    xil_printf("%s", msg);
    xil_printf("%d.%d.%d.%d\n\r", ip4_addr1(ip), ip4_addr2(ip),
               ip4_addr3(ip), ip4_addr4(ip));
}

static void print_ip_settings(ip_addr_t *ip, ip_addr_t *mask, ip_addr_t *gw)
{
    print_ip("Board IP: ", ip);

}

int main(void)
{
    ip_addr_t ipaddr, netmask, gw;

    echo_netif = &server_netif;

    init_platform();


    /* 静态 IP 配置(按需修改) */
    IP4_ADDR(&ipaddr,  192, 168, 1, 10);
    IP4_ADDR(&netmask, 255, 255, 255, 0);
    IP4_ADDR(&gw,      192, 168, 1, 1);

    print_app_header();

    lwip_init();
    reset_all_ip_cores();
    if (!xemac_add(echo_netif, &ipaddr, &netmask, &gw,
                   mac_ethernet_address, PLATFORM_EMAC_BASEADDR)) {
        xil_printf("ERROR: Error adding N/W interface\n\r");
        return -1;
    }

    netif_set_default(echo_netif);

    xil_printf("[INIT] Enabling interrupts...\n\r");
    platform_enable_interrupts();

    xil_printf("[INIT] Bringing up network interface...\n\r");
    netif_set_up(echo_netif);

    xil_printf("\n\r");
    print_ip_settings(&ipaddr, &netmask, &gw);
    xil_printf("\n\r");

    xil_printf("[INIT] Initializing DNA Accelerator...\n\r");
    if (dna_accelerator_init() != 0) {
        xil_printf("ERROR: DNA Accelerator initialization failed!\n\r");
        return -1;
    }
    xil_printf("[INIT] DNA Accelerator ready\n\r");

    if (start_application() != 0) {
        xil_printf("ERROR: Failed to start application\n\r");
        return -1;
   }

    xil_printf("\n\r*** Waiting for connections ***\n\r");

    /* 主循环:收包 + 推进流水 + 计时器 */
    u32 soft_ms   = 0;
    u32 fast_acc  = 0;
    u32 slow_acc  = 0;
    u32 heartbeat = 0;

    xil_printf("[INIT] System initialization complete\n\r");
    xil_printf("[INIT] Ready to accept connections\n\r");
    xil_printf("\n\r");
    for (;;) {
        /* 1) 喂 lwIP 输入(高频) */
        if (echo_netif) {
            xemacif_input(echo_netif);
        }

        /* 2) 处理 lwIP 计时器(硬件Flag优先) */
        if (TcpFastTmrFlag) { tcp_fasttmr(); TcpFastTmrFlag = 0; }
        if (TcpSlowTmrFlag) { tcp_slowtmr(); TcpSlowTmrFlag = 0; }

        /* 软件兜底:每 1ms 一次,确保没有ISR也能触发 lwIP 定时器 */
        usleep(1000);
        soft_ms++;
        fast_acc++;
        slow_acc++;

        if (fast_acc >= 250) { fast_acc = 0; tcp_fasttmr(); }
        if (slow_acc >= 500) { slow_acc = 0; tcp_slowtmr(); }

        /* 心跳:每 10s 打印一行,确认主循环在跑 */
        if (++heartbeat >= 10000) {
            heartbeat = 0;
            //xil_printf("[HB] Main loop alive (runtime: %lu s)\n\r", (unsigned long)(soft_ms/1000));
        }
    }

    /* 不会到达 */
    cleanup_platform();
    return 0;

}
