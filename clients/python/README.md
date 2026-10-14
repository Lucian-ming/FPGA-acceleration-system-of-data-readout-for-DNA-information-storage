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

选择水印、FASTQ/纯文本读段和结果路径，确认板端 IP/端口、几何、阈值、读段数及方向后启动任务。载荷字节数可留空或填写 1..6750 的整数。留空时按 JPEG EOI 截断；其他媒体或需要精确长度的载荷应填写实际字节数。客户端会识别常见图像、音频、视频和 UTF-8 文本格式，无法识别时标为二进制；识别只用于展示和打开方式，不会改变载荷字节。

板端返回结果后，客户端检查全部 LDPC 校验行。全零时提取信息位并保存载荷；任一行非零时显示失败及非零行数，不生成一个“补救”译码结果。对已有结果重新检查也使用同一校验规则。

## 3. 命令行运行

first.py 负责配置并运行板端任务，将板端回传的 64,800 个结果位保存到 --output；POST 完成后调用 verify_board_result 校验并提取载荷。--input-bytes 指定载荷长度，范围为 1..6750；非 JPEG 载荷应填写准确长度。JPEG 可省略该参数，沿用 EOI 截断。--dry-run 只检查输入并打印 CONFIG，不连接板端：

```bash
python3 clients/python/first.py \
  --watermark tests/datasets/common/watermark.txt \
  --reads tests/datasets/D1_random_entropy/reads_se150.fastq \
  --limit 64 --read-bps 150 --dry-run
```

本仓库环境实际运行了该命令：输出 CONFIG 为 44 B，read_bps=150、total_reads=128、score_min=67；传输统计的上行和下行均为 0，说明 dry-run 没有连接板端。--limit 64 是 64 条源读段；默认 orient=both 会按正向和反向互补展开为 128 条线上记录。

连接板端的示例：

```bash
python3 clients/python/first.py \
  --ip <板端IP> --port 7 \
  --watermark <水印文件> --reads <FASTQ或纯文本读段文件> \
  --output <本轮结果文件> --read-bps 150 --orient both \
  --result-timeout 180 --input-bytes <载荷字节数>
```

JPEG 可省略最后的 --input-bytes；其他格式传入真实载荷长度。Windows 可将 python3 换成 py，并使用 PowerShell 路径格式。输入格式默认 auto，也可指定 --format fastq 或 --format plain。--total-reads N 表示要求恰好处理 N 条源读段；--limit N 表示最多处理 N 条源读段。每轮应使用不同的 --output 路径保留结果。

## 4. 板端 LDPC 校验与载荷类型

PC 加载校验矩阵和置换表，对板端回传的 64,800 位结果解交织并计算 syndrome：

- 全部校验行异或为零：板端 LDPC 已收敛，客户端提取信息位并输出载荷。
- 存在非零校验行：抛出 BoardCodeRejected，本次任务失败。PC 端不调用 native_ldpc.hard_decode、c_ldpc 或外部 EXE 重译。

载荷处理按原始字节进行，不执行媒体解码或格式转换：

| 类型 | 处理方式 |
|---|---|
| JPEG 图像 | 可省略字节数，按 JPEG EOI 标记截断；若已知精确长度，也可显式填写。 |
| 其他图像 | 填写文件的准确字节数，避免按 JPEG 标记截断。 |
| 音频、视频 | 填写准确字节数；校验后保存提取的原始载荷。 |
| 文本 | 填写准确字节数；输出保留原始编码字节，不自动改写编码或换行。 |
| 二进制 | 填写准确字节数；输出原始字节，不做内容转换。 |

信息区最多提供 54,000 bit，即 6,750 B，因此 input_bytes 必须在 1..6750 范围内，且载荷长度不能超过可用信息位。

## 5. 数据集与参数口径

- read_bps 仅接受 150 或 250。SE150 每条读段在线占 40 B，SE250 占 64 B。客户端先读取板端 CAPS；请求几何、协议版本或容量不匹配时会停止任务。
- 当前 BKB220 发布配置是 SE150。客户端可以生成 SE250 CONFIG，但只有匹配的 SE250 板端实现才能运行。
- 默认 score_min = floor(0.45 × read_bps)：SE150 为 67，SE250 为 112。可用 CLI --score-min N 或 GUI“分数阈值”覆盖。该阈值改变板端接受读段的条件。
- 默认 orient=both，每条源 read 会形成正向和反向互补两个方向；forward 仅用于对照实验。CONFIG 的 total_reads 是展开方向后的发送条数。
- 仓库数据集位于 tests/datasets/。dry-run 只验证主机侧输入和配置，不证明板端连接、回传或 LDPC 正确。

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

Windows exe 必须在 Windows 上用 PyInstaller 构建；Linux/WSL 上运行 PyInstaller 会生成 Linux 程序。gui_app.spec 会打包运行时需要的校验矩阵 dvb_s2_r5_6.pchk 和置换表 permutation64800，不打包历史外部译码器 EXE、MinGW DLL 或 Linux libc_ldpc.so。

在 Windows PowerShell 中从仓库根目录执行：

```powershell
Set-Location "<仓库路径>\clients\python"
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm gui_app.spec
```

成功后单文件程序位于 clients\python\dist\gui_app.exe。构建后在 Windows 启动程序，确认资源可加载、成功校验时可提取载荷，非零 syndrome 会报告失败。本轮没有在 Windows 执行打包，也没有生成或验收 exe。
