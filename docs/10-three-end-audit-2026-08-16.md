# 10 · 三端代码审查与可维护性重构日志（2026-08-16）

## 回退基线

- 稳定基线：`main@81986bc`（P3 任务配置化完成；全量回归 8 项全过）
- 工作分支：`refactor/three-end-audit-20260816`
- 总体回退（仅在明确要放弃本分支时）：切回 `main`；不要重置 `data/`、`archive/` 或 XSA。
- 单批回退：每节记录对应提交号，使用 `git revert <commit>`，避免破坏历史。

## 原则

1. 先修真 bug，再做解耦；每批保持全量回归可跑。
2. PS / 上位机 / PL 分批提交，禁止一个跨三端的大提交。
3. 改协议/寄存器/数据格式先更新 `02-data-contract.md` 或 `05-interfaces.md`。
4. 所有行为变更在 `03-status.md` 留证据；历史问题不静默删除。
5. `data/R0.83_data/`、`archive/`、两份 XSA 保持只读。

## 批次计划与状态

| 批次 | 范围 | 计划 | 判据 | 提交 / 回退 |
| --- | --- | --- | --- | --- |
| R1 | PS 协议与 Voter 控制 | 已完成：修复失败 ACK、分帧原子发送、超大 payload 恢复；合并 Voter 配置；清理死函数 | `run_sim.sh` 8/8；xsct ELF 941,888 B | `80f53b9` / `git revert 80f53b9` |
| R2 | 上位机 | 已完成：提取 TaskSpec/协议模块；严格水印/读段/结果校验；LDPC 默认原生 | 12 项单测；全量 9/9；dry-run/auto LDPC 通过 | `44f00eb` / `git revert 44f00eb` |
| R3 | PL | 已完成：修复 DNA 入口丢数、三核 AXI-Lite 独立握手、尾批超时位宽；清理死寄存器/乱码注释并标记遗留 RTL | RTL 全量回归 + Voter 综合 | 待提交（功能已验证，提交号待回填） |
| R4 | 文档与收尾 | 同步 03/05/06/09/README；全量回归、ELF、综合复跑 | 全绿 | 待提交 |

## R1 审查发现（已提交 `80f53b9`）

### 已确认真 bug

1. **PS-1：WM/BATCH 失败仍无条件回 OK**
   `process_complete_packet()` 调用 `process_watermark/process_batch` 后无论返回结果都发
   `WM_OK/BATCH_OK`；而两个函数内部失败时还可能自己发 `PKT_ERROR`。客户端会读到
   `ERROR+OK` 两个字节，第二个字节污染下一次 ACK，连接协议失步。
   修复：`process_complete_packet()` 统一依据返回值发送一次 ACK；BATCH 不再隐式触发 POST。
   证据：`sw/app/echo.c`（当前 `process_complete_packet/process_watermark/process_batch`）。

2. **PS-2：`send_framed_pkt()` 不是事务安全的**
   header `tcp_write` 成功而 payload `tcp_write` 因 `ERR_MEM` 失败时，循环重试会再次排队
   header，形成重复/嵌套包头；函数无返回值，上层也无法报告发送失败。
   修复：包头与负载合并为一次 `tcp_write(TCP_WRITE_FLAG_COPY)`，返回 `err_t` 并由调用方记录失败。
   证据：`sw/app/echo.c`（当前 `send_framed_pkt`）。

3. **PS-3：接收超大 payload 可永久卡住连接**
   包头声明 `payload_len > tcp_recv_buffer` 时，`recv_callback()` 一直等待不可能装下的包；
   后续收到数据才以 `ERR_MEM` 返回但不清缓冲、不关闭连接，状态无法恢复。
   修复：头部解析后立即拒绝超过 `sizeof(tcp_recv_buffer)-8` 的声明，清理回调、发送错误并关闭连接；
   缓冲溢出走同一恢复路径。证据：`sw/app/echo.c`（当前 `recv_callback`）。

### 结构问题

4. **PS-S1：Voter 寄存器配置/回读验证重复两遍**
   `PIPE_VOTER_PREP` 与 `PIPE_VOTER_START` 都写同一组 IN/OUT/TOTAL/SCORE 寄存器并回读；
   两份代码曾经出现 `IN_BEATS` 语义不一致（一个写 `reads*6`、一个写 `reads`），虽然
   硬件当前忽略 `IN_BEATS`，但复制分支会继续制造维护漂移。已合并到 `voter_configure_and_verify()`，统一按
   `records*6` 写入并逐项回读。

5. **PS-S2：`echo.c` 仍约 2,100 行，混合 DMA、三级流水线、TCP 协议、调试输出**
   本批先做低风险函数解耦和死代码清理；跨文件拆分（`protocol.c/pipeline_*.c`）需要调整
   Vitis 导入/全局状态边界，留到 helper 行为稳定后再分批，避免一次性扩大回归面。

### R1 验证

- `bash tools/run_sim.sh`：通过 8 项，失败 0 项。
- `env DISPLAY=:0 /tools/Xilinx/Vitis/2022.2/bin/xsct sw/scripts/create_vitis.tcl`：成功；
  `dna_lwip_app.elf` 941,888 B，text 144,519 / data 3,148 / bss 3,266,624。
- `git diff --check`：通过。

## R2 上位机模块化与严格校验（已提交 `44f00eb`）

### 行为修复

1. 水印不再 `[:81000]` 静默截断；只读取一次，位数必须等于 `TaskSpec.watermark_bits`。
2. 读段文件提前结束、非法 batch/limit、超容量全部抛错；`iter_read_batches()` 不再只打印 WARN。
3. 裸 ACK 收到 `PKT_ERROR` 时报告具体操作；`PKT_RESULT` 必须精确为 8,100 B。
4. `--no-post` 上传结束后直接返回，不再等待一个不会到来的结果。
5. LDPC `auto` 固定选择 native；`external` 仅显式调用，DLL 缺失提前失败。

### 模块边界

- `task_protocol.py`：`TaskSpec` / `TaskCaps` / CONFIG CRC。
- `protocol.py`：TCP 包、ACK、CAPS/CONFIG 与网络统计。
- `native_ldpc.py`：GUI 与 `tools/ldpc_decode.py` 共用的译码核心。
- `first.py`：文件编码和会话编排；`gui_app.py` 继续只依赖公共入口。

### R2 验证

- Python `unittest`：12 项通过。
- `bash tools/run_sim.sh`：通过 9 项，失败 0 项。
- R0.83 `--dry-run`：CONFIG CRC `0xD5BC6633`。
- `ldpc_pipeline(auto)`：5 轮收敛、54,000 bit，JPEG SHA-256 `fcd0cf90...b6b1f2c3`。
- `py_compile` / `git diff --check`：通过。
- 当前系统未安装 `tkinter`，GUI 窗口未做运行时启动；`gui_app.py` 已通过 `py_compile`，
  其调用的 `run_client()` / `run_ldpc_decoder(auto)` 已由上述单元与集成判据覆盖。

## R3 PL 审查、流控与控制口修复

### 已确认真 bug

1. **PL-1：DNA FIFO 满时继续向 DMA 宣告 READY，静默丢读段。**
   `eng_busy=1` 时原逻辑无条件 `TREADY=1`，而 1,024 深度 FIFO 在满时忽略写入，
   `in_count` 仍继续增长。`tb_dna_ingress.v` 修复前复现为 11,000 拍全部被接受；
   现改为正常读段仅在 `~in_full` 时握手，并按真实 FIFO 写入更新计数。
2. **PL-2：DNA/Voter/Decoder 的生产 AXI-Lite 从机不支持 AW/W 独立握手。**
   新增 DNA 专项 TB，并把 Stage2/Stage3 BFM 改为先 AW 后 W；修复前均在首笔配置事务
   无 B 响应。三个从机现各保存一个地址/数据槽，凑齐后提交一次写入。
3. **PL-3：DNA partial-batch 超时永远不可达。**
   16 bit `idle_counter` 无法达到 100,000；扩为 17 bit，并由 ingress TB 钉死阈值。

### 低风险清理

- 删除 Voter 中只写不读的 `accumulated_vote`、`current_score`、
  `pre_calc_is_upper`、`pre_calc_bit_idx`；核心地址与投票流水线未改。
- `srpe_batch.v` 的不可逆乱码注释重写为 UTF-8 中文，RTL 逻辑不变。
- 由三个 `component.xml` 文件集确认并标记为 `DEPRECATED`：`srpe.v`、
  `differential_voter_v1_0_M00_AXI.v`、`differential_voter_v1_0_S00_AXI.v`、
  `five_to_four_decoder.v`。历史文件保留，不接回生产路径。
- `bd.tcl` 把 DNA 三个时钟端口以及 Voter/Decoder 的 S00/M00 时钟全部连接到
  `clk_wiz_0/clk_out1`；当前构建不存在跨时钟数据通路。顶层接口仍隐含同钟约束，
  不在本批贸然引入 CDC 重构。
- `tools/run_sim.sh` 现在同时检查进程退出码、`FATAL:` 与显式 `PASS`；修复了
  Icarus 在 Verilog-2005 模式下 `$fatal(1)` 仍返回 0 导致的假绿摘要。

### R3 验证

- `bash tools/run_sim.sh ingress`：读段组装、1,024 深度背压、计数一致、100,000 超时阈值通过。
- `bash tools/run_sim.sh dna_axil`：AW→W、W→AW、`WSTRB` 通过。
- `bash tools/run_sim.sh axi`：1,013 拍 / 64,800 bit 与 Stage3 黄金向量逐位相同。
- `bash tools/run_sim.sh stage2`：阈值 67 两轮 + 阈值 0 一轮，均为 1,266 拍 / 81,000 bit 逐位相同。
- 全量回归、Voter 综合/时序与功能提交号在 R3 收尾后回填。
