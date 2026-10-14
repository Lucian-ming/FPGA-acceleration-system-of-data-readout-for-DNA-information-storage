# 从源码与 XSA 重建可验收制品包

本文记录本项目从 Vivado 硬件输出到可由 `run_g3.sh --strict-artifacts` 接受的软件包的复现路径。硬件与软件分两步：`tools/run_vivado_build.sh` 生成硬件包，`tools/rebuild_software_package.py` 从一份硬件包生成 BSP、FSBL、应用、BOOT 和门禁清单。

## 工具版本与环境

项目的发布主线固定在 WSL Vivado/Vitis **2022.2**：

- 硬件 XSA 的 `generatedVersion` 为 2022.2，软件平台、BSP 和 FSBL 使用同一安装树生成；ARM GCC 实测为 11.2.0，Bootgen 实测为 2022.2.0。
- 竞赛说明列出 Vivado 2026.1/2025.2；竞赛允许其他版本时，必须如实列出实际版本并给出可复现步骤。本项目按既定的 22 主线使用 2022.2，不把它标成 2025.2 或 2026.1。Windows 2026.1 只用于下载、调试 22 产物。
- WSL 安装位置固定为 `/tools/Xilinx/Vivado/2022.2` 与 `/tools/Xilinx/Vitis/2022.2`。Vitis 2022.2 的安装树提供 `lwip211`、不提供 `lwip213`；Tcl 入口按 `lwip213 → lwip211 → lwip210` 探测，本次实测选择 `lwip211_v1_8`（上游 2.1.1）。
- 运行环境还需要 Python 3、GNU make、`sha256sum`、unzip，以及 Vitis 自带的 XSCT、ARM GCC、Bootgen。入口会拒绝覆盖已有输出目录。

## 命令序列

### 1. 从 RTL/BD 构建硬件包

从仓库根目录执行以下命令。`HW_RUN` 必须是新的独立目录：

```bash
export VIVADO_ROOT=/tools/Xilinx/Vivado/2022.2
HW_RUN="hw/build/bkb220-p16-k2-ldpc-prefillopt-$(date -u +%Y%m%dT%H%M%SZ)-reproduce"
tools/run_vivado_build.sh \
  board=bkb220 part_name=xc7z020clg400-2 \
  proj_name=bkb220_p16_k2_ldpc_prefillopt clk_mhz=100 \
  build_dir="$HW_RUN/build" export_dir="$HW_RUN/export" \
  report_dir="$HW_RUN/reports" stage1_p_ways=16 stage1_pipe_tree=1
```

**未实测这条 Vivado 构建命令**：本次任务按要求从当天已有硬件包开始，没有重跑综合与实现。查看入口参数的 `tools/run_vivado_build.sh --help` 为 ✔ 实测、退出 0。实际硬件构建成功判据为：新 `export/` 中 XSA、`top_bd_wrapper.bit` 和 `hardware_build_config.txt` 均非空；`reports/timing.rpt` 达到 100 MHz 收敛条件（WNS/WHS ≥ 0、TNS/THS=0、失败端点为 0）；配置记录与 XSA 的 part、生成版本、HWH 几何和 P_WAYS/PIPE_TREE 一致。下一步的软件入口会再次核对 XSA、独立 bit 与配置文件的一致性。

### 2. 由硬件包生成软件制品包

本次**真实完整运行**使用了当天的 P16 硬件包，输出为新目录：

```bash
tools/rebuild_software_package.py \
  --hw-package hw/build/bkb220-p16-k2-ldpc-prefillopt-20261014T124533Z-board-migrate \
  --out hw/build/bkb220-p16-k2-ldpc-prefillopt-sw-20261014T135534Z-vitis-chain \
  --label 20261014-vitis-chain
```

本次命令为 ✔ 实测、退出 0；完整控制台日志为 [`vitis-chain-run.log`](../../logs/submission/vitis-chain-run.log)。帮助命令 `tools/rebuild_software_package.py --help` 也为 ✔ 实测、退出 0。重新复现时，`--out` 必须改成一个尚不存在的新目录。

入口会检查 XSA 内嵌 bit 与硬件包独立 bit 的 SHA、读取 XSA 的 PS7 初始化脚本，并在新 workspace 中调用 `sw/scripts/create_vitis.tcl`。Tcl 先运行第一次 `platform generate` 物化 BSP 头文件，再把 `lwipopts.h` 的 `TCP_WND` 设为 32768 并重新生成平台/BSP。入口读取新 BSP 的 `include/lwipopts.h` 和 lwIP 源模板，确认值确实为 32768；若头文件未生成或值不符则失败退出。

XSCT 还会生成 standalone 平台、BSP 和 FSBL。若 XSCT 在 `app create` 阶段返回已知的 `Socket create error. Operation not permitted`，入口会在标准输出与 `logs/xsct-build.log` 中明示错误及回退，然后使用**同一个 Vitis 2022.2 安装树**的 ARM GCC 11.2.0 编译 `sw/app` 副本，并链接刚生成 BSP 的 `liblwip4.a` / `libxil.a`。源码副本逐字节核对；历史 `sw/app/xparameters.h` 不会复制进应用源码目录。其他 XSCT 错误不触发回退，会非零退出。

入口随后生成 `export/dna_lwip_app.elf`、从同一硬件平台取 FSBL、运行 Bootgen 生成 `BOOT.bin`，再用 `bootgen -read BOOT.bin` 检查其中恰有 `fsbl.elf`、`top_bd_wrapper.bit`、`dna_lwip_app.elf` 三个 image。它生成 `manifest.json`、`artifact_manifest.json`、`reports/source_manifest.json` 和 `SHA256SUMS`，最后执行 SHA 自检及 G3 strict plan-only 门禁。

逐项成功判据：

1. BSP include 头存在，且 `TCP_WND=32768`；新 BSP 有非空 `libxil.a`、`liblwip4.a`，FSBL 非空。
2. 如果触发 GCC 回退，应用构建日志含 `APP_BUILD_PASS`，且输出 ELF 非空。
3. `BOOT.bin` 非空，Bootgen readback exit 0 并报告 3 个上述 image。
4. `manifest.json` 与 source/artifact manifest 都在 `SHA256SUMS` 中；`sha256sum -c SHA256SUMS` 每项均为 `OK`。
5. `run_g3.sh --strict-artifacts --plan-only` 退出 0，并打印“只读制品/工具核验完成”。这只表示静态制品门禁接受，不表示上板通过。

### 3. 可单独复核的只读门禁命令

本次以下两条命令均为 ✔ 实测并退出 0：

```bash
cd hw/build/bkb220-p16-k2-ldpc-prefillopt-sw-20261014T135534Z-vitis-chain
sha256sum -c SHA256SUMS
```

实得 **2965/2965 OK**。

```bash
cd /home/lucian/projects/FPGA/FpgaAccelerationSystemOfDataReadout
tools/run_g3.sh \
  --artifact-dir hw/build/bkb220-p16-k2-ldpc-prefillopt-sw-20261014T135534Z-vitis-chain \
  --strict-artifacts --device xc7z020 --ip 192.168.1.10 \
  --xsdb /tools/Xilinx/Vitis/2022.2/bin/xsdb \
  --hw-server TCP:127.0.0.1:3132 \
  --win-root /tmp/vitis-chain-plan-only-final \
  --uart-port /dev/ttyUSB2 --plan-only
```

XSDB、hw_server、串口和留证路径参数满足脚本的静态参数检查；`--plan-only` 在检查完制品后提前退出，不打开串口、不连接 JTAG、不下发 TCP、不创建 run。该门禁命令没有访问板卡。

## 本次实测结果与已知偏差

- 新包 `board_id=bkb220`、`part=xc7z020clg400-2`，生产参数与手工包相同：READ_BPS=150、NUM_LC=50、STRIDE=807、REF_LEN=957、BATCH=64、P_WAYS=16、PIPE_TREE=1；Vivado/Vitis/XSCT/GCC/Bootgen 版本字段均匹配。
- 新包 `top_bd_wrapper.bit` SHA-256 为 `8d17d17e54ee46d9e32b087fccfd5afef20a09539b38e4b5858f7d1873f38898`，与当天手工包完全一致；包内 XSA、`ps7_init.tcl` 和 `BOOT.bin` 也逐字节同 SHA。FSBL/ELF 全文件 SHA 因重新生成而不同；对两份 ELF 用 ARM GCC `objcopy` 比较 `.text`、`.data`、`.rodata`，应用和 FSBL 三个段均相同。新旧 LDPC base address 数值均为 `0x43C30000`，JSON 字符串仅十六进制字母大小写不同。
- 实测 XSCT 选择 `lwip211_v1_8`。启动时提示 `lwip213` 不在 2022.2 repository，这是安装树差异；脚本按既有顺序回落并记录所选库，不把该提示当成构建成功判据。
- 实测 `app create` 报 `Socket create error. Operation not permitted`，XSCT 返回 1；入口明确回落到同树 ARM GCC，最终 `APP_BUILD_PASS`、Bootgen readback、SHA 和 G3 plan-only 全通过。
- 受本次任务边界限制，未重新运行 Vivado 硬件构建，也未启动硬件服务、下载、烧录或运行真实板端 G3。重建包可被 `--strict-artifacts` 只读门禁接受；板端验收仍需按 `docs/07-board-build-and-acceptance.md` 单独执行。

实际输出、哈希对照与门禁记录见 [`vitis-chain.md`](../../logs/submission/vitis-chain.md)。
