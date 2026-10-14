> 脱敏副本，原件 `20261014T103825Z-36c2ae3be6/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

任务（workspace-write，看板名 **ldpc-fw**）：把片上 LDPC 译码器**接进 PS 固件**，并用**新的整机 XSA** 重建一份完整软件包。

## 背景（先读）
- 新硬件包（含 LDPC IP，**已通过整机构建，WNS +0.334 ns**）：
  `hw/build/bkb220-p16-k2-ldpc-20261014T102111Z-board-migrate/`（`export/dna_accel.xsa`、`export/top_bd_wrapper.bit`）
- 参考的既有软件包结构（照它的布局）：`hw/build/bkb220-p16-enet0-software-20261012T144141Z-board-migrate/`
- 固件：`sw/app/`（唯一权威源；`sw/workspace/dna_lwip_app_b27/src` 是生成副本，**改动后要同步**）
- 流水线状态机在 `sw/app/pipeline.h`（`PIPE_*` 枚举）与 `sw/app/echo.c`（状态名表 `pipe_state_name`）；Stage3 完成在 `sw/app/stage3_decoder.c` 的 `case PIPE_DONE_STAGE3:`（约 310 行），其后 `pipeline_set_state(PIPE_SEND_RESULT)`
- 集成分工（**已定，按此实现**）：**板端把 Stage3 结果（8100 B = 64,800 位码字）送进译码器；收敛则把纠正后的码字写回同一缓冲，再走原有的 SEND_RESULT**。
  **不收敛则保持原样**。⇒ 协议、结果长度、主机侧流程、板端判据 SHA 的验收方式**全部不变**。
- 判据与边界：`docs/benchmarks/ldpc-decoder-l4.md`、`docs/reference/ldpc-architecture-decision-2026-10-14.md`

## LDPC IP 的寄存器（基地址 `0x43C30000`，AXI4-Lite）
| 偏移 | R/W | 语义 |
| --- | --- | --- |
| `0x00` | R/W | 控制：bit0 启动；bit1 复位译码器并清 done |
| `0x04` | R | 状态：bit0 busy、bit1 sticky done、bit2 converged、bit3 error、bit4 装载中、bit5 读回中；`[15:8]` 有符号迭代轮数 |
| `0x08` | R/W | 装载**字**地址，合法 `0..2024` |
| `0x0C` | R/W | 装载字数据；写一个完整字会展开为 32 次核心写入，**AXI 写响应在装载完成后才返回** |
| `0x10` | R/W | 结果**字**地址，合法 `0..2024` |
| `0x14` | R | 读它触发同步读回并拼成 32 位结果字；核心忙时返回 `SLVERR` |

**位序（已核验，别弄反）**：结果缓冲是**每字节 LSB 先**——`clients/python/fast_readout.py` 的 `fast_unpack_result` 用 `np.unpackbits(raw, bitorder="little")`。所以 64,800 位 = 8,100 字节，字的第 k 位对应缓冲的第 k 位，`word_index*32 + bit_index`。

## 你要做的
### (1) 固件集成
- 在 `sw/app/pipeline.h` 增加 LDPC 阶段的状态（建议 `PIPE_LDPC_PREP` / `PIPE_LDPC_RUN` / `PIPE_LDPC_READBACK`），在 `echo.c` 的 `pipe_state_name` 里补名字；
- 新增 `sw/app/ldpc_onchip.c` / `.h` 承载寄存器读写与流程；
- 流程：把 `DDR_DECODER_OUT_BASE` 的 8,100 B 按字（2,025 个）写进译码器 → 启动 → 轮询 done（**注意这是非阻塞状态机，别在里面死等**）→ 若 converged，按字读回并写回 `DDR_DECODER_OUT_BASE` → 然后照旧 `PIPE_SEND_RESULT`；
- **cache 处理要正确**：读 DDR 前 invalidate、写回后 flush（参考 `stage3_decoder.c` 里现有的做法与 `ddr_layout.h` 的 `ddr_layout_stage1_bytes` 之类接口，**不要用预留容量宏算本次大小**）；
- **基地址不要硬编码**：用 BSP 生成的 `xparameters.h` 里的宏（重建 BSP 后确认它的确切名字，写进答复）；
- 加一条 UART 日志，报告**收敛与否与迭代轮数**（便于板端判读）。

### (2) 用新 XSA 重建**完整**软件包
- 参考 `hw/build/bkb220-p16-enet0-software-20261012T144141Z-board-migrate/` 的目录布局
  （`workspace/`、`export/`、`reports/`、`logs/`、`manifest.json`、`artifact_manifest.json`、`SHA256SUMS`）；
- 用 `sw/scripts/create_vitis.tcl`（需**显式** `xsa=<新 XSA 绝对路径>`；它的自动搜索只找旧的 `hw/build/export/*.xsa`），产出 BSP + 应用；
- 应用用 Vitis 2022.2 的 `arm-none-eabi-gcc` 编译；FSBL 与 `BOOT.bin` 照既有包的做法重打；
- 走 `create_vitis.tcl` **正式流程**，**不要**用 `tools/build_sw_variant.sh` 派生（那是实验手段）；
- 新包另起目录名，例如 `hw/build/bkb220-p16-k2-ldpc-sw-<UTC时间戳>-board-migrate`；**不要覆盖任何既有包**；
- `SHA256SUMS` 自检必须过；`manifest.json` 里记录工具版本与来源。

### (3) 同步与门禁
- `sw/app/` 改完要同步 `sw/workspace/dna_lwip_app_b27/src/`（门禁第 8 项要求逐字节相同）；
- `bash tools/check_repo_hygiene.sh` 必须 PASS。

## 硬约束
- **不要**跑 Vivado 综合/实现（硬件包已建好，**不要重建**）；只做 Vitis/XSCT 侧。
- **不要**改 `clients/`（主机侧一行都不动）、`tools/`、`hw/ip/`、`hw/experimental/`、`docs/`。
- **不做 Git 写操作**；**不要运行 `tools/verify_repo_binding.sh`**（沙箱内 git 只读，必然失败白跑）。
- **不要碰板卡**（上板由 main 做）。
- 看板自行登记：`tools/agent_view.sh start/update/done --agent ldpc-fw ...`

## 交付
1. 改动/新增文件清单；
2. **BSP 里 LDPC 基地址宏的确切名字**（从 xparameters.h 抄）；
3. 新软件包的路径与 `SHA256SUMS` 自检结果；
4. **你验证了什么、没验证什么**——明确区分（例如"编过了"vs"上板跑过"，你没上板）；
5. 你认为**最可能在上板时出错的地方**以及判读方法。
答复用中文。