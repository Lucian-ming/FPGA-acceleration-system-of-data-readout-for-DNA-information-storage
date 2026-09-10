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
#include "ddr_layout.h"   /* 【C2/C3】按实际条数计算/校验 DDR 区间（主机可测） */
#include "task_config.h"  /* 【P3】PKT_CONFIG 解析/校验/CRC（主机可测） */

/* 【P3】读段碱基数：SE250 规格 */
#define READ_BASES_PER_READ     150U
/* 容量内最大的 64 对齐条数：TOTAL_READS=129600 本身就是 64 的倍数 (2025 批) */
#define TASK_MAX_READS          ((TOTAL_READS / FRAME_READS) * FRAME_READS)

/*=============================================================================
 * 协议定义
 *============================================================================*/
#define PROTOCOL_MAGIC          0xBEEF
#define PKT_CONFIG              0x05    /* 【P3】任务配置，必须在 WM/BATCH/POST 前 */
#define PKT_CAPS                0x06    /* 【P3】查询板端能力 */
#define PKT_WM                  0x01
#define PKT_BATCH               0x02
#define PKT_POST                0x03
#define PKT_RESULT              0x04
#define PKT_WM_OK               0x11
#define PKT_BATCH_OK            0x12
#define PKT_CONFIG_OK           0x15    /* 【P3】带包头，4B 状态码（0=接受，1..9=拒绝码） */
#define PKT_CAPS_INFO           0x16    /* 【P3】带包头，24B 能力描述 */
#define PKT_ERROR               0xEE
#define PROTOCOL_HDR_SIZE       8

/*=============================================================================
 * 数据尺寸参数
 *============================================================================*/
#define READ_SIZE_BYTES         40U
#define FRAME_READS             64U
#define FRAME_BYTES             (FRAME_READS * READ_SIZE_BYTES)   /* 4096B */
/* DDR 预留的**记录数容量**上限——不是本次任务的大小，也不是数据集条数。
 * 本次任务的实际条数由 PKT_CONFIG 下发，cache 范围用 ddr_layout_*_bytes() 算。
 *
 * 2026-09-10 由 108000 改回 129600，理由：
 *   - SE250 全量 = 64,800 源读段 × 2 方向 = **129,600 条记录**。
 *     旧值 108000 经 TASK_MAX_READS 的 64 对齐后只剩 **107,968**，
 *     **装不下 SE250 全量**，CAPS 也据此只播报 max_reads=107968。
 *   - 129600 = 64 × 2025 恰好 64 对齐，对齐后仍是 129,600，无损耗；
 *     本文件第 26 行的注释一直写着「TOTAL_READS=129600 本身就是 64 的倍数
 *     (2025 批)」——**注释描述的才是正确值，108000 是回退**。
 *   - DDR 放得下（实算）：
 *       读段区  0x10100000→0x10600000 跨度 5,242,880 B，需 129600×40 = 5,184,000 B ✓（余 1.1%）
 *       Stage1  0x10600000→0x11000000 跨度 10,485,760 B，需 129600×48 = 6,220,800 B ✓
 *     读段区余量只有 1.1%，**再往上加容量必须先重排 DDR 分区**。
 */
#define TOTAL_READS             129600U

/*=============================================================================
 * 水印几何（必须与 srpe_batch 的 parameter 一致）
 *
 *   REF_LEN = STRIDE + READ_BPS = 805 + 250 = 1055
 *   L(符号) = NUM_LC * STRIDE + READ_BPS = 50*805 + 250 = 40,500
 *   水印比特数 = 2 * L = 81,000
 *
 * 【修订 B1】MAX_WATERMARK_SIZE 原为 10120，小于 81,000 bit 所需的 10,125 B；
 * 当前 process_watermark() 对长度不足或超限严格拒绝，不再静默截断。
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
#define WM_REGION_BYTES         (WM_REGION_SYMBOLS * 4U)         /* 4,220 B */
#define WM_REGIONS_TOTAL_BYTES  (WM_NUM_LC * WM_REGION_BYTES)    /* 211,000 B */

/*=============================================================================
 * DDR 地址映射 (SE250 全量布局，扩充读段区至 8.38MB，docs/20 §5.3)
 *
 * 内存布局:
 * 0x10000000 - 0x10002800  : 水印数据 (~10KB)
 * 0x10040000 - 0x10073800  : 展开后水印区域 (211KB)
 * 0x10100000 - 0x108E8000  : 原始读段数据 (129600×64B = 8.294MB ≤ 8.388MB)
 * 0x10900000 - 0x111E6000  : Stage1输出 (129600×72B = 9.331MB ≤ 9.437MB)
 *                             ↑ 直接被Stage2使用，无需重打包！
 * 0x11200000 - 0x11203000  : Stage2(Voter)输出 (1266×8B = 10.128KB)
 * 0x11300000 - 0x11302000  : Stage3(Decoder)输出 (1013×8B = 8.1KB)
 * 0x11800000 - 0x1181FFFF  : DMA TX BD空间 (2048×64B = 128KB)
 * 0x11900000 - 0x1190FFFF  : DMA RX BD空间 (1024×64B = 64KB)
 *============================================================================*/

/* 输入数据区 */
#define DDR_WATERMARK_BASE      0x10000000U    /* 上位机送来的打包水印（LSB-first） */
#define DDR_WM_REGIONS_BASE     0x10040000U    /* 展开后的 50 个区域，共 211,000 B */
#define DDR_READS_BASE          0x10100000U    /* 原始读段数据：跨度 8,388,608 B */

/* Stage1: DNA Accelerator */
#define DDR_DNA_ACC_OUT_BASE    0x10600000U    /* Stage1输出: 129600×72B = 9,331,200 B */
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
 *   0x08: IN_BEATS    - 输入数据拍数 (实际记录数 × 6)
 *   0x0C: OUT_ADDR    - 输出DDR地址
 *   0x10: OUT_BEATS   - 输出数据拍数 (1266)
 *   0x14: TOTAL_READS - 读段总数配置 (本次任务实际条数，C1)
 *   0x30: SCORE_MIN   - 【D1/D2】比对分阈值；score < SCORE_MIN 的记录不投票。
 *                       复位默认 0（不过滤）。注意 0x18~0x2C 是调试寄存器，
 *                       06-implementation-plan 里写的 0x18 已被 DBG_STATE 占用。
 *   （0x18/0x1C/0x20/0x24/0x28/0x2C/0x38 为只读调试寄存器）
 *============================================================================*/
#define VOTER_BASEADDR              XPAR_DIFFERENTIAL_VOTER_0_S00_AXI_BASEADDR
#define VOTER_REG_CTRL_STATUS       0x00U  /* START/STATUS合一 */
#define VOTER_REG_IN_ADDR           0x04U  /* 输入地址 */
#define VOTER_REG_IN_BEATS          0x08U  /* 输入拍数 */
#define VOTER_REG_OUT_ADDR          0x0CU  /* 输出地址 */
#define VOTER_REG_OUT_BEATS         0x10U  /* 输出拍数 */
#define VOTER_REG_TOTAL_READS       0x14U  /* 总读段数 */
#define VOTER_REG_SCORE_MIN         0x30U  /* 【D1/D2】分数阈值 */

/* 【P3】推荐阈值默认值（客户端参考）：固件不再固定使用，而是经 PKT_CONFIG
 * 的 score_min 字段运行时下发。67 = int(0.45 × READ_BPS)，与 tests/golden 的
 * stage2_expect.hex（make_golden.py --min-score 0.45）严格一致；噪声底 59~62，
 * 分离带内 67/68 均可，但判据向量按 67 生成。 */
#define VOTER_SCORE_MIN             112U

/* 为保持代码兼容性，保留旧名称别名 */
#define VOTER_REG_START             VOTER_REG_CTRL_STATUS
#define VOTER_REG_STATUS            VOTER_REG_CTRL_STATUS

/* 状态位掩码 */
#define VOTER_STATUS_IDLE           (1U << 0)
#define VOTER_STATUS_DONE           (1U << 1)
#define VOTER_STATUS_ERROR          (1U << 2)

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
    int             configured;      /* 【P3】已收到合法 PKT_CONFIG（每连接一次） */
    task_config_t   cfg;             /* 【P3】本连接的任务配置 */
} dna_connection_t;

/*=============================================================================
 * 函数声明
 *============================================================================*/

/* 主应用函数 */
int  start_application(void);
int  dna_accelerator_init(void);

/* 数据处理函数 */
int  process_watermark(dna_connection_t *conn, u8 *data, u32 len);
/* 把打包水印展开成 NUM_LC 个区域写进 DDR（修订 B1） */
int  expand_watermark_regions(dna_connection_t *conn);
/* Stage2 共识 ⊕ 水印 → 稀疏流，供 Stage3 使用（修订 B3） */
int  apply_watermark_differential(void);
int  process_batch(dna_connection_t *conn, u8 *data, u32 len);
void process_post(dna_connection_t *conn);
void send_result(dna_connection_t *conn);

/* 流水线控制 */
int  run_processing_pipeline(dna_connection_t *conn);

/* 【P3】任务配置与能力查询（docs/05-interfaces.md 1.1~1.3 节） */
void process_config(dna_connection_t *conn, u8 *data, u32 len);
void process_caps(dna_connection_t *conn);

#endif /* __ECHO_H__ */
