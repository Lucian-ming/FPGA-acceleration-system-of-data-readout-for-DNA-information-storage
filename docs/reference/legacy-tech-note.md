> **⚠️ 已过时**：本文是历史技术说明。其中的 IP 寄存器表是「示例模板」，与实际实现不符，
> 已被 `docs/archive/history/2026/pre-bkb220-handoff-2026-10-10/interfaces.md` 取代；架构描述以 `docs/archive/history/2026/pre-bkb220-handoff-2026-10-10/architecture.md` 为准。保留仅作历史参考。

# 📘 Vitis DNA Accelerator — 技术文档

## 一、系统概览

```
PS (lwIP) ⇄ DMA ⇄ DNA Accelerator ⇄ Differential Voter ⇄ Desparsification Decoder ⇄ DMA ⇄ PS
```

三阶段硬件流水线实现高速 DNA 数据解码处理。

---

## 二、硬件结构

| 模块                     | 接口                                          | 功能           |
| ------------------------ | --------------------------------------------- | -------------- |
| DNA Accelerator          | S_AXI_LITE_CTRL / S_AXIS_DATA / M_AXIS_RESULT | 数据预处理     |
| Differential Voter       | S00_AXI / M00_AXI                             | 加权表决       |
| Desparsification Decoder | S00_AXI / M00_AXI                             | 稀疏数据解码   |
| AXI DMA                  | MM2S / S2MM / SG                              | 高速传输       |
| PS7                      | GP0 / HP0                                     | 控制与内存接口 |

---

## 三、软件结构

-   `main.c`：初始化 lwIP、DMA 与调度逻辑
-   `echo.c / echo.h`：TCP Echo 服务
-   `xparameters.h`：寄存器映射定义
-   `lscript.ld`：链接脚本
-   `create_vitis.tcl`：一键构建脚本

---

## 四、通信协议

| 字段   | 字节 | 描述            |
| ------ | ---- | --------------- |
| Header | 2    | 固定标识 0xBEEF |
| Type   | 1    | 包类型          |
| Length | 4    | 数据长度        |
| CRC32  | 4    | 校验            |

---

## 五、生成与调试

```bash
vivado -mode batch -source hw/scripts/build.tcl
xsct sw/scripts/create_vitis.tcl
```

---

## 六、接口时序与寄存器（三个 IP 核）

### 6.1 DNA Accelerator Core（AXIS + AXI‑Lite）

**AXIS 输入（S_AXIS_DATA）**
| 信号 | 方向 | 说明 |
|------|------|------|
| `S_AXIS_DATA_TDATA[31:0]` | I | 输入数据 |
| `S_AXIS_DATA_TVALID` | I | 数据有效 |
| `S_AXIS_DATA_TREADY` | O | 接收就绪 |
| `S_AXIS_DATA_TLAST` | I | 帧结束 |

**AXIS 输出（M_AXIS_RESULT）**
| 信号 | 方向 | 说明 |
|------|------|------|
| `M_AXIS_RESULT_TDATA[31:0]` | O | 输出数据 |
| `M_AXIS_RESULT_TVALID` | O | 数据有效 |
| `M_AXIS_RESULT_TREADY` | I | 下游就绪 |
| `M_AXIS_RESULT_TLAST` | O | 帧结束 |

**AXI‑Lite 控制（S_AXI_LITE_CTRL，示例寄存器）**
| 偏移 | 名称 | 位段 | 说明 |
|------|------|------|------|
| 0x00 | CTRL | [0]=START | 上升沿启动一次处理 |
| 0x04 | STATUS| [0]=IDLE, [1]=DONE, [2]=ERR | 状态位 |
| 0x08 | CFG_IN_ADDR_LO | 31:0 | 输入物理地址低 32 位 |
| 0x0C | CFG_IN_ADDR_HI | 31:0 | 输入物理地址高 32 位（如需） |
| 0x10 | CFG_OUT_ADDR_LO | 31:0 | 输出地址低 32 位 |
| 0x14 | CFG_OUT_ADDR_HI | 31:0 | 输出地址高 32 位 |
| 0x18 | CFG_LEN | 31:0 | 处理字节数 |

> 具体寄存器以实际 RTL 为准，上表为常见布局建议。

---

### 6.2 Differential Voter Core（AXI‑Lite + AXI Master）

**AXI‑Lite 控制（S00_AXI，示例寄存器）**
| 偏移 | 名称 | 位段 | 说明 |
|------|------|------|------|
| 0x00 | CTRL | [0]=START | 触发一次表决计算 |
| 0x04 | STATUS | [0]=IDLE, [1]=DONE, [2]=ERR | 运行状态 |
| 0x08 | IN_BASE_LO | 31:0 | 输入缓冲区基地址（低） |
| 0x0C | IN_BASE_HI | 31:0 | 输入缓冲区基地址（高） |
| 0x10 | OUT_BASE_LO | 31:0 | 输出缓冲区基地址（低） |
| 0x14 | OUT_BASE_HI | 31:0 | 输出缓冲区基地址（高） |
| 0x18 | LEN | 31:0 | 数据长度（字节/拍） |
| 0x1C | THRESH | 15:0 | 表决阈值/参数 |

**AXI Master（M00_AXI）**

-   通过 M_AXI 从 DDR 读取输入、写回输出（突发长度由内部或寄存器控制）。
-   时钟/复位：`M00_AXI_ACLK` / `M00_AXI_ARESETN`。

---

### 6.3 Desparsification Decoder Core（AXI‑Lite + AXI Master）

**AXI‑Lite 控制（S00_AXI，示例寄存器）**
| 偏移 | 名称 | 位段 | 说明 |
|------|------|------|------|
| 0x00 | CTRL | [0]=START | 触发一次解码 |
| 0x04 | STATUS | [0]=IDLE, [1]=DONE, [2]=ERR | 运行状态 |
| 0x08 | IN_BASE_LO | 31:0 | 输入稀疏数据地址（低） |
| 0x0C | IN_BASE_HI | 31:0 | 输入稀疏数据地址（高） |
| 0x10 | OUT_BASE_LO | 31:0 | 输出密集数据地址（低） |
| 0x14 | OUT_BASE_HI | 31:0 | 输出密集数据地址（高） |
| 0x18 | N_IN | 31:0 | 输入元素数 |
| 0x1C | N_OUT | 31:0 | 输出元素数/最大容量 |

**AXI Master（M00_AXI）**

-   负责从 DDR 读取稀疏输入、写回解码结果。
-   时钟/复位：`M00_AXI_ACLK` / `M00_AXI_ARESETN`。

> Voter/Decoder 的具体寄存器布局以你的 RTL/封装为准；上表提供规范化模板，便于文档化与上位机对接。

---

## 七、网络配置

默认静态 IP：  
IP = 192.168.1.10  
MASK = 255.255.255.0  
GW = 192.168.1.1

可在 `sw/app/app_net_config.h` 修改。
