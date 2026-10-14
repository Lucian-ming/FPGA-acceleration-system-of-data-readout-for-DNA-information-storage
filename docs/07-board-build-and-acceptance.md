# 07 · 板级配置、BKB220迁移与验收

本文件合并原09板级入口与07板级迁移文档。全项目阶段F0～F9、角色分工和监控见[05执行计划](05-implementation-plan.md)，直接派发提示词见[Agent索引](agent-prompts/readme.md)。截至 2026-10-13，BKB220 `ready=1`，P4/P16 已完成 100 MHz 整机 route，P4 与 P16 均有板测；尚未完成项见 §5 和[03 当前状态](03-status.md)。

## 1. 旧基线与新板信息

| 项目 | 旧ZYNQ ECO R6 | BKB220 |
|---|---|---|
| 器件 | xc7z010clg400-1，实际已有板测 | 已按 `xc7z020clg400-2` 完成构建与板测；芯片顶标、工业级温度等级和 PCB 修订仍未逐项核实 |
| PS7/DDR | 单颗16bit MT41J256M16HA-125、512MiB，详细资料在docs/board/zynq-eco-7010/ | 原理图已入库，PS7 配置经 Vivado 2022.2 校验，DDR 写读及实板运行已通过；DDR 板级延迟与 DQS-to-CLK 仍未单独表征 |
| 时钟/UART/GEM/PHY/MIO/XDC | hw/boards/zynq_eco_7010.tcl保留原已知配置 | **已由原理图补齐**：PS_CLK 33.333MHz、UART0=MIO14/15、ENET0=RGMII、PHY=RTL8211E-VL、MDIO=MIO52/53、**PHY 地址=1**、PHY 复位接 PS_POR_B。XDC 复用 hw/constr/top.xdc（无 PL 外部引脚） |
| 制品/正确性 | hw/build/export历史五项SHA可核对，SE150真板闭环 | P4/P16 均完成整机 route、bit/XSA 构建；P4 G3 PASS，P16 smoke、全量、故障探针、42 例 v2 数据集和正式上传包 G3 有记录；六档矩阵已完成 |
| 连接 | 历史板测设备路径不能直接沿用 | **2026-10-12 已实测**：JTAG 单目标 xc7z020/IDCODE `0x23727093`；PS UART 为 UART0/MIO14-15、FT4232H C 通道（Windows COM10 / WSL `/dev/ttyUSB2`）；ENET0 为 RTL8211E、1000BASE-T 全双工。开发在 WSL 2022.2，Windows 2026.1 只负责烧录/下载/调试 22 产物（见 §3a） |

产品手册与用户提供的原理图已收录：[BKB220产品手册v1.1.pdf](board/bkb220/BKB220产品手册v1.1.pdf)、[原理图](board/bkb220/BK_B220_SchDoc.pdf)、[资料来源与SHA校验](board/bkb220/README.md)。原理图已用于核实 MIO、PHY 与复位配置；厂商 board_files/PS7 preset/例程及实物完整料号、PCB 修订仍未确认，手册示例不替代现场证据。

## 2. 配置与构建门禁

hw/boards/load_board.tcl统一选profile。未知板、ready=0、缺uart/xdc/source_refs/ps7_properties均拒绝create_project。BKB220 profile 已由 main 审核来源表并置 `ready=1`；P4/P16 构建和实板判据见对应 benchmark。该值表示配置可用于构建，不代表所有迁移终态门禁已关闭。

SE150生产：READ_BPS150、NUM_LC50、STRIDE807、REF_LEN957、BATCH64；PL100MHz；旧板/新板P4=4/0，P16=16/1，拒绝7010/P16或非法组合。每种板/路数/工具版本用独立build/export/report目录，不覆盖旧发布路径。构建后核对实际IP七参数，保存硬件summary、工具版本、完整器件/PCB与资料来源。

完整route必须WNS/WHS≥0、TNS/THS=0、失败端点0、DRC/路由/约束合法；遇到Decoder→HP或其他真实关键路径按受影响接口回归修复，不加无依据false path，不降频冒充100MHz。

## 3. 工具链和同源制品

用户指定的开发顺序（2026-10-11）：硬件与软件开发全部在 WSL 使用 Vivado/Vitis 2022.2，Windows 2026.1 只负责烧录、下载和调试 22 产物。P16 完整同 XSA 包已有 G3 记录；从硬件包到软件验收包的补步现已收敛到 `tools/rebuild_software_package.py`。2026-10-14 从当天硬件包实际重建后，SHA 与 `run_g3.sh --strict-artifacts --plan-only` 均通过；XSCT `app create` 的 socket 错误由同树 ARM GCC 回退处理。该次为只读制品门禁，不表示新重建包已上板。复现步骤与完整边界见[制品复现说明](submission/reproduce-artifacts.md)和[任务报告](../logs/submission/vitis-chain.md)。旧 ECO XSA 软件兼容探针继续保留；22 主线优化报告完成后再独立复核 Windows 2026.1 完整开发链，按下面三阶段门禁执行。

1. **22主开发**：显式VIVADO_ROOT=/tools/Xilinx/Vivado/2022.2，使用现有run_vivado_build.sh、XSim与独立build/export/report目录。已有 P16 同 XSA 包及本次重建包均覆盖 bit、ps7_init、BSP、应用 ELF、FSBL、BOOT/readback、SHA 与 manifest；本次自动化入口已实际验证平台/BSP生成、socket回退和 plan-only 门禁。托管式 `app create` 本机限制仍保留为已知偏差；不把一次 launcher exit 0 当成功，也不把 plan-only 写成板端通过。
2. **26下载**：Windows实际hw_server/XSDB2026.1仅下载22产生的bit、同XSA的ps7_init和ELF。run_g3.sh显式--artifact-dir、--xsdb、--device、--uart-port和实际IP。Hardware Manager只下载PL不能证明PS软件就绪；混合版本下载兼容性必须经真实UART/CAPS/DDR/GEM/G3验证。
3. **最后26开发复核**：22主线通过后，board在同一冻结HEAD/参数/输入上独立用Windows2026.1重建完整P4/P16硬件和同XSA软件包，rtl复核100MHz整机时序，verify复核功能/接口、新板G3、连续恢复、性能矩阵与长稳。独立目录及带SHA只读输入快照，不原地升级22工程；每包核验同源SHA，跨版本按功能/STA/统计比较，不能要求bit/ELF整文件SHA相等。未通过则保持22为发布主线并保存26失败，不能宣称26开发可靠。

Windows Vivado/Vitis2026.1位于D:/xilinx/2026.1；2026.1 XSCT已实测禁用且可能退出0，软件必须用create_vitis_modern.py/run_vitis_modern.ps1。它已在旧ECO XSA完成实际软件构建，只是兼容证据；下面现代API/BOM规则适用于最后26软件重建或main明确指定的辅助探针，不是提前改用26主开发。

完整新包须有bit、含bit的XSA、同XSA的ps7_init.tcl、BSP、应用ELF、FSBL、BOOT.bin、readback、SHA256SUMS、硬/软件summary和G3 artifact_manifest.json。实际manifest字段以g3_artifacts.py读取为准，必须记录完整part、board、工具/源码SHA、几何和P_WAYS/PIPE_TREE，并验证XSA内bit和HWH七参数。

现代软件JSON显式repo_root/workspace/xsa/export_dir/uart/board_id/part/bootgen，workspace全新、UART来自实际BSP、CPU为ps7_cortexa9_0 standalone。排除sw/app/xparameters.h历史快照；SDT地址/查询键/共享GIC/全局timer使用实际BSP，30秒超时先转64位。sw/app是权威源，workspace不手改。

**lwIP 版本按工具链实际提供的选，不要写死。**（2026-10-12 更正：原句在此处写"standalone/lwip220"，被误读成 22 主线也要 lwip220，导致 board-migrate 在 F4 因"lwip220 不在 Vitis 2022.2 安装树"而阻塞一轮。）
- **22 主线（WSL Vitis 2022.2）**：安装树只有 `lwip211_v1_5/1_6/1_7/1_8`；仓库现有 `sw/scripts/create_vitis.tcl` 本来就按 `lwip213 → lwip211 → lwip210` 回落，**以它的选择为准**；旧板已验证的 BSP 用的就是 `lwip211_v1_8`。
- **Windows 2026.1（F9 复核）**：现代 Vitis 提供 **lwip220**，届时由现代入口选择。跨版本不要求 lwIP 主版本相同，按功能/接口/统计比较。
- 通用规则：**BSP 选择必须来自实际安装树**；缺指定版本时**如实报告并按实际可用版本构建 + 标注差异**，不得静默替换，也不得因为版本号不同就判整包失败。

本机lwIP BOM兼容副本由prepare_vitis_compat_repo.py创建并验证414文件manifest；只移除描述文件BOM，不改安装或原厂库实现。构建同时要求成功哨兵、build状态0、实际非空产物、Bootgen readback和六SHA；不能仅依赖launcher exit0。完整命令及A14边界见[工具核查](benchmarks/bkb220-toolchain-audit.md)。

## 3a. 工具链分工与触板通道（2026-10-12 重写）

**用户 2026-10-12 明确：开发全部在 WSL 用 2022.2；Windows 里的 2026.1 只负责烧录。**

| 用途 | 工具链 | 位置 |
|---|---|---|
| RTL / BD / 约束 / 综合 / 实现 / 时序 / bit / XSA | **Vivado 2022.2** | WSL `/tools/Xilinx/Vivado/2022.2` |
| PS 软件（BSP / 应用 ELF / FSBL / BOOT / readback） | **Vitis + XSCT 2022.2** | WSL `/tools/Xilinx/Vitis/2022.2`（ARM GCC 11.2） |
| **烧录 / 下载 / 调试** | **Vivado / Vitis 2026.1** | Windows `D:/xilinx/2026.1` |
| F9：26 完整开发链独立复核 | Vivado / Vitis 2026.1 | 同上，22 主线稳定后 |

**22 主线是唯一发布线**：F0～F8 的构建、软件包与判据都来自 WSL 2022.2；Windows 26 **不产出**新板验收制品，只烧录 22 产出的 bit / ps7_init / ELF。2026.1 的 `xsct.bat` 实测 disabled 且可能 **exit 0**，软件必须走现代 Python 入口，且 **launcher 退出 0 不能单独作为成功判据**。

**lwIP 版本按各自安装树实际提供的选**（2026-10-12 更正）：WSL Vitis 2022.2 只有 `lwip211_v1_5/1_6/1_7/1_8`，仓库 `sw/scripts/create_vitis.tcl` 本就按 `lwip213 → lwip211 → lwip210` 回落，**以它的选择为准**（旧板已验证的 BSP 用的正是 `lwip211_v1_8`）；`lwip220` 是 **2026.1** 才有的。跨版本不要求 lwIP 主版本相同。通用规则：BSP 选择必须来自实际安装树；缺指定版本时**如实报告并按实际可用版本构建 + 标注差异**，不静默替换、也不因版本号不同判整包失败。

**通道映射（2026-10-12 实测 + 原理图双重确认）**

| FT4232H 通道 | 功能 | 序列号 | Windows | WSL |
|---|---|---|---|---|
| A | JTAG | 15051A | XSDB 直接使用 | `/dev/ttyUSB0` |
| B | 未使用/备用 | 15051B | COM9 | `/dev/ttyUSB1` |
| **C** | **PS UART（UART0 / MIO14-15）** | **15051C** | **COM10** | **`/dev/ttyUSB2`** |
| D | PL UART | 15051D | COM11 | `/dev/ttyUSB3` |

> 按序列号认通道比按 COM 号稳（重枚举后 COM 号可能变）。**不用蓝牙 COM3/COM4 兜底。**

**触板操作要点**

1. Windows 26（烧录，指定路径）与 WSL 22（`usbipd` 直通 + Linux hw_server，**F3 已验证**）两条路径都可用，但设备同一时刻只归一边。
2. 切换归属后**必须真正重新枚举 USB**（确认设备号变化）；只重启 hw_server 会只看到 `xc7z020`、看不到 `arm_dap`。
3. 断电后 FT4232H 回落 Windows、usbipd 断开，并在 3132 留下**已无设备的旧 hw_server**，恢复时先杀它再起新的。
4. **MDIO / PHY 观测必须排在 `ps7_init` 之后**；`BMSR` bit2 是 latching-low，链路状态至少读两次。

**蓝屏历史的处置（2026-10-12 用户确认已解决）**：2026-10-12 连接测试期间 Windows 主机**蓝屏两次**（BugCheck `0x139`/参数1=`0xA`，进程均为 `hw_server.exe`，栈均为 `ftdibus+0xf4d4`）。同日用户自行处置并**明确告知崩溃风险已解决**，同时确认 **USB 供电即可**。因此 **Windows 2026.1 的烧录路径按正常状态使用**。原始诊断证据保留在仓库外但**具体修复项未入仓**——"已解决"属环境所有者的判断，非本项目独立复现；WSL 22 路径（已验证）作为替代入口保留备用。

**厂商资料**：2026-10-12 递归搜 `*b220*/*bkb*` 无任何 BKB220 板卡文件，2026.1 的 `XilinxBoardStore` 只有 Xilinx 官方板，**厂商 board_files/PS7 preset 仍缺**；但**厂商原理图已入库**（[BK_B220_SchDoc.pdf](board/bkb220/BK_B220_SchDoc.pdf)，核对见[来源表 §10](board/bkb220/migration-source-table.md)）。

## 4. 本轮已验证准备成果

| 内容 | 结果/摘要 |
|---|---|
| 正式可选P4/P16、源集、参数/包装 | 打包与2022.2真实catalog通过；[集成摘要](benchmarks/stage1-16way-ip-integration.md) |
| LC50模块与真实包装接口 | Windows2026.1 XSim两个case各两轮PASS，Icarus模块同周期；约3.27倍仅模块周期 |
| G3严格制品选择、串口与性能入口 | 47项主机fixture/替身测试通过；[主机摘要](benchmarks/bkb220-host-verification.md) |
| Windows2026.1软件路线 | 旧ECO XSA A14：BSP/应用/FSBL/BOOT/readback/六SHA PASS；不是新板制品 |
| **BKB220 F4 整机 G3** | **P4 PASS（7/7）**（[来源表 §13](board/bkb220/migration-source-table.md)）：同源包真实下载并端到端跑通，**图片 SHA `fcd0cf90…f2c3` 逐位相同**、四级 DDR 取证通过、CAPS READY。后续 P16 smoke、全量三轮、连续/状态复位、故障探针及 v2 数据集对照已完成；正式 P16 上传配置包 G3 PASS，见相应 benchmark。 |
| **BKB220 P4/P16 整机 100MHz 构建** | **PASS**（[benchmark](benchmarks/bkb220-p4-p16-100mhz-build.md)）：均为 `Physopt postRoute`，P4 WNS+0.680/WHS+0.036、P16 WNS+0.617/WHS+0.017，**失败端点均 0**，DRC 各 **0 errors**，`clk_fpga_0`=100.000 MHz，XSA 内 `PART=xc7z020clg400-2`；P16 33,987 LUT（63.89%）。P4/P16 已有对应板测。 |
| **BKB220 PS7 catalog 验证** | 29 属性经 Vivado 2022.2 逐条检查（[来源表 §8](board/bkb220/migration-source-table.md)）。`MT41K256M16TW-107` **被 catalog 拒绝**，改用 `Custom` + 自定义容量/时序；`xc7z020clg400-2` 在库中，但手册的工业级条目未确认 |
| **BKB220 F3 实板最小启动** | **通过**（[来源表 §9](board/bkb220/migration-source-table.md)）：`ps7_init`/`ps7_post_config` RC=0；DDR 0x10000000 起 1024 字写读 0 不符；PS UART = UART0/MIO14-15 → FT4232H 通道 C（`/dev/ttyUSB2`）115200 8N1 明文正确；PS_CLK 33.333 MHz、DDR 533.33 MHz、FCLK0 100 MHz；**ENET0 MDIO 通、PHY = RTL8211E、1000BASE-T 全双工 link up**。尚缺 CAPS（需固件，属 F4） |

计划与索引曾先推送c4d7ad4；后续用户已明确授权代码和完整整理交付。原三子Agent额度中断后 main 接管。上述构建、板测结果不代表所有剩余迁移门禁均已关闭。

## 5. 迁移顺序与真实验收

1. 配置与连接：`ready=1`；原理图、PS7 配置、JTAG、UART0/COM10、ENET0 PHY 与链路均已有核实记录。实物完整料号、PCB 修订、DDR 板级延迟/DQS-to-CLK 仍未确认。
2. P4/P16 整机 100 MHz route、bit/XSA、完整 P16 同 XSA 包已构建；P4 G3、P16 smoke/全量/连续恢复/故障探针/性能矩阵已完成。
3. 泛化边界：P4/P16 对 v2 42 例与软件验证器 42/42 判定一致；8 个 challenge 例仍失败（LDPC 不收敛），v2 `score_min=67` 未板测，新载荷四级逐级取证未完成。
4. 后续门禁：8 h 长稳（2 h 已完成）、QSPI/SD 冷启动、UART 反向、实测功耗、F9 Windows 2026.1 完整开发链独立复核；Vitis 自动化构建路径还需收敛。
5. 完整样本和失败保留，详情见 03、05、09 与对应 benchmark。迁移收尾时核对源/参数/工具/制品/SHA、复现命令、限制和文档。

板端G3唯一入口是run_g3.sh --artifact-dir完整包，加显式XSDB/device/PS串口/IP；矩阵脚本不自动下载，先确认已加载对应包。JTAG成功不能证明SD/QSPI冷启动；BOOT打包不能当冷启动PASS，非易失介质出厂镜像不默认覆盖。

### 5a. G3 的三层判据（2026-10-14 确立，同日更正一次）

判据实现在 `tools/board/g3_judge.py`，在线由 `tools/run_g3.sh` 逐轮调用，离线只读复算用
`run_g3.sh --offline-recheck <留证目录>`（不触板、中间产物只落临时目录，历史留证保持只读）。

| 层 | 回答什么问题 | 判据 | 是否参与裁决 |
| --- | --- | --- | --- |
| **架构判据** | 板端到底纠对了没有 | 板端回传码字的 **syndrome 全零** | **是** |
| **系统判据** | 载荷出来的就是期望的那一份吗 | 从**板端合法码字直接提取**的字节 SHA-256 | **是** |
| 诊断层 | 旧口径还能不能过 | 主机译码 + 载荷 SHA | 否，**只记录** |

**裁决 = 架构判据 且 系统判据都通过**（`g3_judge.py` 的 `verdict` 字段）。两层各自挡住一类真实错误：

- 架构判据挡住**主机译码兜底**：板端没纠对，靠 PC 补出来也算过。这类错误真实发生过——
  留证 `/mnt/d/bkb220_board_smoke/g3_runs/20261014T110319Z` 的 syndrome 有 **332/10800 行非零**，
  而旧口径（主机译码 5 轮）SHA 照样等于期望值，**旧判据会判 PASS**；新判据判 FAIL 并显式标注
  「PC 兜底标记：发生」。
- 系统判据挡住**合法但错误的码字**：syndrome 全零（架构 PASS），可是板端载荷出来的字节不是期望的，
  **结果是错的**。旧口径在这种情形下判 FAIL，所以若只让架构判据决定裁决，就**比旧判据更宽**。

⚠️ **本项目一度采用过「仅架构判据决定裁决」的写法，那是错的**：它会在上面第二类错误上判 PASS。
已更正为两者都须过（2026-10-14，main）。同时保留一条边界：**系统判据不得反向救场**——
架构判据没过时，系统判据取的是 PC 诊断译码的结果，只作比较，不改变 FAIL。

**离线复算的三个方向都已实测**（`logs/verify/g3-twofold.md`）：
 `20261014T142107Z` 架构 PASS + 系统 PASS ⇒ exit 0；
 `20261014T110319Z` 架构 FAIL（332/10800）⇒ exit 1；
 把期望 SHA 换成 64 个零构造「架构 PASS + 系统 FAIL」⇒ exit 1。

**这套判据为什么非有不可——一对天然对照**（2026-10-14 留证，可离线复算）：

| 留证 | PL bitstream | PS ELF | 架构判据 | 旧口径 |
| --- | --- | --- | --- | --- |
| `…/20261014T142244Z` | `8f0da7bf…` | `8be9ef4c…`（缺解交织） | **FAIL** 332/10800 | PASS |
| `…/20261014T142345Z` | `8f0da7bf…` | `6ec76fc5…`（已修） | **PASS** 0/10800 | PASS |

两轮的 **PL bitstream 逐字节相同**，差别只在 **PS 侧软件**；而两轮的**载荷 SHA 都等于期望值**
（PC 译码把坏的那份也补出来了）。⇒ **bit SHA 分不出这两份，载荷 SHA 也分不出，
只有 syndrome 判据能分。**

这与上一条**互为镜像**，合起来说明为什么必须是"都须过"而不是"某一层说了算"：

| 单一判据说了算 | 会被它放过的错误 | 上面哪条证据 |
| --- | --- | --- |
| 只看**系统**（载荷 SHA） | 板端未纠对、靠主机译码补出正确载荷 | 本节的 bit 相同 / ELF 不同那一对 |
| 只看**架构**（syndrome 全零） | 合法但错误的码字（载荷不是期望的） | 上一节"旧判据会判 PASS"那条 |

**今日 13 份留证按新口径离线复算**：7 PASS / 6 FAIL，**每一条 FAIL 都可解释**——
用的是缺解交织的坏 PS 包（`…-ldpc-sw-20261014T104331Z`），或**PL 里根本没有片上 LDPC**
的对照包（`…-upload-promoted-…`、`…-k2freeze-…`，它们本来就只回传未纠正的码字）。
**没有出现无法解释的失败。**

## 6. 完成定义和回退

P4/P16 配置、合法 100 MHz 整机 route、同源制品、全量/连续/恢复及六档矩阵已有通过记录；当前仍不能宣布全部迁移与交付终态完成，因 8 h 长稳、v2 新载荷 `score_min=67`、新载荷四级取证、冷启动、UART 反向、功耗和 F9 尚待完成。旧 SE250、P14 OOC、仿真与 A14 兼容探针均不能替代这些门禁。失败保留独立 run 和报告，不覆盖历史数据、export 或失败证据。
