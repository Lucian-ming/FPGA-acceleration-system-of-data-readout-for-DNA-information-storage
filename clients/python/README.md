# 上位机客户端使用说明

本目录提供 tkinter GUI 与命令行板端客户端。客户端负责读段解析、任务配置、TCP 上传/回传和 LDPC 译码；它不替代板端固件，也不代表板卡已经通过验收。

## 1. 环境与依赖

- Python 3.8 或更新版本。
- Python 依赖：`numpy`、`Pillow`，通过本目录的 `requirements.txt` 安装。
- GUI 需要 Tcl/Tk。Windows 安装 Python 时需包含 Tcl/Tk；Debian/Ubuntu/WSL 可安装与 Python 对应的 `python3-tk`。本仓库当前使用环境实测缺少 `tkinter`，直接启动 GUI 会退出并提示安装图形界面运行库。

在仓库根目录执行：

```bash
python3 -m venv clients/python/.venv
source clients/python/.venv/bin/activate
python -m pip install -r clients/python/requirements.txt
```

Windows PowerShell：

```powershell
py -m venv clients\python\.venv
.\clients\python\.venv\Scripts\Activate.ps1
python -m pip install -r clients/python/requirements.txt
```

Linux 若 Tk 不可用，安装系统包后再启动 GUI：

```bash
sudo apt update
sudo apt install python3-tk
```

## 2. 启动 GUI

在仓库根目录运行：

```bash
python3 clients/python/gui_app.py
```

Windows：

```powershell
py clients\python\gui_app.py
```

界面中依次选择水印文件、FASTQ/纯文本读段文件和结果文件；确认板端 IP/端口、几何规格、阈值、方向、传输批大小、读段数和 LDPC 后端，然后点“启动硬件加速全流水线”。“测试连接”只测试 TCP 连接；“仅重跑 LDPC 译码”读取输出结果文件，不会连接板端。“保存参数预设...”与“加载参数预设...”使用 JSON 保存/恢复连接与任务参数（不包含水印、读段和输出文件路径）；无效文件会报错且不会部分应用。运行日志会显示 CAPS/CONFIG、上传与译码状态；窗口关闭后当前日志和指标不会作为历史记录保留。

## 3. 命令行运行

`first.py` 负责板端交互并将板端回传的 64,800 个结果位保存到 `--output`；它**不执行 LDPC 译码**。译码后端可在 GUI 的“LDPC 后端”下拉框中选择。命令行 dry-run 会检查输入、推导任务配置并打印 CONFIG，不连接板端：

```bash
python3 clients/python/first.py \
  --watermark tests/datasets/common/watermark.txt \
  --reads tests/datasets/D1_random_entropy/reads_se150.fastq \
  --limit 64 --read-bps 150 --dry-run
```

本环境实测输出包含：`PKT_CONFIG(0x05) 44B`、`每条读段线上 40 B`、`read_bps=150`、`total_reads=128`、`score_min=67` 和 payload hex；传输统计为 0，未连接板端。这里 `--limit 64` 指 64 条源读段；默认 `--orient both` 会上传正向与反向互补两份，所以 CONFIG 中为 128 条。

连接板端时去掉 `--dry-run`，替换为实际地址和输入文件：

```bash
python3 clients/python/first.py \
  --ip <板端IP> --port 7 \
  --watermark <水印文件> --reads <FASTQ或纯文本读段文件> \
  --output <结果文件> --read-bps 150 --orient both \
  --result-timeout 180
```

Windows 可将 `python3` 换成 `py`，并使用 PowerShell 路径格式。输入格式默认 `auto`，也可指定 `--format fastq` 或 `--format plain`。`--total-reads N` 表示要求恰好处理 N 条源读段；`--limit N` 表示最多处理 N 条源读段。当前结果输出路径会被后续运行覆盖；需要保留多轮结果时，为每轮指定不同的 `--output` 文件名。

## 4. LDPC 后端选择

GUI 的后端选项如下。`auto` 是默认值：有经过清单校验的本机 C 动态库时优先使用 `c_accel`，否则用 `native`。C 库哈希不符会直接报错并拒绝载入；C 运行时自身失败时，`auto` 会在日志中说明并回落到 `native`。

| 后端 | 实际实现 | 选择建议 |
|---|---|---|
| `native` | `native_ldpc.py` 中的纯 Python DVB-S2 R=5/6 硬判决实现 | 通用且可审计；没有 C 库时可用，处理速度较慢。 |
| `c_accel` | `c_ldpc_accel.c` 编译出的 ctypes 动态库；载入前按 `resources/SOURCES.json` 校验 SHA-256 | 有匹配本机动态库时使用。当前入库的是 Linux x86-64 `libc_ldpc.so`，没有 Windows `c_ldpc.dll`。 |
| `external` | `resources/R5_6_LDPC_hard_decoder.exe`，并使用配套 `.pchk`、置换表和 3 个 MinGW DLL | 只适用于 Windows；显式选择后运行外部 EXE。 |
| `auto` | `c_accel` 优先，否则 `native` | 推荐作为默认。Windows 缺少 `c_ldpc.dll` 时会在 GUI 日志或 Python warning 中明确提示，实际 backend 名称标为 `native (Windows c_accel unavailable)`。 |

Linux 上如需重建 C 加速库，在仓库根目录执行：

```bash
bash clients/python/build_c_accel.sh
```

该脚本会用 GCC 重建 `resources/libc_ldpc.so`，并同步更新其 `SOURCES.json` 哈希。不要把 Linux `.so` 打进 Windows exe；当前仓库没有经验证的 Windows C DLL 构建方法。

## 5. 数据集与参数口径

- `read_bps` 仅接受 150 或 250。SE150 每条读段在线占 40 B，SE250 占 64 B。客户端会先读取板端 CAPS；请求几何、协议版本、容量必须与板端能力一致，否则不会继续发送任务。
- 当前 BKB220 发布配置是 SE150。客户端虽然支持生成 SE250 CONFIG，但这不表示当前板端 bitstream 支持 SE250；只有匹配的 SE250 板端实现才可运行。
- 默认 `score_min = floor(0.45 × read_bps)`：SE150 为 67，SE250 为 112。可显式用 CLI `--score-min N` 或 GUI“分数阈值”覆盖。该阈值表示板端比对门限，变更它会改变接受读段的条件。
- 默认 `orient=both`，每条源 read 会形成正向和反向互补两个方向；`forward` 仅用于对照实验。CONFIG 的 `total_reads` 是展开方向后的发送条数，并按协议帧大小对齐。
- 仓库数据集位于 `tests/datasets/`。例如 `D1_random_entropy/reads_se150.fastq` 可用于 dry-run；dry-run 只验证主机侧配置，不证明板端连接、回传或 LDPC 正确。

## 6. 常见失败

| 表现 | 含义与检查方向 |
|---|---|
| `Connection refused`、`WinError 10061` 或连接超时 | IP/端口没有服务监听，或网络链路不可达。确认板卡供电、网线、主机网卡地址、板端固件和 TCP 端口；不要把它当作 CONFIG 拒绝。 |
| `板端未按 P3 协议应答 PKT_CAPS` | 对端未返回当前客户端期待的 CAPS 包；检查固件版本与启动状态。 |
| `PKT_CONFIG 被拒绝（码 N）` | 板端明确拒绝任务。码 1=协议版本不支持；2=`read_bps` 不支持；3=几何与比特流不符；4=`symbols` 契约不满足；5=`total_reads` 非法；6=`score_min` 超范围；7=CRC32 不符；8=重复 CONFIG；9=命令顺序非法。先核对 CAPS、读长和板端 bitstream。 |
| `timed out` / 结果等待超时 | `--result-timeout` 是从等待板端结果开始计算的整条 FPGA 处理时限，不是进度轮询间隔。按任务读段规模调大；连接与 CONFIG 阶段另有握手超时。 |
| `LDPC 译码未收敛（…轮后仍有…失败校验）` | 板端回传数据未通过 LDPC 校验。检查输入数据集、几何/阈值、结果文件是否为本次板端回传，并可切换后端复核；更换后端不会修复错误的板端数据。 |
| `LDPC C 动态库 SHA-256 不匹配，拒绝载入` | `.so`/`.dll` 与 `SOURCES.json` 不一致。不要绕过校验；从受信源码运行 `build_c_accel.sh` 刷新库与清单，或恢复一组配对的资源。 |
| GUI 提示 `No module named 'tkinter'` | Python 环境未安装 Tcl/Tk。Linux 安装 `python3-tk`；Windows 使用带 Tcl/Tk 的 Python 安装。 |

## 7. Windows exe 打包

实际打包必须在 Windows 上执行。PyInstaller 的目标平台由运行它的系统决定；在 Linux 上生成的不是 Windows exe。本目录的 `gui_app.spec` 已按 spec 文件所在位置解析资源路径，打包数据包含 Windows 外部译码器和运行时 DLL，不含 Linux `libc_ldpc.so`。当前包的 `auto` 将提示 Windows C 加速 DLL 缺失并使用 `native`。

在 Windows PowerShell 中从 `clients/python` 执行：

```powershell
cd <仓库路径>\clients\python
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m PyInstaller --clean --noconfirm gui_app.spec
```

按当前 spec 的单文件 `EXE` 结构，输出为 `dist\gui_app.exe`。交付前在 Windows 上启动 exe，确认主窗口出现、资源可读取；若用 `external`，再用有效板端回传文件执行“仅重跑 LDPC 译码”，确认能生成图像。`--clean` 和 `--noconfirm` 的作用以及从 `.spec` 构建的命令格式见 [PyInstaller 官方使用说明](https://pyinstaller.org/en/stable/usage.html)。本轮没有运行 PyInstaller，也没有产出 Windows exe。
