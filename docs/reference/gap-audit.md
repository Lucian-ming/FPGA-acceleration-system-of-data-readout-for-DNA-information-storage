> **历史归档说明**：本文记录 2026-08-05 的缺口审计及 2026-08-06 的补充复审，**仅供追溯当时仓库状态，不代表当前状态，也不应据此派发当前缺项**。2026-08-06 的复审在此基础上定位了 6 个具体的算法实现缺陷，见 `docs/archive/history/2026/pre-bkb220-handoff-2026-10-10/status.md`；文中提到的 `DATASET.md` 现为 `docs/reference/dataset.md`，`docs/README.md` 现为 `docs/reference/legacy-tech-note.md`。

# 复现与后续开发缺口清单

审计方法：以远端 `main` 的提交 `683d6ad102c2dcdcf47709110b1c80b1feb0fdf5` 为准，逐一检查 63 个普通文件；二进制 XSA 已解包检查其 HWH、PS7 初始化和元数据。下文“路径不存在”表示该路径不在这 63 个文件中，因而没有可报告的字节数；其余结论均附文件路径及字节数。

## 2026-08-05 补充的开发事实

- 项目历史上使用过不同版本的数据，水印长度和使用的读段总数不固定；因此旧注释/常量不能被当成唯一协议规格。后续目标是上位机根据上传水印自动得到有效水印长度，板端按本次任务配置运行；上位机也必须显式决定并传达本次发送读段数。
- 用户确认现有项目的真实流水线目前不能得到正确结果；历史 Python/提交版本存在“使用已知正确结果直接生成图片”的路径，必须改为以真实板端输出为输入，经过可验证的 LDPC 后生成图片。用户随后指定正确来源为 `E:\桌面\提交`：其 `演示文件/result.txt`/`dec_input.txt` 已核实与 R0.83 正确码字完全相同，`decoded_bits.txt`/`decoded_image.jpg` 也与 R0.83 参考完全相同；这些文件现已归档，必须只作黄金 oracle，不得代替板端输出。
- 已从用户提供的 `E:\文档\R0.83_data` 及其后提供的 RAR5 包完整导入 8 个文件至 `data/R0.83_data/`（总计 56,486,685 字节）；新增的 `DNA-40.5Kb-MC-SE150.fastq` 含 51,781 条×150 bp，原先的 `SE250` 含 64,800 条×250 bp。源/目标 SHA-256 已逐文件一致；清单、格式和限制见 `DATASET.md`。它们是开发和回归的重要输入/参考，而不是当前流水线已经验证正确的证明。

## 用户列出的核查项

| 核查项 | 结论与证据 | 对复现/换板的含义 |
| --- | --- | --- |
| `hw/constr/top.xdc` 是否为空 | 是，`hw/constr/top.xdc` 为 **0 字节**；且 `hw/scripts/build.tcl`（1,832 字节）中没有 `add_files`/`read_xdc`。 | 当前设计没有 PL 外部用户端口，空 XDC 本身未必妨碍历史板的 PS `FIXED_IO` 设计；但没有任何可迁移的 PL 引脚约束。新板的 DDR、MIO、PHY 不是靠此 XDC，而是靠 PS7 配置，后者也没有被 Tcl 完整保存。 |
| `hw/scripts/collect_info.tcl` 是否为空 | 是，`hw/scripts/collect_info.tcl` 为 **0 字节**。 | 没有可用的工程/板级信息采集或导出辅助。 |
| `bd.tcl` 是否只用 PS7 自动化、未保存 DDR/MIO | 是。`hw/scripts/bd.tcl`（7,600 字节）只调用 `apply_bd_automation`，随后仅设置 `PCW_USE_M_AXI_GP0`、`PCW_USE_S_AXI_HP0`、`PCW_EN_CLK0_PORT` 三项。 | 真正的板级数据只可从 XSA 推回：其中 `design_1.hwh` 含 DDR3 `MT41J128M16 HA-125`、533.333 MHz、GEM0 MIO 16..27、MDIO MIO 52..53、UART1 MIO 48..49 等配置，而这些未写入 Tcl。因此不能仅靠 Tcl 在同一板或新板可靠复现 PS7。 |
| README 所说 `clients/python/requirements.txt` 是否存在 | 不存在；`clients/python/` 只有 `first.py`（20,532）、`gui_app.py`（21,444）、`gui_app.spec`（882）、`ldpc_pipeline.py`（4,486）和 `resources/`。 | `README.md`（1,613）给出的 `pip install -r ...` 必然失败，也未固定 GUI 所需的 Pillow 等依赖。 |
| README 的 `python client.py` 是否对得上 | 不对。`clients/python/client.py` 不存在；可执行入口是 `first.py`（含 argparse CLI）和 `gui_app.py`（Tk GUI）。 | README 运行命令必然失败，应明确选择 CLI 或 GUI 入口。 |
| README 所说 LICENSE、THIRD_PARTY_NOTICES 是否存在 | 都不存在；根目录文件列表中没有 `LICENSE`、`THIRD_PARTY_NOTICES.md`，也没有 README 所列 `.gitignore`。 | 授权边界、第三方 Xilinx/lwIP 代码通知及构建产物忽略规则未随仓库交付。 |
| LDPC 是否只有 EXE、无 C/HDL 源 | 是。唯一 LDPC 实现为 `clients/python/resources/R5_6_LDPC_hard_decoder.exe`（169,525 字节，`PE32+ x86-64 for Windows`）；相关数据为 `dvb_s2_r5_6.pchk`（993,612）和 `permutation64800`（259,200）。按全树文件名和内容职责检查，没有 LDPC 的 C/C++/Verilog/VHDL/HLS 源码或测试工程。 | 无法审计、修改、综合或移植 LDPC；在 Linux 上 `ldpc_pipeline.py` 直接执行该 EXE 也没有可用的原生运行路径说明。 |
| 两份 XSA 是否相同，哪个权威 | 完全相同：`design_2_wrapper.xsa` 与 `hw/build/export/hardware.xsa` 都是 **708,463 字节**，且 SHA-256 相同（`79c647...e6eb33`）。 | 内容上无“较新者”；`create_vitis.tcl`（5,256）会优先在 `hw/build/export/*.xsa` 搜索，因此该路径是脚本上的操作入口。根目录副本是冗余副本；而 `build.tcl` 默认会输出另一个尚不存在的 `hw/build/export/dna_accel.xsa`。 |
| 是否缺少仿真/测试向量/参考 I/O | 是。仅有 `hw/ip/Dna_accelerator_core_1_0/hdl/tb_dna_quick.v`（12,609）和 `vivado_quick_sim.tcl`（4,429）；Testbench 内部用 `$random`/函数生成数据，没有文件型向量或黄金输出。 | 没有二、三级 IP Testbench、没有端到端 TCP/DMA/LDPC 回归、没有 FASTQ/水印/`dec_input.txt`/期望图像或期望比特流样例。 |

## 阻断“一键复现”的问题（按优先级）

1. **README 的两条一键命令按文档执行会找错路径。** `README.md`（1,613）要求在根目录执行，然而 `hw/scripts/build.tcl`（1,832）以 `[pwd]/../..` 推导 `repo_root`，根目录执行时会得到仓库之外的目录；`sw/scripts/create_vitis.tcl`（5,256）同样用 `../../...` 推导 XSA、源码和 workspace。两者都隐含“当前目录是各自的脚本目录”，与 README 冲突。

2. **硬件重建脚本没有把本地三套 IP 加入 Vivado IP Catalog。** `hw/scripts/build.tcl`（1,832）没有 `ip_repo_paths` 或 `update_ip_catalog`，但 `hw/scripts/bd.tcl`（7,600）直接创建三种 `xilinx.com:user:*:1.0` IP。干净机器无法从仓库路径发现这些 IP；脚本依赖作者全局安装的 IP Catalog 状态。

3. **IP 封装自身还引用未提交文件。** 三个 `component.xml`（分别 65,861、76,176、73,148 字节）均列出其 `drivers/...` 文件和 `bd/bd.tcl`；这些目录不在对应 `hw/ip/*_1_0/` 下。相同驱动片段虽被历史 XSA 内嵌，但没有以源码形式随 IP 封装交付。

4. **提交的 XSA 不是现有 `bd.tcl` 的可验证产物。** XSA 内部是 `design_1.hwh`/`processing_system7_0`，地址为反稀疏化 `0x43C10000`、投票 `0x43C20000`；`bd.tcl` 创建的是 `top_bd`/`ps_0`/`clk_wiz_0`，并且其注释的固定地址把投票写为 `0x43C10000`、反稀疏化写为 `0x43C20000`。它虽使用自动地址分配，仍不存在可证明其能生成提交 XSA 的源 BD 或日志。

5. **PS/Vitis 可重建输入不完整。** 仓库交付的是 `xparameters.h`（15,318，历史生成物）和两份 XSA，却没有 Vitis workspace、BSP 配置/生成日志、`.elf`、启动镜像或烧写步骤。`sw/app/app_net_config.h` 为 **0 字节**，而 `create_vitis.tcl` 写入的 `APP_IP_*` 宏并没有被 `main.c`（10,563）包含；网络地址实际硬编码为 `192.168.1.10`。

6. **上位机依赖和运行样例不完整。** 除缺失的 `requirements.txt` 外，`gui_app.spec`（882）还声明打包 `dec_input.txt`，但 `clients/python/dec_input.txt` 不存在；默认的 `watermark.txt`、`read.fastq` 也不存在。没有 PC 端到板端连通性、输入格式、输出字节序和 EXE 运行成功的可复现实例。

7. **LDPC 不能继续开发。** `ldpc_pipeline.py`（4,486）只会拷贝 `R5_6_LDPC_hard_decoder.exe`、`dvb_s2_r5_6.pchk` 和 `permutation64800` 到临时目录再执行；无算法源码、码表生成器、HLS/RTL、迭代次数/吞吐/资源指标、验证向量或许可证。对方向 (B)，前两份数据文件正是必须保留并理解的关键输入。

## 已发现的不一致或高风险点

- **当前代码尚未实现“按数据版本运行时适配”。** `clients/python/first.py`（20,532）定义 `DEFAULT_TOTAL_READS = 64_800`，而 `sw/app/echo.h`（10,399）定义 `TOTAL_READS = 108000U`；这可能来自不同历史数据版本，不能仅视为注释错误。问题在于协议没有把本次实际水印长度、读段数和相关派生尺寸作为完整任务配置下发，板端三级流水线仍按 108,000 条/81,000 bit 的固定宏组织；收到较少读段后仍允许 POST，会使剩余 DDR 输入无确定初始化。R0.83 FASTQ 已证实为 64,800 条、每条 250 bp，现有 Python 却固定按 150 bp 编码，故该适配必须同时明确序列截断/编码规则。

- **文档中的 IP 寄存器表不是实现的权威来源。** `docs/README.md`（4,828）明确称各寄存器表为“示例/以实际 RTL 为准”；实际 DNA AXI-Lite 只有 4 个寄存器，投票与反稀疏化寄存器则以 `sw/app/echo.h`（10,399）和顶层 RTL 为准。缺少一份版本化、可供软件/FPGA 共同使用的寄存器与数据格式规范。

- **仿真脚本与项目目标不一致。** `vivado_quick_sim.tcl`（4,429）把 part 写成 `xc7z020clg484-1`，而项目/XSA 是 `xc7z010clg400-1`；脚本还要求 RTL 位于当前工作目录，而实际文件位于 `hdl/`。`tb_dna_quick.v`（12,609）把 AXI-Lite `AWVALID`、`WVALID` 固定为 0，故其中给 `ctrl_reg`、`start`、`preload` 的赋值不会真正写入 DUT 控制寄存器；它不是有效的端到端功能证明。

- **`hw/constr/top.xdc` 即使存在也不会参与构建。** 它为 0 字节，且 `build.tcl` 没有读入约束的命令；新板的 PL 引脚、时钟、I/O 电平约束需要重新纳入构建流。

- **硬件/软件文件包含多个遗留模板。** `platform_mb.c`、`platform_ppc.c`、`platform_zynqmp.c` 及 `sfp.c`/`si5324.c`/`iic_phyreset.c` 带有非 XC7Z010 或 ZC706/ZCU102 的条件编译内容；`sw/app/README.txt`（2,695）仍把服务称为“任何数据原样 echo”。它们未必在当前 Cortex-A9 配置下编译进最终程序，但会误导换板和维护。

- **结果长度的注释不可靠。** `echo.h` 正确将 LDPC 码字设为 64,800 bit = 8,100 byte，`echo.c` 也发送 8,100 byte；但 `echo.c` 中同一行注释写为“64800”。`first.py` 再把每字节展开成 LSB-first 的 64,800 个 `'0'/'1'` 字符。缺少黄金向量，无法确认此位序与 EXE 期望完全一致。

## 方向 (A)：更换 XC7Z010 板卡

**芯片内部可移植的部分：** 三个自研 IP 的主综合 RTL（DNA 顶层及 `srpe_batch`、`differential_voter_v1_0.v`、`desparsification_decoder_v1_0.v`）、AXI-DMA/GP0/HP0 的逻辑结构、裸机协议状态机和 Python 协议代码，原则上可在相同器件型号/速度等级上迁移；需重新评估资源、时钟和时序。Icarus 对三个当前综合顶层进行了语法检查，但尚无时序/板上验证。

**必须按新板修改/重新生成的部分：**

- PS7：DDR 型号、频率、总线宽度、训练/走线参数，MIO 复用、电平、GEM PHY 接口模式与复位、MDIO、UART、启动配置；现有具体值仅在两份 708,463 字节 XSA 的内部 `design_1.hwh`/`ps7_init.tcl` 中。
- 约束和时钟：`hw/constr/top.xdc` 为 0 字节且未进构建流；若新板有 PL 时钟、复位、GPIO、PHY 或其他外部 PL I/O，必须新增并纳入 Tcl。
- 软件生成物：从新 XSA 重新生成 `xparameters.h`、BSP、linker memory map，并核验 `PLATFORM_EMAC_BASEADDR`、GEM PHY 驱动、静态 IP/MAC；`main.c` 的 IP 与 MAC 都是硬编码。
- 烧写/启动：需要新板的 bitstream、FSBL/boot 方案、ELF 下载或 BOOT.BIN 流程；仓库没有此类步骤或产物。

## 方向 (B)：把 LDPC 解码搬到第 4 个 PL IP

现有三级核的 AXI-Lite 控制、AXI4 Master 访问 DDR 的范式，以及 `echo.c` 中的三级调度、缓存维护、TCP 结果回传可作为接口设计参考；`ic_lite` 当前配置 4 个从端口、`ic_hp` 当前配置 5 个主端口，因此加入第四核还需扩展互连、地址分配、时钟/复位、软件寄存器定义和 DDR buffer 布局。DNA/投票/反稀疏化的算法 RTL 不依赖某一块板，但 LDPC 的资源需求、DDR 带宽、时钟和时序必须在 XC7Z010 上重新预算。

关键的算法输入已经在仓库中：`clients/python/resources/dvb_s2_r5_6.pchk`（993,612 字节）定义 DVB-S2 R=5/6 校验矩阵，`clients/python/resources/permutation64800`（259,200 字节）定义 64,800 长度置换关系。它们必须被解析为 FPGA 可用的稀疏图/地址表或由可重复的生成工具转换；不能只把 Windows EXE 搬进 PL。尚缺：可审计的 LDPC 算法/源码、硬判决消息位约定、迭代/早停策略、定点位宽、并行度、BRAM/URAM/DDR 映射、吞吐/时延目标、与 EXE 的黄金向量及比特序证明。

## 建议补齐顺序

1. 先确定“权威硬件源”：导出当前板的 BD Tcl（含完整 PS7 配置）、IP 仓库/封装目录、XDC 和一次成功构建日志，并消除 `design_1` 与 `top_bd` 的差异。
2. 修正并实际验证从仓库根目录可运行的 Vivado/XSCT 脚本，再提交生成的 XSA、BSP 配置和最小可下载 ELF 或可复现生成步骤。
3. 补齐板级资料：原/新板原理图、DDR/PHY 型号、MIO/时钟/复位表、烧写与串口日志；新板先完成 GEM ping/TCP echo 再接入加速核。
4. 补齐端到端数据集：水印、FASTQ、期望一级/二级/三级输出、`dec_input.txt`、LDPC 期望 bitstream/图像，以及自动化回归脚本。
5. 决定 LDPC 的可维护实现路径，取得或重建源码/生成器，并以 `dvb_s2_r5_6.pchk`、`permutation64800` 和版本化数据集的明确映射作为受版本控制的码参数输入。
6. 最后补 Python `requirements.txt`、正确入口文档、许可证/第三方声明和 `.gitignore`。
