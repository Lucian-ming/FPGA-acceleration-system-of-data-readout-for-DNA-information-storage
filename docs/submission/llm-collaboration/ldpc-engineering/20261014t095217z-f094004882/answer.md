> 脱敏副本，原件 `20261014T095217Z-f094004882/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

## 交付

已实现 AXI4-Lite LDPC IP，并接入整机 BD。`ldpc-axi` 看板目前标为阻塞：打包门禁要求给新 HDL 加回归覆盖，但本任务禁止修改 `tools/`。

新增文件：

- [component.xml](<仓库根目录>/hw/ip/ldpc_decoder_1_0/component.xml)
- [ldpc_decoder_v1_0.v](<仓库根目录>/hw/ip/ldpc_decoder_1_0/hdl/ldpc_decoder_v1_0.v)
- [ldpc_decoder_p1.v](<仓库根目录>/hw/ip/ldpc_decoder_1_0/hdl/ldpc_decoder_p1.v)，与 `hw/experimental/` 原文件逐字节相同
- [ldpc_decoder_v1_0.tcl](<仓库根目录>/hw/ip/ldpc_decoder_1_0/xgui/ldpc_decoder_v1_0.tcl)
- ROM 数据副本：[bt_col_by_res.hex](<仓库根目录>/hw/ip/ldpc_decoder_1_0/data/bt_col_by_res.hex)、[bt_res_off.hex](<仓库根目录>/hw/ip/ldpc_decoder_1_0/data/bt_res_off.hex)

修改了 [bd.tcl](<仓库根目录>/hw/scripts/bd.tcl) 和由工具生成的 [PACKAGED_VARIANTS.txt](<仓库根目录>/hw/ip/PACKAGED_VARIANTS.txt)。AXI-Lite 互联扩为 5 个从口，新 IP 接 `M04_AXI`、`clk_wiz_0/clk_out1` 和 `rst_ps/peripheral_aresetn`。原四个地址保持不变，新地址为 `0x43C30000`，范围 `0x00010000`。

## 寄存器映射

| 偏移 | 读写 | 语义 |
| --- | --- | --- |
| `0x00` | R/W | 控制：bit 0 启动；bit 1 复位译码器并清除 done 状态。 |
| `0x04` | R | 状态：bit 0 busy、bit 1 sticky done、bit 2 converged、bit 3 error、bit 4 装载中、bit 5 读回中；bit `[15:8]` 为有符号迭代轮数。 |
| `0x08` | R/W | 装载字地址，合法范围 `0..2024`。 |
| `0x0C` | R/W | 装载字数据；完整字节使能写入会展开为 32 次核心写入，AXI 写响应在装载完成后返回；读取可查看最近写入值。 |
| `0x10` | R/W | 结果字地址，合法范围 `0..2024`。 |
| `0x14` | R | 触发同步读回并拼成 32 位结果字；核心忙时返回 `SLVERR`。 |

## 位序

客户端收到结果包后，[`first.py`](<<仓库根目录>/clients/python/first.py>) 调用 [`fast_unpack_result`](<<仓库根目录>/clients/python/fast_readout.py>)；该函数使用 `np.unpackbits(raw, bitorder="little")`。因此结果缓冲是 **每字节 LSB-first**：先取 byte 0 的 bit 0 到 bit 7，再取 byte 1。

包装器将 `load_word_data_q[bit_index]` 依次送入核心，并将每个核心结果位放入结果字的同一 bit 位置，保持这一路序。`native_ldpc.py::bits_to_bytes` 的 MSB-first 是另一条载荷输出打包路径，不是 Stage3 结果缓冲的解包规则。

## 检查结果与未完成项

- 通过：`iverilog -g2012 -Wall -s ldpc_decoder_v1_0 -tnull`；BD Tcl `info complete`；IP-XACT XML 解析、端口与文件映射检查；核心和 ROM 副本的逐字节比较。
- 通过：`tools/check_repo_hygiene.sh`。
- 已执行 `tools/check_ip_packaging.sh --write-manifest` 生成清单。常规 `tools/check_ip_packaging.sh` **未通过**：仅新 IP 的 `ldpc_decoder_p1.v` 和 `ldpc_decoder_v1_0.v` 缺少 `tools/run_sim.sh` 回归覆盖；其余打包检查通过。未修改 `tools/`，所以此门禁待主会话获准补回归后重跑。
- 未运行 Vivado、XSim 或板测。IP Catalog 对自定义 ROM 参数、整机 BD 校验和布线时序仍需主会话验证。
- PS 固件尚未驱动该 IP，也未实现“收敛后读回覆盖缓冲、不收敛则保留缓冲”的流程；本任务按约束只交付 RTL/IP/BD。

整机实现的主要风险是 L4 译码器的 `+0.444 ns` 时序余量来自 OOC、不是整机证据。主会话应检查整机实现的 WNS/WHS 和失败端点，并确认两个 ROM 路径可读。板端还应确认完整装载 2,025 个字、收敛后回写 8,100 B，并用既有客户端解包后检查原 SHA；不收敛时确认缓冲逐字节未变。
