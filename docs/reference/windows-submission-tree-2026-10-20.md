# Windows 自包含提交树（2026-10-20 建立并验证）

> 本文只存在于 WSL 仓库，作为**两棵树的关系记录**。提交树本身不反向引用 WSL
> （见 `readme.md` 与 `report/design-report.md` 中无 WSL 路径）。

## 1. 关系与同步方向

| 项 | 说明 |
| --- | --- |
| 开发源 | 本仓库（WSL）：开发、实验、判据与证据的权威来源 |
| 提交树 | `D:\dna-accel-bkb220`（WSL 侧 `/mnt/d/dna-accel-bkb220`），226 MB |
| 同步方向 | **WSL 开发 → 完成后向 Windows 同步**；Windows 侧不反向修改源码 |
| 依赖关系 | 提交树自包含：不引用 WSL 路径、不依赖 usbip / WSL hw_server |

## 2. 结构

```text
dna-accel-bkb220/
├── readme.md            项目说明、目录对照、复现步骤、命名例外
├── license
├── src/                 工作树根（脚本按自身位置推根）
│   ├── hw/  sw/  clients/  tools/  tests/  data/
├── build/
│   ├── build.config / build_driver.tcl / run_build.{bat,sh}
│   ├── vivado/export、vivado/reports    2026.1 构建产物与报告
│   ├── vitis.config.json、sw-repo/      Vitis 2026.1 软件构建配置与 lwIP 覆盖库
│   ├── software-export/                 ELF / FSBL / BOOT.bin / ps7_init.tcl
│   └── artifact/                        run_g3.sh 可直接使用的完整制品包
├── board/  data/  sim/                 推荐结构的说明与入口
├── skill/                              技能包（8 个）
└── report/                             设计报告 + 大模型协作记录 + 第三方声明
```

不随包：`docs/`（本仓库文档）、`AGENTS.md`、`CLAUDE.md`、`archive/`、`logs/`、
`hw/build/`、`sw/workspace/`、原始逐轮/逐例日志。

## 3. 命名

自研源码与目录全小写、无版本号；例外三类，均在 `readme.md` 注明：

1. 4 个 Vivado IP 目录保留 `_1_0`（Vivado 按 `<IP名>_<版本>` 解析 HDL 路径）；
2. `BOOT.bin`（Bootgen 固定输出）、`SHA256SUMS`（校验清单惯例）；
3. `build/sw-repo/` 下第三方 lwIP 源码保留原始文件名。

## 4. 2026.1 构建结果（提交树内实测）

| 项 | 值 |
| --- | --- |
| 工具 | Vivado / Vitis 2026.1（Windows 原生，Python API 流程） |
| 器件 | `xc7z020clg400-2`，PL 100 MHz，P16（`P_WAYS=16` / `PIPE_TREE=1`） |
| 时序 | WNS **+0.089 ns**、WHS **+0.030 ns**（无失败端点） |
| 资源 | LUT 36,731 / FF 38,437 / RAMB36 89 / RAMB18 2 / DSP 6 |
| 固件身份 | `fw_build_id = bfcd40dd3c435a19`（ELF 内烧录、板上读回一致） |
| bit | `babfbc269a3aa7a4ffe56d9d996d23f26df1636135499c6954f47c0142246732` |
| XSA | `46fd1858c0f070b77f89dd9a158524a1cb88d007683311db43a58b39ddd24893` |
| ELF | `e71554ac3c911d3536c788e89677154002f283c625ba09136d648c4173a9b176` |
| BOOT.bin | `bbf358a78f20e0596e03e826b7a5c29ebcf8bb3f4a7987f0a8de873c24e4b7a3` |
| manifest | `9187656411e9a874cf0291d41b2af3362c89809864b9cc88826daf2024665480`（2026-10-20 路径清理后重签 `source_manifest`；bit/ELF/BOOT 未变） |

与随包 2022.2 参考报告（LUT 36,289 / FF 37,595 / WNS +0.411 ns）相比，
资源与时序差异来自工具版本，功能等价性由两级取证确认（见 §5）。

## 5. 板端验证（同一制品，五轮，全部 PASS）

| 轮次 | 驱动方式 | 结果 |
| --- | --- | --- |
| `20261020T025652Z` | WSL xsdb + hw_server（usbip） | 三层判据 PASS：烧录、`fw_build_id`、CAPS、架构 0/10800、系统 SHA |
| `20261020T025814Z` | 同上 | 三层 PASS + **四级逐级取证 4/4** |
| `20261020T030433Z` | **Windows 原生**：Git Bash × Vitis 2026.1 `xsdb` × 本机 `hw_server` × `COM10` | 三层 PASS + **四级逐级取证 4/4** |
| `20261020T031743Z` | 同上（重签 source_manifest 后，manifest `c38f3a3e…`） | 三层 PASS + **四级逐级取证 4/4** |
| `20261020T032441Z` | 同上（最终 manifest `91876564…`，包内路径清理完毕） | 三层 PASS + **四级逐级取证 4/4** |

四级数字（后两轮完全一致）：

| 级 | 结果 |
| --- | --- |
| 水印 | 47,850 / 47,850 字逐位相同 |
| Stage1 | 码字 4,096 / 4,096 相同；score 4,096 / 4,096 |
| Stage2 | 整字相同 1,253 / 1,266，比特误码 0.14% |
| Stage3 | 整字相同 997 / 1,012，比特误码 0.12% |

原始日志留在本机，不随包提交：

- `/mnt/d/bkb220_submit_work/g3-evidence/g3_runs/`（前两轮）
- `/mnt/d/bkb220_submit_work/win-native-g3/evidence/g3_runs/`（原生轮）
- 构建原始日志：`/mnt/d/bkb220_submit_work/vivado-build-logs-20261020/`、
  `/mnt/d/bkb220_submit_work/vitis-build-logs-20261020/`

不随包的原因：`summary.txt` / `boot.tcl` / `artifact_selection.json` 等生成物含宿主机
绝对路径，与"提交内容只引用项目内文件"的口径冲突；结论与数字已写入
`report/design-report.md` §12。

## 6. 提交包整理与许可处置（2026-10-20，用户拍板）

| 项 | 处置 |
| --- | --- |
| 未使用的 `r5_6_ldpc_hard_decoder.exe` + 3 个 MinGW DLL | **从包中删除**；哈希写入 `sources.json` 的 `removed_files` |
| `dvb_s2_r5_6.pchk`、`permutation64800` | **保留**；按 DVB-S2 标准出处标注，来源信息待补 |
| R0.83 原始数据与派生黄金向量 | **保留**（比赛评审用途，非公开再分发），权属状态如实写明 |
| 42 例多媒体测试集 | **保留**，逐资产来源/许可写入 `src/data/test-sets/multimedia/sources.json` |
| 61 个中文文件名（`期望结果.txt`/`参考输出.jpg`） | 改为 `expected.txt`/`reference.jpg`，引用同步 |
| 测试脚本中的宿主机留证路径 | 改为环境变量 `BKB220_BOARD_EVIDENCE`，缺省时跳过 |
| `arm_baseline.py` | **删除**：依赖旧板 Vivado Lab 2022.2 / `dna_platform_b27` BSP 与硬编码路径，在新板上可能用旧 `ps7_init` 误复位 |
| Vitis / XSDB 包装脚本的安装路径默认值 | 改为 `XILINX_VITIS` / `XILINX_VIVADO` 环境变量；`run_g3.sh` 的 `nm` 改由 `--xsdb` 推导，推导失败即报错 |
| `source_manifest` | 清理后重签（104 条源码），`manifest.json` 最终为 `91876564…`，并复跑板测（§5 后两轮） |

## 7. 已记录的限制

- 许可：`dvb_s2_r5_6.pchk` 与 `permutation64800` 的文件级来源仍待补；R0.83 数据的权利人
  与再分发授权仍未确认（见 `report/third-party-notices.md` §7）。
- 主会话的 LLM 协作记录尚未补入 `report/llm-collaboration/`。
- 逐轮/逐例原始记录不随包；报告给出统计与判据，可用 `src/tools/run_g3.sh` 复跑。
- 长稳（8h / 1736 轮）证据来自 v1.1 制品，不适用于 2026.1 制品；
  2026.1 制品目前只有单轮 + 取证轮，未重跑长稳。

## 7. 复跑入口

```bash
# 构建
build/run_build.bat                      # Vivado 2026.1
# 软件
python src/sw/scripts/create_vitis_modern.py --config build/vitis.config.json
# 组装制品
python src/tools/make_artifact_package.py --hw-export build/vivado/export \
  --sw-export build/software-export --app-src src/sw/app \
  --out build/artifact-rebuilt --package-name bkb220-release
python src/tools/write_source_manifest.py --package build/artifact-rebuilt --resign
# 板测（Git Bash，需常驻 hw_server）
cd src/tools && bash run_g3.sh --artifact-dir ../build/artifact-rebuilt \
  --xsdb <Vitis安装目录>/bin/xsdb.bat --hw-server TCP:127.0.0.1:3121 \
  --device xc7z020 --uart-port COM10 --ip 192.168.1.10 --port 7 \
  --win-root <盘符>:/<留证目录> --full
```
