# 上位机客户端使用说明

本目录提供 tkinter GUI 与命令行板端客户端。客户端负责读段解析、任务配置、TCP 上传/回传和结果校验。LDPC 译码全部由 FPGA 片上完成；PC 只检查板端码字的 syndrome 并提取载荷。校验不通过就是本次任务失败，PC 不会再次译码或兜底。这些说明不代表板卡已经通过验收。

## 1. 环境与依赖

- Python 3.8 或更新版本。
- Python 依赖：numpy、Pillow，通过本目录的 requirements.txt 安装。
- GUI 需要 Tcl/Tk。Windows 安装 Python 时需包含 Tcl/Tk；Debian/Ubuntu/WSL 可安装与 Python 对应的 python3-tk。

在仓库根目录执行：

```bash
python3 -m venv clients/python/.venv
source clients/python/.venv/bin/activate
python -m pip install -r clients/python/requirements.txt
```

Windows PowerShell：

```powershell
py -m venv clients\python\.venv
.\clients\python\.venv\Scripts\python.exe -m pip install -r clients\python\requirements.txt
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

选择水印、FASTQ/纯文本读段和结果路径，确认板端 IP/端口、几何、阈值、读段数及方向后启动任务。载荷字节数可填写 1..6750 的整数，也可留空：显式填写时精确保留指定字节数（包括末尾零）；留空时客户端按魔数推断格式和长度。若格式标记或长度字段无法确定边界，客户端会按去尾零估算，并显示格式、建议扩展名、长度确定性和判定依据；不确定时会明确提示“载荷长度靠去尾零推测，可能不准”。推断结果可能不准确；已知准确长度时应显式填写。

板端返回结果后，客户端检查全部 LDPC 校验行。全零时提取信息位并保存载荷；任一行非零时显示失败及非零行数，不生成一个“补救”译码结果。对已有结果重新检查也使用同一校验规则。

## 3. 命令行运行

first.py 负责配置并运行板端任务，将板端回传的 64,800 个结果位保存到 --output；POST 完成后调用 verify_board_result 校验并提取载荷。--input-bytes 指定精确载荷长度，范围为 1..6750；省略时客户端按魔数推断格式与长度，并在不能确定时说明估算依据。--dry-run 只检查输入并打印 CONFIG，不连接板端：

```bash
python3 clients/python/first.py \
  --watermark ../data/01_peppers_baseline/watermark.txt \
  --reads ../data/01_peppers_baseline/read.fastq \
  --limit 64 --read-bps 150 --dry-run
```

该命令在开发阶段实际运行过（当时用的基准数据集不随包；包内任一用例目录可直接替代）：输出 CONFIG 为 44 B，read_bps=150、total_reads=128、score_min=67；传输统计的上行和下行均为 0，说明 dry-run 没有连接板端。--limit 64 是 64 条源读段；默认 orient=both 会按正向和反向互补展开为 128 条线上记录。

连接板端的示例：

```bash
python3 clients/python/first.py \
  --ip <板端IP> --port 7 \
  --watermark <水印文件> --reads <FASTQ或纯文本读段文件> \
  --output <本轮结果文件> --read-bps 150 --orient both \
  --result-timeout 180 --input-bytes <载荷字节数>
```

--input-bytes 可省略；显式提供时按给定长度逐字节截取，省略时使用载荷推断。Windows 可将 python3 换成 py，并使用 PowerShell 路径格式。输入格式默认 auto，也可指定 --format fastq 或 --format plain。--total-reads N 表示要求恰好处理 N 条源读段；--limit N 表示最多处理 N 条源读段。每轮应使用不同的 --output 路径保留结果。

## 4. 板端 LDPC 校验与载荷类型

PC 加载校验矩阵和置换表，对板端回传的 64,800 位结果解交织并计算 syndrome：

- 全部校验行异或为零：板端 LDPC 已收敛，客户端提取信息位并输出载荷。
- 存在非零校验行：抛出 BoardCodeRejected，本次任务失败。PC 端不调用 native_ldpc.hard_decode、c_ldpc 或外部 EXE 重译。

载荷按原始字节保存，不执行媒体解码或格式转换。显式给出 `input_bytes` 时，严格保留指定长度。留空时按格式魔数识别，并按可用的自描述边界确定长度；若边界缺失或无法识别，则通过去除尾部零字节估算长度，此时长度不确定，不能当成可靠判定：

| 类型 | 处理方式 |
|---|---|
| JPEG、PNG、GIF | 分别尝试用 EOI、IEND、Trailer 标记确定长度；标记缺失时改为去尾零估算并标为不确定。 |
| BMP、RIFF WAVE/AVI | 尝试使用文件长度字段；字段无效时改为去尾零估算并标为不确定。 |
| PDF、ZIP | 尝试使用 EOF、EOCD 结束结构；结构缺失或不完整时改为去尾零估算并标为不确定。 |
| UTF-8 文本、任意二进制及其他未支持自描述边界的格式 | 只能去除尾部零字节估算长度，并标为不确定；末尾零也可能是有效数据。 |

推断格式和长度不保证正确；格式后缀是建议值。GUI 会显示推断到的格式、后缀、长度确定性与依据。若 `length_certain` 为假，会显示“载荷长度靠去尾零推测，可能不准”。要精确保留包含尾零的数据，请显式填写真实字节数。

信息区最多提供 54,000 bit，即 6,750 B，因此 input_bytes 必须在 1..6750 范围内，且载荷长度不能超过可用信息位。

## 5. 数据集与参数口径

- read_bps 仅接受 150 或 250。SE150 每条读段在线占 40 B，SE250 占 64 B。客户端先读取板端 CAPS；请求几何、协议版本或容量不匹配时会停止任务。
- 当前 BKB220 发布配置是 SE150。客户端可以生成 SE250 CONFIG，但只有匹配的 SE250 板端实现才能运行。
- 默认 score_min = floor(0.45 × read_bps)：SE150 为 67，SE250 为 112。可用 CLI --score-min N 或 GUI“分数阈值”覆盖。该阈值改变板端接受读段的条件。
- 默认 orient=both，每条源 read 会形成正向和反向互补两个方向；forward 仅用于对照实验。CONFIG 的 total_reads 是展开方向后的发送条数。
- 包内测试用例平铺在 `../data/<NN>_<资产>_<baseline|challenge>/`（相对 `src/`），每例含 `read.fastq` 与 `watermark.txt`。dry-run 只验证主机侧输入和配置，不证明板端连接、回传或 LDPC 正确。

## 6. 常见失败

| 表现 | 含义与检查方向 |
|---|---|
| Connection refused、WinError 10061 或连接超时 | IP/端口没有服务监听，或网络链路不可达。检查板卡供电、网线、主机网卡地址、固件和 TCP 端口。 |
| 板端未按 P3 协议应答 PKT_CAPS | 对端未返回当前客户端期待的 CAPS 包；检查固件版本与启动状态。 |
| PKT_CONFIG 被拒绝（码 N） | 板端拒绝任务。码 1=协议版本不支持；2=read_bps 不支持；3=几何与比特流不符；4=symbols 契约不满足；5=total_reads 非法；6=score_min 超范围；7=CRC32 不符；8=重复 CONFIG；9=命令顺序非法。 |
| 等待结果超时 | --result-timeout 限制板端处理和结果回传的总时长；按任务规模调整。 |
| BoardCodeRejected，校验行非零 | 板端码字没有通过片上 LDPC 校验。本次任务失败；核对输入数据集、几何、阈值、板端 bitstream 和结果文件是否属于同一轮。客户端不会重译兜底。 |
| input_bytes 参数错误 | 使用 1..6750 的整数，并确认载荷长度不超过 54,000 个信息位。 |
| GUI 提示缺少 tkinter | Python 环境未安装 Tcl/Tk。Linux 安装 python3-tk；Windows 使用包含 Tcl/Tk 的 Python 安装。 |

## 7. Windows exe 打包

Windows exe 必须在 Windows 上用 PyInstaller 构建；Linux/WSL 上运行 PyInstaller 会生成 Linux 程序。gui_app.spec 只打包运行时需要的校验矩阵 dvb_s2_r5_6.pchk 和置换表 permutation64800；历史外部译码器 EXE 与 MinGW DLL 已从包中移除，Linux 的 libc_ldpc.so 也不打包。

在 Windows PowerShell 中从仓库根目录执行：

```powershell
Set-Location "<仓库路径>\clients\python"
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm gui_app.spec
```

成功后单文件程序位于 clients\python\dist\gui_app.exe。随包已附一份用 Windows Python 3.13 + PyInstaller 6.22 按上述步骤打包的 `gui_app.exe`（与本 readme 同目录），已连板跑通 3 组用例。
