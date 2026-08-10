/******************************************************************************
 * @file echo.h
 * @brief DNA Accelerator Header - 三阶段流水线配置 (已优化，去除重打包)
 *
 * 修改说明:
 * 1. ✅ 去除DDR_STAGE1_REPACK缓冲区，Stage1输出直接被Stage2使用
 * 2. ✅ 重新分配DDR地址，避免地址冲突
 * 3. ✅ 删除repack_stage1_to_stage2()函数声明
 * 4. ✅ 优化地址映射，提高性能和可维护性
 ******************************************************************************/

#ifndef __ECHO_H__
#define __ECHO_H__

#include "xparameters.h"
#include "xil_types.h"
#include "lwip/err.h"
#include "lwip/tcp.h"
#include "xil_io.h"
#include "xil_cache.h"

/*=============================================================================
 * 协议定义
 *============================================================================*/
#define PROTOCOL_MAGIC          0xBEEF
#define PKT_WM                  0x01
#define PKT_BATCH               0x02
#define PKT_POST                0x03
#define PKT_RESULT              0x04
#define PKT_WM_OK               0x11
#define PKT_BATCH_OK            0x12
#define PKT_ERROR               0xEE
#define PROTOCOL_HDR_SIZE       8

/*=============================================================================
 * 数据尺寸参数
 *============================================================================*/
#define READ_SIZE_BYTES         40U
#define FRAME_READS             64U
#define FRAME_BYTES             (FRAME_READS * READ_SIZE_BYTES)   /* 2560B */
#define TOTAL_READS             108000U

/*=============================================================================
 * 水印几何（必须与 srpe_batch 的 parameter 一致）
 *
 *   REF_LEN = STRIDE + READ_BPS
 *   L(符号) = NUM_LC * STRIDE + READ_BPS = 50*807 + 150 = 40,500
 *   水印比特数 = 2 * L = 81,000
 *
 * 【修订 B1】MAX_WATERMARK_SIZE 原为 10120，小于 81,000 bit 所需的 10,125 B，
 * 而且 process_watermark() 还会静默截断，尾部 40 bit 直接丢掉。
 *============================================================================*/
#define WM_NUM_LC               50U
#define WM_STRIDE               807U
#define WM_REF_LEN              957U
#define WM_SYMBOLS              (WM_NUM_LC * WM_STRIDE + 150U)   /* 40,500 */
#define WM_TOTAL_BITS           (WM_SYMBOLS * 2U)                /* 81,000 */
#define WM_PACKED_BYTES         ((WM_TOTAL_BITS + 7U) / 8U)      /* 10,125 */
#define MAX_WATERMARK_SIZE      10240U                           /* 上位机按 8 对齐发 10,128 */

/* 展开后的区域缓冲：每个符号占一个 32-bit 字（低 2 位有效），
 * DNA 核预载时每拍只取 TDATA[1:0]，故必须一符号一拍地送。 */
#define WM_REGION_SYMBOLS       WM_REF_LEN
#define WM_REGION_BYTES         (WM_REGION_SYMBOLS * 4U)         /* 3,828 B */
#define WM_REGIONS_TOTAL_BYTES  (WM_NUM_LC * WM_REGION_BYTES)    /* 191,400 B */

/*=============================================================================
 * DDR 地址映射 (优化后，去除重打包)
 *
 * 内存布局:
 * 0x10000000 - 0x10002800  : 水印数据 (~10KB)
 * 0x10100000 - 0x105F4000  : 原始读段数据 (108000×40B = 4.32MB)
 * 0x10600000 - 0x10AEF000  : Stage1输出 (108000×48B = 5.184MB)
 *                             ↑ 直接被Stage2使用，无需重打包！
 * 0x11000000 - 0x11003000  : Stage2(Voter)输出 (1266×8B = 10.128KB)
 * 0x11100000 - 0x11102000  : Stage3(Decoder)输出 (1013×8B = 8.1KB)
 * 0x11800000 - 0x1181FFFF  : DMA TX BD空间 (2048×64B = 128KB)
 * 0x11900000 - 0x1190FFFF  : DMA RX BD空间 (1024×64B = 64KB)
 *============================================================================*/

/* 输入数据区 */
#define DDR_WATERMARK_BASE      0x10000000U    /* 上位机送来的打包水印（LSB-first） */
#define DDR_WM_REGIONS_BASE     0x10040000U    /* 展开后的 50 个区域，共 191,400 B（修订 B1） */
#define DDR_READS_BASE          0x10100000U    /* 原始读段数据 */

/* Stage1: DNA Accelerator */
#define DDR_DNA_ACC_OUT_BASE    0x10600000U    /* Stage1输出: 108000×48B */
#define DNA_ACC_RESULT_PACKED_BYTES  48U
#define DNA_ACC_OUTPUT_SIZE_BYTES    (TOTAL_READS * DNA_ACC_RESULT_PACKED_BYTES)

/* Stage2: Voter (直接使用Stage1输出，无需中间缓冲区) */
#define DDR_VOTER_IN_BASE       DDR_DNA_ACC_OUT_BASE  /* ✅ 直接使用Stage1输出 */
#define DDR_VOTER_OUT_BASE      0x11000000U    /* Stage2输出: 1266×8B = 10.128KB */

/* Stage3: Decoder */
#define DDR_DECODER_IN_BASE     DDR_VOTER_OUT_BASE    /* 使用Stage2输出 */
#define DDR_DECODER_OUT_BASE    0x11100000U    /* Stage3输出: 1013×8B = 8.1KB */

/* DMA BD描述符空间 */
#define BD_SPACE_BASE_TX        0x11800000U
#define BD_SPACE_SIZE_TX        (MAX_BD_COUNT_TX * 64)
#define BD_SPACE_BASE_RX        0x11900000U
#define BD_SPACE_SIZE_RX        (MAX_BD_COUNT_RX * 64)

/*=============================================================================
 * Stage1 输出数据格式
 *
 * 每个read: 48字节 = 6个u64 (最后一个u64仅使用低6位)
 * 位布局:
 *   bits [9:0]    = score (10位)     - 相关性得分
 *   bits [25:10]  = position (16位)  - 在标准水印中的匹配位置
 *   bits [325:26] = codeword (300位) - DNA读段的编码信息
 *   bits [383:326]= padding (58位)   - 补零对齐到48字节
 *============================================================================*/

/*=============================================================================
 * Stage2 输入/输出格式
 *
 * 输入: 直接使用Stage1的48字节输出
 *   - 每个read: 48字节 = 6个u64
 *   - 硬件配置: IN_BEATS = TOTAL_READS (硬件自动读取每read的6个u64)
 *
 * 输出: 投票结果
 *   - 81000 bits = 1266个u64 (每个u64包含64位投票数据)
 *============================================================================*/
#define VOTER_INPUT_BYTES_PER_READ   48U
#define VOTER_INPUT_TOTAL_BYTES      (TOTAL_READS * VOTER_INPUT_BYTES_PER_READ)
#define VOTER_INPUT_BEATS            TOTAL_READS  /* ✅ 硬件自动处理6个u64/read */

#define VOTER_OUTPUT_BITS       81000U
#define VOTER_OUTPUT_BYTES      10125U
#define VOTER_OUTPUT_BEATS      1266U   /* (81000+63)/64 = 1266拍 */

/*=============================================================================
 * Stage3 输入/输出格式
 *============================================================================*/
#define DECODER_INPUT_BITS      81000U
#define DECODER_INPUT_BYTES     10125U
#define DECODER_INPUT_BEATS     1266U
#define DECODER_OUTPUT_BITS     64800U
#define DECODER_OUTPUT_BYTES    8100U
#define DECODER_OUTPUT_BEATS    1013U

#define RESULT_SIZE_BYTES       DECODER_OUTPUT_BYTES

/*=============================================================================
 * IP核基地址与寄存器映射
 *============================================================================*/

/* ========= 第一个IP核: DNA Accelerator ========= */
#define DNA_ACCELERATOR_BASEADDR    XPAR_DNA_ACCELERATOR_CORE_0_S_AXI_LITE_CTRL_BASEADDR
#define DNA_ACC_REG0_CTRL           0x00U
#define DNA_ACC_CTRL_BIT_START      (1U << 0)
#define DNA_ACC_CTRL_BIT_PRELOAD    (1U << 1)
#define DNA_ACC_CTRL_BIT_SOFTRST    (1U << 2)
/* 【修订 B1】预载的区域号寄存器。原实现从未写过它，
 * 结果 50 个区域里只有第 0 个被写入，其余 49 个恒为全 0。 */
#define DNA_ACC_REG1_WMSEL          0x04U

/* ========= 第二个IP核: Voter (差分投票) =========
 *
 * 硬件寄存器映射 (基于axi_slave_voter模块):
 *   0x00: CTRL_STATUS - 写:bit[0]=start_pulse, bit[1]=done_clr
 *                       读:bit[0]=idle, bit[1]=done
 *   0x04: IN_ADDR     - 输入DDR地址
 *   0x08: IN_BEATS    - 输入数据拍数 (设置为TOTAL_READS)
 *   0x0C: OUT_ADDR    - 输出DDR地址
 *   0x10: OUT_BEATS   - 输出数据拍数 (1266)
 *   0x14: TOTAL_READS - 读段总数配置 (108000)
 *============================================================================*/
#define VOTER_BASEADDR              XPAR_DIFFERENTIAL_VOTER_0_S00_AXI_BASEADDR
#define VOTER_REG_CTRL_STATUS       0x00U  /* START/STATUS合一 */
#define VOTER_REG_IN_ADDR           0x04U  /* 输入地址 */
#define VOTER_REG_IN_BEATS          0x08U  /* 输入拍数 */
#define VOTER_REG_OUT_ADDR          0x0CU  /* 输出地址 */
#define VOTER_REG_OUT_BEATS         0x10U  /* 输出拍数 */
#define VOTER_REG_TOTAL_READS       0x14U  /* 总读段数 */

/* 为保持代码兼容性，保留旧名称别名 */
#define VOTER_REG_START             VOTER_REG_CTRL_STATUS
#define VOTER_REG_STATUS            VOTER_REG_CTRL_STATUS

/* 状态位掩码 */
#define VOTER_STATUS_IDLE           (1U << 0)
#define VOTER_STATUS_DONE           (1U << 1)

/* ========= 第三个IP核: Decoder (反稀疏化解码) =========
 *
 * 寄存器映射:
 *   0x00: IN_ADDR     - 输入DDR地址
 *   0x04: IN_BEATS    - 输入数据拍数 (1266)
 *   0x08: OUT_ADDR    - 输出DDR地址
 *   0x0C: OUT_BEATS   - 输出数据拍数 (1013)
 *   0x10: START       - 启动控制 (写1启动)
 *   0x18: STATUS      - 状态寄存器 (bit[0]=idle, bit[1]=done)
 *============================================================================*/
#define DECODER_BASEADDR            XPAR_DESPARSIFICATION_DEC_0_S00_AXI_BASEADDR
#define DECODER_REG_IN_ADDR         0x00U
#define DECODER_REG_IN_BEATS        0x04U
#define DECODER_REG_OUT_ADDR        0x08U
#define DECODER_REG_OUT_BEATS       0x0CU
#define DECODER_REG_START           0x10U
#define DECODER_REG_STATUS          0x18U   /* ⚠️ 注意: 状态寄存器在0x18 */

#define DECODER_STATUS_IDLE         (1U << 0)
#define DECODER_STATUS_DONE         (1U << 1)
#define DECODER_SENTINEL_U64        (0x0A55AA55AA55AA55ULL)

/*=============================================================================
 * DMA BD描述符配置
 *============================================================================*/
#define BD_ALIGNMENT            64U
#define MAX_BD_COUNT_TX         2048U
#define MAX_BD_COUNT_RX         1024U
#define DMA_ADDR_ALIGNMENT      8U
#define DMA_PER_BD_MAX          (16U * 1024U)

/*=============================================================================
 * 寄存器读写工具函数
 *============================================================================*/
static inline void write_reg32(u32 base, u32 off, u32 val) {
    Xil_Out32(base + off, val);
}

static inline u32 read_reg32(u32 base, u32 off) {
    return Xil_In32(base + off);
}

/*=============================================================================
 * 应用状态定义
 *============================================================================*/
typedef enum {
    STATE_IDLE = 0,
    STATE_PROCESSING
} app_state_t;

typedef struct {
    struct tcp_pcb *tpcb;
    app_state_t     state;
    u32             watermark_size;
    u32             total_reads_received;
} dna_connection_t;

/*=============================================================================
 * 函数声明
 *============================================================================*/

/* 主应用函数 */
int  start_application(void);
int  dna_accelerator_init(void);

/* 数据处理函数 */
void process_watermark(dna_connection_t *conn, u8 *data, u32 len);
/* 把打包水印展开成 NUM_LC 个区域写进 DDR（修订 B1） */
int  expand_watermark_regions(dna_connection_t *conn);
/* Stage2 共识 ⊕ 水印 → 稀疏流，供 Stage3 使用（修订 B3） */
int  apply_watermark_differential(void);
void process_batch(dna_connection_t *conn, u8 *data, u32 len);
void process_post(dna_connection_t *conn);
void send_result(dna_connection_t *conn);

/* 流水线控制 */
int  run_processing_pipeline(dna_connection_t *conn);

/* 网络回调 */
static err_t poll_callback(void *arg, struct tcp_pcb *tpcb);

/* 调试与分析函数 */
static void analyze_decoder_output(u32 out_addr, u32 total_beats);
static int validate_decoder_written_beats(u32 out_addr, u32 total_beats, u32 *written_beats);


#endif /* __ECHO_H__ */
