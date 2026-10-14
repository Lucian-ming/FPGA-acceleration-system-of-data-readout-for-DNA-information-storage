> 脱敏副本，原件 `20261014T095217Z-f094004882/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

任务（workspace-write，看板名 **ldpc-axi**）：把片上 LDPC 译码器**封装成 AXI4-Lite IP 并接入整机 BD**。**只做 RTL/IP/BD 这一层，不跑 Vivado 构建（构建由 main 跑），不改 PS 固件。**

## 背景（先读）
- 译码器本体：`hw/experimental/ldpc_decoder_p1.v`（p=1 边串行 flooding Min-Sum，**功能已对黄金、时序已收敛**，见 `docs/benchmarks/ldpc-decoder-l4.md`）
- 现有整机 BD：`hw/scripts/bd.tcl`；现有 IP 例子：`hw/ip/desparsification_decoder_1_0/{component.xml,hdl,xgui}`
- 地址图（`bd.tcl` 末尾）：`0x40400000` DMA、`0x43C00000` Stage1、`0x43C10000` 反稀疏化、`0x43C20000` Voter。**新 IP 用 `0x43C30000`**
- **Stage3 输出的 8100 B 就是 64,800 位 LDPC 码字**；主机拿它跑 LDPC 得到载荷
- 判据：`docs/benchmarks/ldpc-decoder-l4.md` 与 `docs/reference/ldpc-architecture-decision-2026-10-14.md`

## 集成分工（已经定好，按此实现）
**板端把码字 LDPC 纠正后写回结果缓冲；协议、结果长度（8100 B）、主机侧流程全部不变。**
- 收敛 → 结果缓冲换成纠正后的 64,800 位；
- **不收敛 → 保持原样不动**（主机侧行为与现在完全相同，仍会报未收敛）。
这样**板端判据 SHA `fcd0cf90…b1f2c3` 的验收方式不变**。

## 你要交付
### (1) AXI4-Lite 包装 IP `hw/ip/ldpc_decoder_1_0/`
含 `component.xml`、`hdl/`（包装模块 + 复用译码器本体）、`xgui/`。参考 `desparsification_decoder_1_0` 的结构与命名风格（vlnv 建议 `xilinx.com:user:ldpc_decoder:1.0`）。
**接口**：一个 AXI4-Lite 从口（S00_AXI），时钟与复位各一根。
**寄存器建议**（具体你定，但要写清地址与语义）：
- 控制（start；复位/清状态）
- **装载**：32 位数据寄存器 + 字地址寄存器。**写数据寄存器即把该 32 位按序推入译码器的 `load_addr/load_bit/load_we`**（译码器是 1 bit/拍，包装里用小 FSM 展开 32 拍）。64,800 位 = 2,025 个字。
- **状态**：busy / done / converged / 迭代轮数
- **读回**：32 位数据寄存器 + 字地址寄存器。读数据寄存器时包装里按 32 拍把 `result_addr/result_bit` 的结果拼成一个字返回。

### (2) 接入 `hw/scripts/bd.tcl`
`create_bd_cell` → 接时钟（`clk_wiz_0/clk_out1`）与复位（`rst_ps/peripheral_aresetn`）→ 接 `ic_lite` → 用 `assign_bd_address -offset 0x43C30000 -range 0x00010000 ... -force`。**保持既有四个地址不动**，且不要依赖自动分配顺序。

### (3) 更新 `hw/ip/PACKAGED_VARIANTS.txt`
它是 `tools/check_ip_packaging.sh --write-manifest` 生成的，**请用该工具重新生成**，不要手改。同时确认 `tools/check_ip_packaging.sh` 与 `tools/check_repo_hygiene.sh` 均通过（后者有「IP 打包目录里不能有非 .v 文件」等检查）。

### (4) ⚠️ **位序必须先查清并写明**
主机把 8100 字节的结果缓冲解释成 64,800 位——**这个位序必须与 `clients/python/` 里现有客户端一致**（去看 `clients/python/first.py` / `ldpc_pipeline.py` / `native_ldpc.py` 是怎么把结果字节转成比特的）。**这是最容易错的一处**：位序反了，纠正后的码字就全是错的，而且板上表现为"LDPC 反而把好结果改坏了"。请在答复里**明确写出你查到的确切位序**（例如"每字节 LSB 先"还是"MSB 先"），以及包装 IP 里对应怎么接。

## 硬约束
- **不要**跑 Vivado 综合/实现/整机构建（main 会跑，避免资源争用）。
- **不要**改 `sw/`、`clients/`、`tools/` 的既有文件、`docs/`；不要动 `hw/ip/` 下**已有**的三个 IP。
- **不要改 `hw/experimental/ldpc_decoder_p1.v` 的逻辑**（要复用就实例化；若必须小改接口，请在答复里显式列出）。
- **不做 Git 写操作**；**不要运行 `tools/verify_repo_binding.sh`**（沙箱内 git 只读，必然失败白跑）。
- 不碰板卡。
- 看板自行登记：`tools/agent_view.sh start/update/done --agent ldpc-axi ...`

## 交付
1. 新增/改动文件清单；
2. **寄存器映射表**（偏移、读写、语义）；
3. **位序结论与依据**（引用你查到的客户端代码位置）；
4. 你做了哪些**静态检查**（如 `iverilog` 语法/详述通过、打包门禁通过）——**明确区分"检查过"与"没跑过"**；
5. 你认为**最容易在整机构建或板端出错的地方**，以及到时候该怎么判。
答复用中文。