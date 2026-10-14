> 脱敏副本，原件 `20261014T115404Z-e66b3ea203/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目（FPGA 基因数据读出加速系统）的子 Agent，工作目录 <仓库根目录>。

【必读】先读 AGENTS.md（开发规范：语言约定、事实边界、文档地图）。再读 docs/benchmarks/stage1-multibase-ooc-probe.md（**本任务是它的续做**）与 docs/benchmarks/bkb220-p16-full-flow-compression.md 的 §2B。

【你的任务：K=3 的可行性探针 —— 只做可行性，不做集成】

背景（已实测，别重复做）：
- Stage1 每块拍数 = `1 + 18 + ceil(150/K) + 5 + 1 + 1`。K=1→176 拍，**K=2（当前生产值）→101 拍**，K=4→64 拍。
- 探针只跑过 K=1/2/4。**K=4 整机 place 硬失败**（63,246 LUT > XC7Z020 的 53,200），K=2 整机有效值 35,702 LUT / WNS +0.313 ns。
- K 现在**已写死为 2**：`hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_pway.v` 的 `localparam integer BASES_PER_CYCLE = 2;`（可配置 parameter 通道已于 2026-10-14 撤销，git 历史里有参数化版本）。

要回答两个问题：
1. **资源与 100 MHz 时序**：K=3 在 XC7Z020 上做 **OOC 综合+布局+布线（SYNTH_IMPL=1）** 能否装入并收敛？给出 LUT/FF/RAMB36/DSP 与 route 后 WNS/WHS/失败端点。已知 K=2 OOC 28,708 LUT / WNS +0.300、K=4 OOC 41,342 LUT / WNS +0.185，K=3 落在中间——**但那是外推，要实测**。
2. **位对齐**（这条可能直接否掉 K=3，务必先想清楚再报）：K=2 是 4 bit（半字节）、K=4 是 8 bit（整字节），而 **K=3 是 6 bit，跨字节**。数据契约的位平面打包/解包（docs/02-data-contract.md，LSB-first）以及 `PLANE_BANK_DEPTH`、`WM_BANK_DEPTH`、`RUN_GROUPS = ceil(150/3) = 50`（150 不被 3 整除？150/3=50 整除，但**每块的碱基总数**与 bank 深度是否还成立要算清楚）是否仍然正确？**如果位对齐会破坏数据契约或需要额外搬运，这本身就是「不可行」的结论**——那就直接给这个结论，不要硬凑。

【做法要求】
- **不要修改生产 RTL**：`hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_pway.v` 与其它 `hw/ip/**` 保持一个字节不动。用 `git show <冻结 K 参数化之前/时的提交>:hw/ip/.../srpe_batch_pway.v` 取出参数化版本，或复制一份到**你自己的临时目录**（如 `<本机路径>`）再改。探针工程与报告放 `logs/vivado/k3-probe/`（logs/ 在 .gitignore 内）与 `docs/benchmarks/stage1-k3-feasibility.md`。
- 沿用既有探针脚本 `docs/submission/skill/fpga-timing-probe/ooc_probe.tcl`（`SYNTH_IMPL=1`）。工具：`VIVADO_ROOT=<本机路径>`。
- **只报布线后数字**，综合后的一律标注为估算。

【验收判据】
- 给出 K=3 的 OOC 布线后 资源/时序 表，并与 K=2、K=4 的已知值并列。
- 明确回答「K=3 是否可行」，并给出理由；**如果不可行，也要给出是哪一条否掉的**（容量？时序？位对齐？）。
- 报告里必须写清：**这是 OOC 单模块，不是整机、不是板测**；OOC 余量不等于整机余量（项目有实测案例：同模块 OOC +0.444 ns，整机只剩 +0.31~0.33 ns）。
- 若你做了仿真，说明覆盖了什么；**没做就写没做**。

【看板】用 tools/agent_view.sh 自行维护，`--agent stage1-k3`：开始前 update、完成时 done。不要手工编辑 view.md。

【产出】报告 `logs/vivado/k3-probe/report.md`（含原始 util.rpt/timing.rpt 路径）+ 新增 `docs/benchmarks/stage1-k3-feasibility.md`。

【硬性禁止】
- **不做任何 Git 写操作**（add/commit/push/rebase），Git 由 main 负责；不要跑 tools/verify_repo_binding.sh（子 Agent 沙箱里跑不了，会白跑一轮）。
- **不改 `hw/ip/**` 下任何生产文件**；不改 `hw/scripts/bd.tcl`。
- **不碰板卡**（板级验证只能 main 做；你在沙箱里也跑不了 Windows 二进制）。不要开 hw_server、不要烧录。
- 不跑整机 synth/impl（太长且没必要，OOC 足够回答可行性）。

【边界】你只回答「K=3 值不值得做」。**不代表**它能进整机、**不代表**它在板上正确。