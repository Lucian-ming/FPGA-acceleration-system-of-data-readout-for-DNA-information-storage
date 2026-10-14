> 脱敏副本，原件 `20261013T123951Z-bd9362bbfa/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

**产出：本次最终答复；未创建或修改文件。** 检查时工作树在 `exp/stage1-k2`，`git status` 干净。以下把实验分支的新问题与历史遗留分开。

## 1. 高严重度

### K=2 已可配置，但没有对应的功能正确性判据

- **文件 → 符号：** [`srpe_batch_pway.v`](<仓库根目录>/hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_pway.v) → `srpe_batch_pway::BASES_PER_CYCLE`；[`Dna_accelerator_core_v1_0.v`](<仓库根目录>/hw/ip/Dna_accelerator_core_1_0/hdl/Dna_accelerator_core_v1_0.v) → `g_stage1_pway`；[`run_sim.sh`](<仓库根目录><本机路径>) → `stage1_pway`。
- **问题：** BD Tcl 已能把 `C_STAGE1_BASES_PER_CYCLE` 传到 P-way 实现；但回归只设置 `CFG_P_WAYS` 和 `CFG_PIPE_TREE`，测试实例的 `BASES_PER_CYCLE` 仍取默认值 1。没有 K=2 的分数、位置和输出顺序比对。
- **后果：** OOC 布线结果不能证明 K=2 的算法结果正确。若启用 K=2，目前缺少可复现的功能正确性判据，可能把 Stage1 错算误认为有效配置。**这不是已证实的错算。**
- **建议：** 给 TB 增加 `BASES_PER_CYCLE` 配置，并将 K=2（以及若计划支持则 K=4）加入回归；覆盖区域和滑窗边界、末组不足 K 个碱基、并列选优，并与独立 oracle 比对。
- **严重度：** 高。
- **归类：** 本轮 K=2 引入。

## 2. 中严重度

### K 参数没有完整接入 GUI 和取值约束

- **文件 → 符号：** [`component.xml`](<仓库根目录>/hw/ip/Dna_accelerator_core_1_0/component.xml) → `C_STAGE1_BASES_PER_CYCLE`；`xgui/Dna_accelerator_core_v1_0.tcl` → 参数显示与验证过程；[`bd.tcl`](<仓库根目录>/hw/scripts/bd.tcl) → `stage1_bases_per_cycle`；[`srpe_batch_pway.v`](<仓库根目录>/hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_pway.v) → `BASES_PER_CYCLE`。
- **问题：** XML 和 BD Tcl 已接入该参数，但 XGUI 只列出 P-ways 和流水树参数，没有该参数的显示、更新或验证过程。参数也没有限定范围；RTL 对其做除法、取模并据此定义数组，取 0 会导致无效展开。
- **后果：** GUI 用户无法可靠配置新参数，未经约束的值可能导致构建失败；现有静态门禁也没有检查这个新参数的 GUI 和取值约束。
- **建议：** 明确支持值（例如只允许已验证的 1、2、4），并在 XGUI、BD Tcl、RTL 静态检查中统一验证。
- **严重度：** 中。
- **归类：** 本轮 K=2 引入。

### 打包门禁仍要求生产算法与 K2 前的实验版本完全相同

- **文件 → 符号：** [`check_ip_packaging.sh`](<仓库根目录><本机路径>) → Stage1 `algorithm()` 比较；[`srpe_batch_pway.v`](<仓库根目录>/hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_pway.v) 与 `hw/experimental/srpe_batch_pway.v`。
- **问题：** 门禁会剥除注释和少数默认值后，断言生产 P-way 算法等于实验目录中的旧版本。我用同一套摘取逻辑只读比较，结果为不相等；K2 的 bank 和状态机改动已改变算法体。
- **后果：** `run_sim.sh` 的完整回归和生产回归入口先执行该门禁，因此这个实验分支会被旧迁移契约拒绝。若门禁保持红色是有意的保护措施，需明确记录这个边界；若要在本分支继续回归，就需要为新算法建立新的比较和验证契约。
- **建议：** 保留旧版作为 K=1 参考，明确登记 K2 的算法变更，并在有 K2 功能回归后更新门禁；不要仅删除算法一致性检查。
- **严重度：** 中。
- **归类：** 本轮 K=2 引入，是否有意保持门禁拒绝待确认。

### Decoder 拍数分散在多处硬编码，新增 profile 容易漂移

- **文件 → 符号：** [`echo.h`](<仓库根目录>/sw/app/echo.h) → `DECODER_INPUT_BEATS` / `DECODER_OUTPUT_BEATS`；[`reg_timing.c`](<仓库根目录>/sw/app/reg_timing.c) → `decoder_configure_default`；[`stage3_decoder.c`](<仓库根目录>/sw/app/stage3_decoder.c) → `pipeline_step_stage3`。
- **问题：** `stage3_decoder.c` 取消定义共享几何宏后又重算；其实际配置路径还使用本地的 `1266` / `1013` 常量。`reg_timing.c` 也另有同值常量。
- **后果：** 当前 SE150 数值一致，但更换输入或输出几何时，缓存范围、寄存器拍数、轮询和回读长度可能由不同常量控制，产生截断或等待长度不一致。
- **建议：** 以单一几何定义派生输入/输出 beat 数，让配置、轮询、缓存和回读都使用同一来源。
- **严重度：** 中；当前 SE150 未发现数值不一致。
- **归类：** 历史遗留。

### FASTQ 解析会静默忽略或改写异常输入

- **文件 → 符号：** [`first.py`](<仓库根目录>/clients/python/first.py) → `inspect_reads_file` / `analyze_reads_file`；[`fast_readout.py`](<仓库根目录>/clients/python/fast_readout.py) → `fast_iter_source_seqs` / `LUT_HI` / `LUT_LO`。
- **问题：** 解析器以 `errors="ignore"` 读取；FASTQ 记录只按四行读取，不核对 header、`+` 行或序列与质量长度。遇到不完整记录时会直接停止。查表还会把未知碱基字符编码成零位平面。
- **后果：** 损坏或格式错误的输入可能被静默截短或改写成看似有效的读段，客户端仍可继续上传，结果不再对应原输入。
- **建议：** 对完整 FASTQ 记录和可接受碱基（明确允许 `N`）进行校验；遇到异常时报记录序号和原因，不要静默跳过尾部或字符。
- **严重度：** 中；只在异常输入时触发，未发现当前合法输入的错误。
- **归类：** 历史遗留。

## 3. 低严重度 / 可读性

### 现行注释仍用文件行号定位代码

- **文件 → 符号：** [`stage1_dna.c`](<仓库根目录>/sw/app/stage1_dna.c) → `pipeline_step_stage1` 的时钟与轮询说明；[`task_protocol.py`](<仓库根目录>/clients/python/task_protocol.py) → `read_size_bytes` 等注释；[`make_golden.py`](<仓库根目录><本机路径>)、[`run_g3.sh`](<仓库根目录><本机路径>)、`tools/board/g3_wait_ready.py` 的实现说明。
- **问题：** 注释仍含文件加行号的引用；`check_repo_hygiene.sh` 只能确认引用未悬空或越界，不能发现行号仍有效但代码内容已移动。
- **后果：** 维护者可能沿着过期位置定位到错误逻辑。
- **建议：** 改为函数、状态或信号名。
- **严重度：** 低。
- **归类：** 历史遗留。

### FIFO 说明与当前有效延迟互相矛盾

- **文件 → 符号：** [`Dna_accelerator_core_v1_0.v`](<仓库根目录>/hw/ip/Dna_accelerator_core_1_0/hdl/Dna_accelerator_core_v1_0.v) → `eng_cw_vld` 附近的 handshake 注释；[`fifo_sync_sdpram_b64.v`](<仓库根目录>/hw/ip/Dna_accelerator_core_1_0/hdl/fifo_sync_sdpram_b64.v) → `raddr_q` / `dout`。
- **问题：** handshake 标题仍写“一拍后数据有效”，同一逻辑实际用 `in_rd_d2`，旁边的 B26 注释也说明 pop 后要等三拍。
- **后果：** 当前有效逻辑没有因此显示出错，但保留旧标题会诱发后续把采样点改早。
- **建议：** 删除旧的一拍说明，统一写清从 `in_rd` 到 `dout` 稳定的时钟边沿定义。
- **严重度：** 低；属于注释风险，未发现当前采样逻辑错误。
- **归类：** 历史遗留。

### 存在仓库内零调用的辅助函数

- **文件 → 符号：** [`first.py`](<仓库根目录>/clients/python/first.py) → `count_reads_in_file`、`iter_reads`；[`reg_timing.h`](<仓库根目录>/sw/app/reg_timing.h) → `voter_read_status`、`decoder_read_status`。
- **问题：** 全仓精确标识符搜索只命中定义；其中 `count_reads_in_file` 是 `inspect_reads_file` 的包装函数。
- **后果：** 后续修改可能落在仓库内无人调用的实现上；外部调用者情况待确认。
- **建议：** 若不是外部 API，确认后删除；若要保留，增加实际调用或声明其 API 用途。
- **严重度：** 低。
- **归类：** 历史遗留。

## 4. “屎山”风险最高的 3 处

1. **P-way K2 银行化路径**：[`srpe_batch_pway.v`](<仓库根目录>/hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_pway.v) 已可被构建配置启用，但没有 K2 功能判据，参数约束和 GUI 也未补齐。
2. **Stage3 拍数几何**：`echo.h`、`reg_timing.c`、`stage3_decoder.c` 各自保存同一几何的数值，未来改 profile 容易出现互相不一致。
3. **客户端读段解析**：`first.py` 负责计数和格式推断，`fast_readout.py` 负责实际批量读取；异常 FASTQ 没有严格校验，解析链路可能静默丢弃或改写输入。

## 5. 方法与边界

- 检查了仓库卫生规则、当前分支和工作树状态；用标识符搜索核对函数/模块引用、`component.xml` 与 `PACKAGED_VARIANTS.txt`、`tools/README.md` 登记、行号引用、FIFO 延迟注释、寄存器 TB 和 K 参数测试配置。
- `type grep` 返回 `<本机路径>`，不是 shell 函数。`file` 对当前 HDL 文件识别为 UTF-8 或 ASCII；本轮没有用中文 grep 结果判断引用。
- `tools/check_repo_hygiene.sh` **通过**。根目录残留检查无输出；工具均有 README 登记。`bench_align.py` 现在已被 README 和现行文档引用，不再是过去的零引用工具。
- `tb_dec_ddr_restart.v` 已由 `tools/run_xsim.sh` 注册，并包含单次启动与重启写序列场景。当前 `tb_dna_quick.v` 中 AW/WVALID 由 `axil_write` 任务驱动，AGENTS 中“恒为 0”的描述与当前文件不符；该 TB 未被 `run_sim.sh` 或 `run_xsim.sh` 调用。
- `tools/check_ip_packaging.sh` 在只读沙箱中因无法创建 here-document 临时文件而退出，不能把该次退出单独当成源码门禁结论。另用只读比较确认其算法比较函数对当前生产/历史 P-way 源的比较结果为不相等；完整门禁是否拒绝当前分支需在可写执行环境复核。
- **未覆盖：** 没有逐行审阅范围内全部约 2.7 万行源码；大型板级脚本与 Python 工具做了引用和错误处理模式扫描，未逐项人工审阅。未运行 `run_sim.sh`、Vivado 或 XSim，也未做 K2 功能验证；本次无法对 K2 算法正确性下结论。
