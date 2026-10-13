# BKB220 P16 上传提速软件包构建记录

记录日期：[实测记录] 2026-10-13。源分支：`exp/upload-promotion`，提交 `9bd2b9d520a6d064aa56a14d98091f445d883291`。

**最终结论（2026-10-13 补测）：正式 P16 完整包已通过 G3，载荷 SHA 逐位相同，上传实测 0.40 s、同小时 `t_result` 为 9.33 s。** 下文最初的沙箱前置失败保留为过程记录；它只说明该次尝试没有触板。泛化与长稳没有在这个精确转正包上重跑，不能把此前包的配置级结果说成逐制品复测。

文中标记：`[实测]` 表示本轮命令、编译、哈希或工具输出；`[静态检查]` 表示对源文件/包内容的核验；`[未测]` 表示本轮没有获得板端数据。

## 软件包

- [实测] 新包：`hw/build/bkb220-p16-upload-promoted-20261013T113400Z-board-migrate/`。
- [实测] SHA256SUMS 自检覆盖 2966 个文件，`sha256sum -c SHA256SUMS` 全部为 `OK`。
- [实测] `tools/board/g3_artifacts.py --artifact-dir <新包> --device xc7z020` 通过，报告 `xc7z020clg400-2`、SE150 几何及 P16/PIPE_TREE=1；XSA 内 bit 与独立 bit 一致。
- [实测] 完整构建日志、退出码、Bootgen readback、软件摘要和源清单都保存在新包的 `logs/` 与 `reports/`。

## 实际构建路径

[实测] 开发侧使用 WSL Vitis/XSCT 2022.2、ARM GCC 11.2.0 和 Bootgen 2022.2.0。输入 XSA、bit、ps7_init 与 FSBL 来自冻结包 `hw/build/bkb220-p16-enet0-software-20261012T144141Z-board-migrate/export/`。

[实测] 正式入口 `sw/scripts/create_vitis.tcl` 使用 `xsct -nodisp` 执行。首次运行到 `platform write` 后，新 workspace 只有 BSP 骨架，尚无 `lwipopts.h`，脚本的缺文件保护因此退出 1；单独执行一次 `platform generate`（exit 0）后，头文件才出现。随后重跑正式 Tcl，脚本将 BSP 源模板中的 `TCP_WND` 改为 32768，平台/BSP 生成完成；XSCT 的 `app create` 因 `Socket create error. Operation not permitted` 退出 1。

[实测] 应用构建按实际发生的路径使用 ARM GCC：以冻结包 Makefile 为模板，将 BSP 路径指向新 XSA 生成的 BSP，把 `sw/app/` 源码复制到新 workspace（排除历史快照 `xparameters.h`），并用正式参数生成 `app_net_config.h`。`make` 退出 0，日志包含 `APP_BUILD_PASS`。Bootgen 创建 BOOT.bin 与读取 BOOT.bin 均退出 0；readback 含 FSBL、PL bit 和 `dna_lwip_app.elf` 三个 image。

由于 BSP 的 lwIP Makefile 不跟踪 `lwipopts.h` 头依赖，在头文件改好后本轮又执行了 BSP `make clean`（exit 0）和 `make all`（exit 0），清除旧对象后全量重编，避免只改头文件却沿用旧库。各次启动失败、正式入口失败及构建日志均保存在新包内，没有覆盖冻结包。

## 两处改动核验

| 改动 | 本轮证据 |
| --- | --- |
| `TCP_WND` | [实测] 新包 BSP 的 `include/lwipopts.h`、`libsrc/.../include/lwipopts.h` 和导出 `bspinclude/include/lwipopts.h` 都是 `#define TCP_WND 32768`。清理后重编的新 `liblwip4.a` SHA-256 为 `1cc4d99e395f72bd7fd39732c2c4bbd580c1f530ae256e8f3f401aa714c32d1c`；冻结包对应库为 `ce1944bed15c2bc9bf71853e0042e085e164c111fc92db39da329e540c45e6ff`。清理和重编日志见 `logs/bsp-clean.log`、`logs/bsp-build.log`。 |
| 空闲取帧 | [静态检查] `sw/app/main.c` 与新包 `workspace/dna_lwip_app/src/main.c` 逐字节相同，SHA-256 均为 `45d981fc9d7f49f199c7ebb30af5a1fb76f0ec4c3bd89c3639712cdeb14d1c6e`；默认定义为 `#define PIPE_IDLE_FETCH_N 16U`。 [实测] 该源码由 ARM GCC 编入新包 ELF，应用构建日志有 `APP_BUILD_PASS`。字节比较和两份哈希见新包 `reports/application-main-comparison.txt`。 |

## 硬件制品一致性

以下为 `sha256sum` 本轮实测；每组新包与冻结包值逐项相同。

| 制品 | 冻结包 SHA-256 | 新包 SHA-256 |
| --- | --- | --- |
| `top_bd_wrapper.bit` | `123c02b3f3d0156b7b60c935c9e48aa064a0ec2eac943361ccb656c7d8b6e6cf` | `123c02b3f3d0156b7b60c935c9e48aa064a0ec2eac943361ccb656c7d8b6e6cf` |
| `dna_accel.xsa` | `d3afb1d5d3818bd0c8ab8db4a073cc2486e7284c8def787fe12f069fe78fb14a` | `d3afb1d5d3818bd0c8ab8db4a073cc2486e7284c8def787fe12f069fe78fb14a` |
| `ps7_init.tcl` | `2f80e045cb18d7c37d5144bf0a819cd8fd42d09a622fca164f2ef7b007b6c81f` | `2f80e045cb18d7c37d5144bf0a819cd8fd42d09a622fca164f2ef7b007b6c81f` |
| `fsbl.elf` | `1f22062b9ce8e9e6898f110d02ee108a054ca455681eb66822b8a2e699e07bef` | `1f22062b9ce8e9e6898f110d02ee108a054ca455681eb66822b8a2e699e07bef` |

[实测] 对这四个文件另执行 `cmp -s`，四项 exit 均为 0；SHA 与逐字节比较输出保存在新包 `reports/hardware-sha-comparison.txt`。

## 最初沙箱尝试（当次未进入板测；后由 main 补测）

按要求尝试创建 Windows 留证目录：

```bash
cmd.exe /c "mkdir D:\bkb220_board_promo" < /dev/null
```

[实测] 命令被 WSL interop 拒绝，输出 `UtilBindVsockAnyPort:307: socket failed 1`；本会话的 `/mnt/d` 是只读 9p 挂载，无法在 Linux 侧补建目录。随后指定的 `run_g3.sh --full --skip-dump` 在 Windows 留证根目录前置检查处退出 2，尚未调用 XSDB，也未下载 bit/ELF、未与板端通信。证据见新包 `logs/windows-mkdir.log` 与 `logs/g3-prereq-failure.log`。

本轮尝试的 G3 命令：

```bash
bash tools/run_g3.sh --artifact-dir hw/build/bkb220-p16-upload-promoted-20261013T113400Z-board-migrate \
  --xsdb D:/xilinx/2026.1/Vitis/bin/xsdb.bat --device xc7z020 --strict-artifacts \
  --uart-port COM10 --ip 192.168.1.10 --port 7 --win-root D:/bkb220_board_promo \
  --full --skip-dump
```

- 板端判据 SHA `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`：[未测] 本轮没有板端载荷，不能判 PASS 或 FAIL。
- `first.py` 的读段上传耗时与吞吐：[未测] G3 未进入 XSDB/运行阶段，因此没有客户端上传日志；约 0.2 s 目标未获本轮验证。
- 多 payload 泛化与长稳：[未测] 未运行。

---

## 补记：板端判据（2026-10-13 20:0x，由 main 在主会话执行）

上面「未测」的那些项**已补测**。原因不是包有问题，而是**子 Agent 的沙箱里跑不了 Windows 二进制**：
`run_g3.sh` 的 1/7 前置检查要 `cmd.exe /c "mkdir D:\..."` 建留证目录，沙箱里报
`<3>WSL (341 - ) ERROR: UtilBindVsockAnyPort:307: socket failed 1`，于是 G3 在 XSDB 前置检查就退出 2、
**板子根本没被访问**。同一条命令在主会话里正常。→ **凡是要上板的活不能派给 codex 子 Agent。**

补测命令与结果（主会话、非沙箱）：

| 项 | 结果 |
| --- | --- |
| G3 判据（`--full --skip-dump --strict-artifacts`） | **PASS** |
| 载荷 SHA-256 | `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`（逐位相同） |
| 读段上传 | **0.40 s / 83.43 Mbps**（104 批 / 4,144,640 B） |
| 板端处理 `t_result` | 9.33 s（与参考包同小时实测的 9.33 s 相同 → 处理段未受影响） |
| 单轮 `first.py` 墙钟 | 10 s（参考包同小时为 14 s） |

**同小时参考包对照**（冻结 P16 包，`D:/bkb220_board_speed/g3_runs/20261013T091036Z/`）：
读段上传 **4.27 s / 7.76 Mbps**、`t_result` 9.33 s。→ **上传段 4.27 s → 0.40 s（10.7×）**。

### ⚠️ 一条待办：0.40 s 还没到「休眠归零」那档的 0.19 s

派生包 `PIPE_IDLE_SLEEP_US=0` 实测是 **0.19 s / 172 Mbps**，而转正版的
「连取 16 帧 + 睡 1 ms」只到 **0.40 s / 83 Mbps**——**拿回了约一半**。
理论值 `16×1514 B ÷ 1.029 ms ≈ 23.5 MB/s` 也没达到，说明瓶颈不止「每圈帧数」一项
（可能还有窗口 32 KB 与 1 ms 循环周期的配合、或每帧处理开销）。**未查清、未再调**。
若要再抠这 0.2 s，可试 N=32/64 或缩短空闲休眠；但按整轮 10 s 算只值 2%。

### 未在这个精确转正包上重跑

- 多 payload 泛化（v1 8 套 / v2 42 例）**未在这个转正包上重跑**。已跑过的是**派生包**
  （`bkb220-p16-swwnd32k-idle0-…`）：v1 8/8、v2 34 PASS/8 FAIL 且失败集与冻结参考包逐例相同。
  本包的改动与派生包**同源**（BSP 的 TCP_WND + `PIPE_IDLE_FETCH_N`），但**严格说不是同一份制品**。
- **本包**未重跑长稳；此前 P16 包已完成 2 h，8 h 未做。此处按精确制品包限定，不覆盖配置层面的既有结果。
