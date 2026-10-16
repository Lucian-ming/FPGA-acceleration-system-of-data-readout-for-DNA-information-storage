# SD 卡冷启动（2026-10-16）

项目欠账之一：**QSPI/SD 冷启动**。此前所有板测都是 **JTAG 灌入**（`fpga -f bit` + `dow elf`），
**从未验证过板子能否自己启动**。本次做的是 **SD 卡**这一路。

## 1. 结果：通过（功能层）

**板子从 SD 卡自行启动，跑起我们的固件，并在不碰 JTAG 的前提下通过 G3 三层判据。**

| 项 | 值 |
| --- | --- |
| 留证 | `/mnt/d/bkb220_board_smoke/g3_runs/20261016T093751Z` |
| 命令 | `tools/run_g3.sh --skip-boot --skip-dump --full --score-min 67` |
| 烧录步骤 | **SKIP（`--skip-boot`）—— 全程没有任何 JTAG 写操作** |
| 板端就绪 | `READY 2.0 1`（握手只用了 2 秒 ⇒ 板子早已自行起来） |
| 任务 | 103,616 条记录 / `score_min=67` / `Result: 8100 bytes, 4.87s` |
| 架构判据 | **PASS** — syndrome 全零 0/10800 |
| 系统判据 | **PASS** — SHA-256 `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3` |
| 本次裁决 | **PASS** |
| 串口 | `[PIPE] total 79682 steps`（分级静默固件，成功路径只打这一行） |

另：`192.168.1.10` 的 ARP 是 `00:0a:35:00:01:02`（**Xilinx 默认 MAC**），
与"板端 lwIP 应用在跑"一致。

## 2. 卡上放了什么

写的是**当日推广包**的 `export/BOOT.bin`：

- 大小 **4,411,984 B**，SHA-256 `69a33763510bad963d8d3bf4a956ec102536b7a55402a4e984150e451066e51c`
  —— **与构建产物逐字节一致**（`cmp` 核过），卡上再核对一次相同；
- 内容（`export/boot.bif`）：`[bootloader] fsbl.elf` + `top_bd_wrapper.bit` + `dna_lwip_app.elf`
  ⇒ **一次上电把 PL + 应用整套拉起来**，不依赖 JTAG；
- 头部 `feffffea`（ARM 异常向量）+ `665599aa XNLX`（Zynq boot header）⇒ 合法启动镜像。

### ⚠️ 出厂镜像没有被丢

卡原本是**厂商出厂演示卡**（根目录有 `BOOT.BIN` 2,269,972 B + Alarms/DCIM/Pictures 等目录）。
按项目硬规则「**不覆盖出厂镜像**」：

- **整卡已备份**到 `D:\bkb220_sd_backup_20261016T091532Z\`（2.2 MB）；
- 厂商 `BOOT.BIN` 的 SHA-256 = `5d83ce5fc17ce5bea6ae0438a113b46b0d296dde364d85005f2910030221e41a`；
- 卡上其余目录**原样未动**（那 6 个"媒体文件"全是 0 字节的 Android 缩略图残留，无用户数据）。

## 3. 拨码

手册（`bkb220-product-manual-v1.1.pdf`，第 3 章）的 BOOT_CFG 表：

| BOOT_CFG | 1 | 2 |
| --- | --- | --- |
| JTAG | ON | ON |
| QSPI/FLASH | ON | OFF |
| **SD_CARD** | **OFF** | **OFF** |

由用户把两个拨码都拨到 **OFF** 后上电。

⚠️ **概念澄清（本次反复确认过）**：`BOOT_CFG` 选的**不是"开不开 JTAG"**，
而是**上电后 BootROM 从哪儿加载启动镜像**。JTAG 是硬件调试口，**任何启动模式下都在**。
所以"切到 SD 之后 JTAG 还通"是正常的；反过来，**JTAG 能连上也不等于冷启动成功**——
冷启动的唯一证据是"不碰 JTAG、板子自己起来并跑对"，也就是上面那张表。

## 4. 边界（**不要读成"冷启动已完全通过"**）

- ⚠️ **没抓到 FSBL 自己的启动日志**。串口抓取必须在上电**之前**就开始，
  而本次是板子已经在跑之后才接上的。**"从 SD 启动"是由这三条推出来的、不是日志直接读到的**：
  ① 用户把 BOOT_CFG 拨到 SD 并上电；② QSPI 从未写过（项目记录）；③ 全程无 JTAG 写操作。
- ⚠️ **只做了 SD，没做 QSPI**。两项都算"冷启动"，本次只关掉 SD 这一半。
- ⚠️ **不证明跨温度/电压/多次上电的稳定性**；只证明**这一次**能起来并跑对。
- ⚠️ **不覆盖四级逐级取证**：本次 `--skip-dump`（dump 要 XSDB/JTAG）。
- 本次是**单个载荷**（R0.83 SE150 全量）的一轮；不是长稳、不是成功率统计。

## 5. 过程中遇到的两件事（都影响后续工作流）

### 5.1 板子每次重新上电，`usbipd` 的 attach 都会掉

FT4232H 在板上，**板子断电它也跟着重新枚举** ⇒ WSL 侧 `/dev/ttyUSB*` 消失、
`hw_server` 持有的 USB 句柄失效（表现为 `jtag targets` 空链）。
**每次上电后都要走三步**：

```
cmd.exe /c "usbipd attach --wsl --busid 6-2"     # busid 每次可能不同，先 usbipd list 查
sudo chmod 666 /dev/ttyUSB*                       # 用户不在 plugdev
# 按 PID 精确重启 hw_server（禁用 pkill -f，见 CLAUDE.md）
```

⚠️ 注意 `ttyUSB0` 是**通道 A = JTAG**，被 `usbfs`（hw_server）持有；
`ttyUSB1/2/3` 才是三个串口，**PS UART 是 `ttyUSB2`**。

### 5.2 ⚠️ 未解释：**切到 SD 启动后 JTAG 扫描链枚举不出来**

- 板子在 SD 模式下**上电并正常运行**（网络应答、G3 PASS），
  但 `jtag targets` 返回**空链**（连 `FT4232H` 那行都没有），
  `usbipd` attach 正常、接口 `1-1:1.0` 由 `usbfs` 持有（没被 `ftdi_sio` 抢）、
  只有**一个** `hw_server` 实例、detach/attach 循环过、重启并等待 20 s 过 —— **仍然为空**。
- 对照：**今天 07:46 板子在 JTAG 模式下时，链是正常枚举的**
  （`Xilinx HW-Z1-ZCU104 FT4232H 15051A` → `arm_dap 4ba00477` → `xc7z020 23727093`）。
- ⇒ **观察到的相关**：JTAG 模式能枚举、SD 模式不能。**未做机理分析，不得据此下因果结论。**
- **影响**：本次冷启动验收不受影响（`--skip-boot --skip-dump` 不需要 JTAG）。
  但**常规工作流（JTAG 烧录 + 四级 dump）依赖 JTAG**，这一条要先解决。
- **下一步实验**：把拨码拨回 ON/ON 上电，再枚举一次 —— 若恢复正常，则相关性坐实；
  若仍为空，则是 USB/线缆/供电层面的问题。
