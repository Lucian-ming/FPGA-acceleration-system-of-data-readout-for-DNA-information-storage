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
/* tcp_fasttmr()/tcp_slowtmr() 在 lwIP 2.x 里声明在私有头里；
   不包含它会变成隐式声明（-Werror 下直接失败，且返回类型按 int 猜测）。 */
#include "lwip/priv/tcp_priv.h"

/* 应用层 */
#include "echo.h"
#include "sleep.h"
#include "dna_time.h"
#include "prof.h"

/* 流水线运行期主循环每圈的休眠（us），0 = 不休眠。可用 -DPIPE_RUN_SLEEP_US=N 覆盖做对照实验。 */
#ifndef PIPE_RUN_SLEEP_US
#define PIPE_RUN_SLEEP_US 200U
#endif

/* 注意：standalone BSP 的 sleep.h 已经声明并实现了 `void sleep(u32)`。
   这里原本还定义了一个 `void sleep(unsigned int)` 的弱符号兜底，
   与 BSP 原型冲突（u32 是 unsigned long），编译直接报
   "conflicting types for 'sleep'"。既然 BSP 一定提供，直接去掉。 */

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

    // 方法1：清零配置并等待超时
    xil_printf("[RESET] Method 1: Clear config and wait...\n\r");
    write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
    write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, 0);
    write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, 0);
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
    PROF_CACHE_FLUSH(dummy_in_addr, 128);
    PROF_CACHE_FLUSH(dummy_out_addr, 128);

    // 配置最小任务：8个输入beat，6个输出beat
    write_reg32(DECODER_BASEADDR, DECODER_REG_IN_ADDR,  dummy_in_addr);
    write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_ADDR, dummy_out_addr);
    write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, 8);
    write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, 6);
    usleep(1000);

    // 启动
    write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x01);
    usleep(50000);  // 等待50ms完成
    write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
    usleep(50000);  // 再等50ms

    status = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);
    xil_printf("[RESET] After Method 2: STATUS=0x%02X (IDLE=%d, DONE=%d)\n\r",
               status, (status & 0x01) ? 1 : 0, (status & 0x02) ? 1 : 0);

    // 清零配置
    write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, 0);
    write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, 0);
    usleep(50000);

    status = read_reg32(DECODER_BASEADDR, DECODER_REG_STATUS);
    if (status & 0x01) {
        xil_printf("[RESET] ✓ Method 2 succeeded\n\r");
        return 0;
    }

    // 方法3：多次尝试推进状态机
    xil_printf("[RESET] Method 3: Multiple dummy cycles...\n\r");
    for (int attempt = 0; attempt < 5; attempt++) {
        xil_printf("[RESET] Attempt %d/5...\n\r", attempt + 1);

        write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, 1);
        write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, 1);
        usleep(1000);

        write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x01);
        usleep(20000);
        write_reg32(DECODER_BASEADDR, DECODER_REG_START, 0x00);
        usleep(20000);

        write_reg32(DECODER_BASEADDR, DECODER_REG_IN_BEATS, 0);
        write_reg32(DECODER_BASEADDR, DECODER_REG_OUT_BEATS, 0);
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

/* ============================================================================
 * 启动顺序契约与 lwIP 初始化流程（docs/05 §C1）
 * ----------------------------------------------------------------------------
 * 1. init_platform()：使能 I/D-Cache，初始化中断控制器 SCUGIC 与私有定时器 SCUTIMER。
 * 2. lwip_init()：初始化协议栈内存池与数据结构。
 * 3. reset_all_ip_cores()：强制复位 PL 端三大加速核，特别针对 Stage3 Decoder 执行
 *    IDLE 状态恢复（force_decoder_to_idle），防止软重启或前次任务未完成导致状态机锁死。
 * 4. xemac_add(...)：向 lwIP 注册 Xilinx EmacPs 网络接口结构体。
 * 5. netif_set_default(echo_netif)：设置为默认路由接口。
 * 6. platform_enable_interrupts()：使能 GIC CPU 中断，必须在 xemac_add 之后、netif_set_up 之前完成。
 * 7. netif_set_up(echo_netif)：激活以太网链路（启动 PHY 自协商与 MAC 接收）。
 * 8. dna_accelerator_init()：初始化 Stage1 DMA 描述符环与各 IP 寄存器初始基地址。
 * 9. start_application()：绑定 TCP 端口 7，注册 accept 回调，进入就绪监听。
 * 10. for(;;) 主轮询循环：高频 xemacif_input 灌包，并由硬件 ISR + 软件计数器双重驱动定时器。
 * ============================================================================ */
int main(void)
{
    ip_addr_t ipaddr, netmask, gw;

    echo_netif = &server_netif;

    /* 步骤 1: 硬件平台与 Cache 初始化 */
    init_platform();


    /* 静态 IP 配置(按需修改) */
    IP4_ADDR(&ipaddr,  192, 168, 1, 10);
    IP4_ADDR(&netmask, 255, 255, 255, 0);
    IP4_ADDR(&gw,      192, 168, 1, 1);

    print_app_header();

    /* 步骤 2: lwIP 协议栈全局初始化 */
    lwip_init();

    /* 步骤 3: PL 端 IP 核复位（防止飞行数据与状态锁死） */
    reset_all_ip_cores();

    /* 步骤 4: 添加 EmacPs 接口 */
    if (!xemac_add(echo_netif, &ipaddr, &netmask, &gw,
                   mac_ethernet_address, PLATFORM_EMAC_BASEADDR)) {
        xil_printf("ERROR: Error adding N/W interface\n\r");
        return -1;
    }

    netif_set_default(echo_netif);

    /* 步骤 6: 使能中断控制器与 CPU 全局中断（必须在 netif_set_up 前就绪） */
    xil_printf("[INIT] Enabling interrupts...\n\r");
    platform_enable_interrupts();

    /* 步骤 7: 激活网络链路 */
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

    /* 主循环: 收包 + 事件驱动流水线推进 + 精确硬件计时器 */
    XTime t_last_fast = 0, t_last_slow = 0;
    XTime_GetTime(&t_last_fast);
    t_last_slow = t_last_fast;
    const XTime fast_interval = (XTime)(COUNTS_PER_SECOND / 4U); /* 250ms */
    const XTime slow_interval = (XTime)(COUNTS_PER_SECOND / 2U); /* 500ms */

    xil_printf("[INIT] System initialization complete\n\r");
    xil_printf("[INIT] Ready to accept connections (event-driven pipeline active)\n\r");
    xil_printf("\n\r");
    for (;;) {
        /* 1) 喂 lwIP 输入(高频) */
        if (echo_netif) {
            PROF_NETIN_BEGIN(netin);
            xemacif_input(echo_netif);
            PROF_NETIN_END(netin);
        }

        /* 2) 处理 lwIP 计时器(硬件Flag优先) */
        if (TcpFastTmrFlag) { tcp_fasttmr(); TcpFastTmrFlag = 0; }
        if (TcpSlowTmrFlag) { tcp_slowtmr(); TcpSlowTmrFlag = 0; }

        /* 软件兜底: 按 XTime 硬件计数器精确触发 lwIP 定时器 */
        XTime t_now;
        XTime_GetTime(&t_now);
        if (t_now - t_last_fast >= fast_interval) {
            t_last_fast = t_now;
            tcp_fasttmr();
        }
        if (t_now - t_last_slow >= slow_interval) {
            t_last_slow = t_now;
            tcp_slowtmr();
        }

        /* 3) 主动推进流水线 (P12-B 事件驱动，消除 poll 白等) */
        echo_pipeline_poll();

        /* 4) 节流休眠: 空闲时休眠 1ms 降低 CPU 功耗；运行中按 PIPE_RUN_SLEEP_US 微延
         *    （0 = 不休眠）。2026-09-22 板测：运行期 [waiting] ≈ 主循环次数 × 200 us，
         *    每条记录的斜率由这一行决定，见 docs/03 P13。 */
        if (echo_pipeline_is_running()) {
            if (PIPE_RUN_SLEEP_US > 0U) {
                usleep(PIPE_RUN_SLEEP_US);
            }
        } else {
            usleep(1000);
        }
    }

    /* 不会到达 */
    cleanup_platform();
    return 0;

}
