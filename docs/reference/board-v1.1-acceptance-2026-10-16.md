# v1.1 板端验收（2026-10-16）

**被验对象**：`hw/build/bkb220-v1.1-release-20261016T134556Z-fwid`
- bit `2ec76c7dfbe3d92ef706d8f5a60f8062e1e714fcd424b6ca9c7cee7fc313d1aa`
- ELF `7f2f6862970c20dbcebdbba1b18df4c95587bfc12e43bcfc0c87afccc6d27e28`
- XSA `8fb75a31404074c0a71aa69be8e8323473d4b4a676b573facda012284dd58979`
- `fw_build_id` `db5705fb4d0bc003`
- 源码 `517f1dc`（+ 固件构建 ID 那几笔）

> ⚠️ **本文只记录板端实测**。制品构建见 [build-v1.1-2026-10-16.md](build-v1.1-2026-10-16.md)，
> 上板前的风险审核见 [pre-board-audit-2026-10-16.md](pre-board-audit-2026-10-16.md)。

## 0. 板上固件身份**首次可证**

本次之前，**板上没有任何可读回的构建身份**（CAPS 只回几何，烧录只检查 `BOOT> running`，
严格制品门禁对完整的 v1.0 包也返回 exit=0）⇒ "v1.1 通过"无从归属。

本次为此新增了固件符号 `fw_build_id` 与板上读回核对（见 §4）。实测：

```
固件身份核对：期望=db5705fb4d0bc003；实读=db5705fb4d0bc003；结果=PASS
```

⇒ **这一次的板端结果可以严格归属到上面那份制品**，不再是"我们相信我们刷了"。

## 1. G3 三层判据：PASS

留证：`/mnt/d/bkb220_board_smoke/g3_runs/20261016T140322Z-v11-fwid-run3/`

| 步骤 | 结果 |
| --- | --- |
| 完整制品包一致性（SHA / XSA 内 bit / part / 参数） | PASS |
| 烧录（`rst -system` → `fpga` → `ps7_init` → `dow` → `con`） | PASS |
| **板上固件构建身份核对** | **PASS**（`db5705fb4d0bc003`） |
| 板端应用层就绪（CAPS） | PASS（`READY 5.1 1`） |
| **架构判据** | **PASS — syndrome 全零 0/10800** |
| **系统判据** | **PASS — SHA-256 `fcd0cf90…b1f2c3`，来源=板端合法码字直接提取** |
| 诊断层（不参与裁决） | PASS（主机译码 + SHA） |
| 四级逐级取证 | 水印 ✅ / Stage1 ✅ / Stage2 ✅ / Stage3 ✅ |
| 串口收到板端输出 | PASS（302 字节） |
| **本次裁决** | **PASS**（架构判据与系统判据均通过；诊断层不参与裁决） |

## 2. v2 挑战集 42 例：与 v1.0 **逐例一致**，**0 例危险**

运行：`ARTIFACT=<上包> OUTDIR=logs/g3/c2-v2-67-v1.1 bash logs/g3/c2-v2-67/run_all_67.sh`
脚本退出码 **1**（16 例失败 ⇒ **加固后的正确行为**：有失败必须非零，不再打印
`FULL SWEEP DONE` 假装成功）。

| | v1.0 | v1.1 |
| --- | ---: | ---: |
| G3 PASS | 26 | **26** |
| G3 FAIL | 16 | **16** |
| **verdict 逐例不同的例数** | — | **0**（42 例全同） |

**16 个失败的形态（逐例核过，这是关键）：**

| 形态 | 例数 |
| --- | ---: |
| ✅ **安全不收敛**（架构判据 FAIL + syndrome 非零 + 无载荷） | **16** |
| 🔴 **危险**（架构判据 PASS 但系统判据 FAIL = 静默给出错误字节） | **0** |
| ❓ 其他形态 | **0** |

⇒ **26 通过 / 16 安全不收敛 / 0 例危险**，与 v1.0 完全一致。
G3 三层判据设计上要挡的"合法但错误的码字"，实测 **0 例**。

**42 例的固件身份核对：42/42 PASS** —— 每一例都在复核板上跑的是不是本包。

另：`brick_wall-baseline`（`input_bytes` 未由调用者给出）走的是**新加的推断路径**：
```
载荷输出模式 : infer_payload 推断长度并以期望 SHA-256 仲裁
载荷长度由期望 SHA-256 精确确认：6730 B
```
⇒ **"客户端从板端解码结果自行判定长度/格式 + SHA 仲裁"在板上跑通**，
而且长度是**仲裁出来的**，不是调用方给的。

## 3. 8 h 长稳

**（本节在长稳跑完后补写。）**

## 4. SD 冷启动

**（待做——需要把 v1.1 `BOOT.bin` 写进 SD 卡；见 §6。）**

## 5. 过程中两次失败的根因（操作教训，值得留档）

### 5.1 第一次：`Memory write error at 0x100000. AP transaction timeout`

- **现象**：`dow`（把 ELF 写进 DDR）失败；`jtag targets` 显示
  `DAP (APB AP transaction error, DAP status 0x30000021)`，**没有 Cortex-A9 目标**；
  但**板子在网络上是活的**（CAPS 仍 PASS）。
- **根因**：**陈旧的 `hw_server` / USB 句柄**。`/dev/ttyUSB*` 全部消失、
  `usbipd` 里 FT4232H 从 `Attached` 掉成 `Shared`（设备重新枚举）。
- **修法**（项目记录的恢复三步）：
  `usbipd attach --wsl --busid 6-2` → `sudo chmod 666 /dev/ttyUSB*` →
  **按 PID** 重启 `hw_server`（项目规则：不许 `pkill -f`）。
  修完 `targets` 立刻出现 `ARM Cortex-A9 MPCore #0 (Running)`。**全程不需要动拨码。**
- ⚠️ **这修正了记录里那条模糊描述**（`logs/board/sd-cold-boot-20261016.md` §5.2 说
  "切到 SD 启动后 JTAG 扫描链枚举不出来"）：本次症状不是"链空"，而是
  "**DAP APB abort、PS 够不着**"，根因是**陈旧句柄**而非启动模式。

### 5.2 第二次：`FW_BUILD_ID_ERROR 未知参数: --elf … --hw-server … --nm …`

- **根因**：新写的 `read_fw_build_id.tcl` 里写了 `main $argv`。
  **Tcl 的变量替换不拆词**，整个列表被当作**一个**参数传进去 ⇒ 参数解析必然失败。
  必须写 **`main {*}$argv`**（Tcl 8.5+ 的展开算子）。
- 本地 `tclsh` 最小复现确认：`$argv` 传 1 个、`{*}$argv` 传 6 个。
- ⚠️ **它失败关闭了**（没有假装通过）——这正是加这道核对的目的。

## 6. 边界（**不要读成"v1.1 全部验收完成"**）

- **SD 冷启动未做**（见 §4）；**QSPI 冷启动从未做过**；
- **功耗从未测**（无仪器）；
- **SE250 profile 未构建**；
- 本文的 v2 结论是**与 v1.0 对照**得出的"逐例一致"，**不是**"v1.1 比 v1.0 更好"；
- 板端证据的**原始逐例/逐轮日志在 `logs/` 与 `/mnt/d/`**，两者**都不进 Git**
  （`.gitignore:41`）⇒ 提交材料若只留本文，审阅者无法复核逐例。**这是已知缺陷。**
