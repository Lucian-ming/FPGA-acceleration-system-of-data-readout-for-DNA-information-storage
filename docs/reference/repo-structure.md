> **归档说明**：本文是 2026-08-05 的仓库结构快照。此后文档已重组到 `docs/`（原 `DATASET.md`→`docs/reference/dataset.md`，`MISSING.md`→`docs/reference/gap-audit.md`，`STRUCTURE.md`→本文，`SUBMISSION.md`→`docs/reference/submission-archive.md`，旧 `docs/README.md`→`docs/reference/legacy-tech-note.md`），并新增了 `docs/01`~`docs/04` 与 `tools/golden_model.py`。文件职责描述仍然有效，路径以当前仓库为准。

# 仓库结构审计

审计基线：远端 `main` 分支提交 `683d6ad102c2dcdcf47709110b1c80b1feb0fdf5`（2025-11-07）含 63 个普通文件；2026-08-05 已另从用户提供的 `E:\文档\R0.83_data` 导入 7 个运行数据文件，并新增本说明、`DATASET.md` 和 `AGENTS.md` 作为开发准备文档。括号内为文件大小（字节），说明中的类别即本报告采用的分类；XSA 内部解包出的文件不另算为仓库文件。

```text
.
├── AGENTS.md 【文档】面向后续 AI/开发者的事实边界、数据契约、禁止事项和变更检查表。
├── DATASET.md 【文档】R0.83 数据集的来源、校验和、格式、已知关系与使用限制。
├── SUBMISSION.md 【文档】2025-11-07 提交资产的来源、校验和、源码差异和黄金参考关系。
├── README.md (1,613) 【文档】项目总览、环境要求和所谓“一键复现/运行”命令。
├── archive/
│   ├── R0.83_data_source.rar (6,894,183) 【LDPC资源】用户提供的 R0.83 原始 RAR5 包，含 150 bp/250 bp FASTQ 和其余 R0.83 参考数据。
│   └── submission_2025-11-07/ 【文档】从 `E:\桌面\提交` 完整保留的非重复提交资产（18 个文件，231,602,980 字节）。
│       ├── 演示文件/
│       │   ├── dec_input.txt (64,800) 【LDPC资源】演示 LDPC 输入，字节等同于 R0.83 `codeword_R083.txt`。
│       │   ├── decoded_bits.txt (54,000) 【LDPC资源】演示译码输出，字节等同于 R0.83 `source_bit.txt`。
│       │   ├── decoded_image.jpg (6,624) 【文档】演示译码图像，字节等同于 R0.83 原图。
│       │   ├── gui_app.exe (31,800,183) 【上位机Python】Windows x86-64 PyInstaller GUI 演示可执行文件。
│       │   ├── read.fastq (19,079,454) 【上位机Python】另一历史版本的 FASTQ，含 51,781 条、每条 150 bp 读段。
│       │   ├── result.txt (64,800) 【LDPC资源】与 `dec_input.txt` 和 R0.83 码字完全相同的正确结果参考。
│       │   └── watermark.txt (81,001) 【LDPC资源】演示版本文本水印，长度同为 81,000 bit 但内容不同于 R0.83 水印。
│       ├── DNA存储读出FPGA实现架构_49030_技术文档.pdf (1,401,484) 【文档】21 页的历史技术说明，含 51,781 条读段和 81,000-bit 水印等历史口径。
│       ├── DNA存储读出FPGA实现架构_49030_海报.pptx (1,618,432) 【文档】单页历史项目海报源文件。
│       ├── DNA存储读出FPGA实现架构_49030_重要代码.rar (1,209,267) 【文档】历史重要代码压缩包，保持原样归档等待具备 RAR 工具后复核。
│       ├── DNA存储读出FPGA实现架构_49030_承诺书.pdf (203,316) 【文档】历史提交承诺书。
│       ├── DAN存储读出FPGA实现架构_49030_演示视频.mp4 (172,929,104) 【文档】历史项目演示视频。
│       ├── 069a9fb033ef3d47642e6aee8818b9dc.jpg (231,107) 【文档】历史提交图片资产。
│       ├── 309927374fc5eddde6b97e9cd998e577.png (38,536) 【文档】历史提交图片资产。
│       ├── 35f83b5023b881ead7fc1621b3e611c7.jpg (212,665) 【文档】历史提交图片资产。
│       ├── 5bcc86f5d3889be808822ea8fe0fe267.png (38,652) 【文档】历史提交图片资产。
│       ├── 图片1.jpg (27,611) 【文档】历史提交图片资产。
│       └── 微信图片.jpg (2,541,944) 【文档】历史现场照片资产。
├── clients/
│   └── python/ 【上位机Python】TCP 客户端、GUI 和 LDPC 调用封装所在目录。
│       ├── first.py (20,532) 【上位机Python】命令行客户端核心，编码 FASTQ/纯文本读段并按 0xBEEF 协议与板端通信。
│       ├── gui_app.py (21,444) 【上位机Python】Tkinter 图形客户端，调用 `first.py` 后再触发 LDPC 外部解码器。
│       ├── gui_app.spec (882) 【上位机Python】PyInstaller 打包说明，声明 GUI 与 LDPC 资源的打包规则。
│       ├── ldpc_pipeline.py (4,486) 【上位机Python】复制资源、启动外部 LDPC EXE 并收集译码输出的封装。
│       └── resources/ 【LDPC资源】DVB-S2 码率 5/6 硬判决译码器及其运行数据。
│           ├── R5_6_LDPC_hard_decoder.exe (169,525) 【LDPC资源】Windows x86-64 PE 控制台可执行文件，是唯一的 LDPC 解码实现载体。
│           ├── dvb_s2_r5_6.pchk (993,612) 【LDPC资源】外部解码器读取的 DVB-S2 R=5/6 校验矩阵数据。
│           ├── permutation64800 (259,200) 【LDPC资源】外部解码器读取的长度 64,800 交织/置换表。
│           └── readme.txt (412) 【LDPC资源】说明 EXE 的输入 `dec_input.txt`、硬判决 `H` 参数和输出文件名。
├── design_2_wrapper.xsa (已删除，SHA-256 79c64736...e6eb33，依据代码卫生§5第2条与第3条，可由 git show HEAD^:design_2_wrapper.xsa 取回)
├── data/
│   └── R0.83_data/ 【文档】从用户指定目录完整导入的 DNA R0.83 输入、参考输出和水印数据；校验和见 `DATASET.md`。
│       ├── Sequencing data/
│       │   ├── DNA-40.5Kb-MC-SE150.fastq (19,079,454) 【上位机Python】51,781 条、每条 150 bp 的测序读段输入，等同于历史演示 `read.fastq`。
│       │   └── DNA-40.5Kb-MC-SE250.fastq (36,836,306) 【上位机Python】64,800 条、每条 250 bp 的测序读段输入。
│       └── Source data/
│           ├── Encoded_codeword/codeword_R083.txt (64,800) 【LDPC资源】R0.83 的 64,800-bit 二进制码字参考文件。
│           ├── Encoded_sequences/DNA-40.5Kb-MC (R=0.83).txt (40,500) 【LDPC资源】R0.83 编码 DNA 序列参考文件。
│           ├── Original data files/Milk coronet.jpg (6,624) 【文档】原始 240×302 JPEG 图像参考。
│           ├── Original data files/source_bit.txt (54,000) 【LDPC资源】原图对应的 54,000-bit 信息位参考文件。
│           └── Watermark sequences/
│               ├── SequenceL81000NoPeriodOnly2ndFILE (324,000) 【LDPC资源】81,000 个 32-bit 0/1 值形式的水印数据。
│               └── r0.83_watermark.txt (81,001) 【LDPC资源】含一个换行的 81,000-bit 文本水印。
├── docs/
│   ├── README.md (4,828) 【文档】系统拓扑、协议、接口和网络配置的技术说明。
│   └── images/
│       └── images.jpg (77,486) 【文档】919×739 架构图，图中展示 ARM、DDR3、三段 PL 流水线及 PC 端 LDPC。
├── hw/
│   ├── constr/
│   │   └── top.xdc (0) 【PL硬件RTL/IP】预留的顶层约束文件；当前为空。
│   ├── ip/ 【PL硬件RTL/IP】三个自研 Vivado IP 的包装元数据、RTL、XGUI 和仿真辅助文件。
│   │   ├── Dna_accelerator_core_1_0/
│   │   │   ├── component.xml (65,861) 【PL硬件RTL/IP】`xilinx.com:user:Dna_accelerator_core:1.0` 的 IP-XACT 接口、参数和文件集描述。
│   │   │   ├── hdl/
│   │   │   │   ├── Dna_accelerator_core_v1_0.v (21,339) 【PL硬件RTL/IP】DNA 一级核顶层，连接 AXI-Lite、AXIS、输入/结果 FIFO 与 `srpe_batch`。
│   │   │   │   ├── Dna_accelerator_core_4way.v (16,513) 【PL硬件RTL/IP】4-way 并行 DNA 核顶层变体。
│   │   │   │   ├── Dna_accelerator_core_v1_0_S_AXI_LITE_CTRL.v (6,074) 【PL硬件RTL/IP】DNA 顶层使用的四寄存器 AXI4-Lite 从接口。
│   │   │   │   ├── fifo_sync_sdpram_b64.v (1,924) 【PL硬件RTL/IP】当前 DNA 顶层实际使用的同步 FIFO/RAM。
│   │   │   │   ├── s2mm_pack64.v (3,455) 【PL硬件RTL/IP】将 DNA 结果打包为 64-bit AXIS 输出拍。
│   │   │   │   ├── srpe_batch.v (18,039) 【PL硬件RTL/IP】2-way 批处理相关/峰值搜索引擎。
│   │   │   │   ├── srpe_batch_4way.v (20,385) 【PL硬件RTL/IP】当前打包进比特流的 4-way 批处理相关/峰值搜索引擎。
│   │   │   │   └── vivado_quick_sim.tcl (4,469) 【构建脚本(Vivado/Vitis)】创建 DNA 快速仿真工程、添加波形并运行 xsim 的脚本。
│   │   │   └── xgui/Dna_accelerator_core_v1_0.tcl (9,605) 【PL硬件RTL/IP】DNA IP 的 Vivado XGUI 参数页和参数传递过程。
│   │   ├── desparsification_decoder_1_0/
│   │   │   ├── component.xml (73,148) 【PL硬件RTL/IP】`xilinx.com:user:desparsification_decoder:1.0` 的 IP-XACT 接口、参数和文件集描述。
│   │   │   ├── hdl/
│   │   │   │   ├── desparsification_decoder_v1_0.v (23,490) 【PL硬件RTL/IP】三级 5b→4b 反稀疏化核顶层，含 AXI-Lite 控制与 AXI4 Master 读写状态机。
│   │   │   │   └── desparsify_datapath.v (7,583) 【PL硬件RTL/IP】三级反稀疏化数据通路核心。
│   │   │   └── xgui/desparsification_decoder_v1_0.tcl (4,808) 【PL硬件RTL/IP】反稀疏化 IP 的 XGUI 参数页和参数传递过程。
│   │   └── differential_voter_1_0/
│   │       ├── component.xml (76,176) 【PL硬件RTL/IP】`xilinx.com:user:differential_voter:1.0` 的 IP-XACT 接口、参数和文件集描述。
│   │       ├── hdl/
│   │       │   └── differential_voter_v1_0.v (36,729) 【PL硬件RTL/IP】二级差分投票核顶层，含控制从接口、81,000-bit BRAM 累加和 AXI4 Master 访存 FSM。
│   │       └── xgui/differential_voter_v1_0.tcl (7,981) 【PL硬件RTL/IP】差分投票 IP 的 XGUI 参数页和参数传递过程。
│   ├── experimental/ 【PL硬件RTL/归档】退出打包目录的非综合 RTL；仅保留 local_correlator.v 与说明。
│   │   ├── README.md 【文档】退休规则与历史退休记录。
│   │   └── local_correlator.v (7,005) 【PL硬件RTL/实验】局部相关器实现，全库零引用但暂不满足退休三条。
│   ├── scripts/
│   │   ├── bd.tcl (7,600) 【构建脚本(Vivado/Vitis)】创建名为 `top_bd` 的 PS7、DMA、双 AXI interconnect 和三自研 IP Block Design。
│   │   ├── build.tcl (1,832) 【构建脚本(Vivado/Vitis)】创建 Vivado 工程、调用 `bd.tcl`、综合/实现并导出含 bitstream 的 XSA。
│   │   └── collect_info.tcl (0) 【构建脚本(Vivado/Vitis)】预留的信息收集脚本；当前为空。
│   └── build/
│       └── export/hardware.xsa (已删除，与原根目录 XSA 相同，SHA-256 79c64736...e6eb33，可由 git 取回)
└── sw/
    ├── app/ 【PS裸机软件】基于 Xilinx lwIP Echo 模板改写的 Cortex-A9 裸机 TCP 服务端及平台辅助代码。
    │   ├── README.txt (2,695) 【文档】遗留的通用 lwIP Echo Server 使用说明，并未描述实际自定义协议。
    │   ├── Xilinx.spec (36) 【PS裸机软件】Xilinx 交叉工具链的极简 specs 片段。
    │   ├── app_net_config.h (0) 【PS裸机软件】预留的应用网络配置头；当前为空且未被 `main.c` 包含。
    │   ├── echo.c (75,976) 【PS裸机软件】实现 TCP 分包、AXI-DMA SG、三级流水线调度、缓存维护和结果回传。
    │   ├── echo.h (10,399) 【PS裸机软件】定义协议、DDR 地址布局、三个 IP 寄存器偏移和应用状态。
    │   ├── i2c_access.c (13,161) 【PS裸机软件】遗留的 I2C/PHY 访问辅助实现，受相关硬件宏条件编译保护。
    │   ├── iic_phyreset.c (3,465) 【PS裸机软件】面向 ZCU102 I2C PHY 复位的遗留辅助代码。
    │   ├── main.c (10,563) 【PS裸机软件】硬编码静态 IP/MAC，初始化 lwIP、平台中断与三个 IP 后运行主循环。
    │   ├── platform.c (4,760) 【PS裸机软件】MicroBlaze/PPC 条件编译的平台通用实现。
    │   ├── platform.h (1,898) 【PS裸机软件】平台初始化、定时器和中断函数声明。
    │   ├── platform_config.h (158) 【PS裸机软件】指定 Zynq 平台和 `XEMACPS_0` 作为以太网 MAC。
    │   ├── platform_mb.c (3,079) 【PS裸机软件】MicroBlaze 条件编译的定时器/中断实现。
    │   ├── platform_ppc.c (2,635) 【PS裸机软件】PPC 条件编译的定时器/中断实现。
    │   ├── platform_zynq.c (6,626) 【PS裸机软件】Cortex-A9/Zynq-7000 实际选用的 lwIP 定时器、中断和缓存实现。
    │   ├── platform_zynqmp.c (5,479) 【PS裸机软件】ZynqMP 条件编译的平台实现，当前 XC7Z010 构建不使用。
    │   ├── sfp.c (7,043) 【PS裸机软件】面向 ZC706 SFP PHY 的条件编译遗留代码。
    │   ├── si5324.c (6,315) 【PS裸机软件】面向 ZC706 Si5324 时钟芯片的条件编译遗留代码。
    │   └── xparameters.h (15,318) 【PS裸机软件】从历史 XSA 导出的硬件地址、DMA、GEM0、UART1 与 PS7 参数头。
    ├── linker/
    │   └── lscript.ld (6,260) 【PS裸机软件】Cortex-A9 链接脚本，将程序放入 `ps7_ddr_0`（0x00100000 起）。
    └── scripts/
        └── create_vitis.tcl (5,256) 【构建脚本(Vivado/Vitis)】创建 standalone+lwIP Vitis 平台、导入 `sw/app`、写网络宏并构建 ELF 的 XSCT 脚本。
```

## 已核实的硬件快照

两份 XSA 均为 708,463 字节，SHA-256 均为 `79c64736b081720c9de37e608ab930b879be93c4609f55ad729c010b42e6eb33`，内容包含 `design_2_wrapper.bit`（2,083,852 字节）、`design_1.hwh`、`ps7_init.tcl` 和三个自定义 IP 的驱动片段。归档的 `design_1.hwh` 表示实际快照为 `xc7z010clg400-1`、100 MHz、GP0/HP0、GEM0、UART1，地址为 DMA `0x40400000`、DNA `0x43C00000`、反稀疏化核 `0x43C10000`、投票核 `0x43C20000`。

对当前综合顶层分别进行了不落盘的 Icarus Verilog 语法检查：DNA Testbench（连同当前综合文件集）、`differential_voter_v1_0.v` 和 `desparsification_decoder_v1_0.v` 均通过；这不是功能、时序或板上验证。
