> 脱敏副本，原件 `20261014T135205Z-d7a9c14182/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目的**独立验收子 Agent（时序/资源/周期模型方向）**，工作目录 <仓库根目录>。

【你的立场：不采信任何现成结论】
main 刚改了 Stage1 的 RTL（提交 `e6c83b9`），声称：每块 101→94 拍、OOC WNS 从 +0.300 升到 +0.755、
整机 LUT 减 299、整机 WNS 从 +0.334 降到 +0.233。
**这些数字你都要独立重测/重推，不许抄录或复述 main 的报告作为你的结论。**
另一位验收员负责**功能等价**那一半，你**不要**重复做差分仿真。

【必读】AGENTS.md；`docs/benchmarks/stage1-block-overhead-plan.md`（当线索读，不当证据）；
`git show e6c83b9` 看改动；`docs/benchmarks/stage1-multibase-ooc-probe.md`（K 的历史基线）。

【本轮范围】

**1. 独立重推"每块拍数"模型（不许跑仿真，纯读 RTL 推导）**
- 通读 `srpe_batch_pway.v` 的状态机，**自己**给出每块的拍数公式与每一项的出处（哪个状态的哪个计数变量）。
- 分别给出**改前**（`git show e6c83b9^`）与**改后**的公式与数值。
- 明确回答：改后每块到底是多少拍？省了几拍？**与 main 声称的 101→94 是否一致？**

**2. 独立重测 OOC 布线后时序与资源**
- 用 `docs/submission/skill/fpga-timing-probe/ooc_probe.tcl`（`SYNTH_IMPL=1`），
  `SYNTH_GENERICS="P_WAYS=16 PIPE_TREE=1 NUM_LC=50"`，对**改前**与**改后**两份各跑一次，
  放你自己的输出目录（例如 `logs/vivado/stage1-verify-sta/`）。
- 给出两者的 LUT/FF/RAMB36/DSP 与 **route 后** WNS/WHS/失败端点。
- **只报布线后数字**；综合后的要标注为估算。

**3. 独立核对整机数字**
- 现成的两份整机产物（**只读，不要重跑**）：
  - 基线：`hw/build/bkb220-p16-k2-ldpc-baseline-20261014T125946Z-board-migrate/`
  - 改动后：`hw/build/bkb220-p16-k2-ldpc-prefillopt-20261014T124533Z-board-migrate/`
- 从各自的 `reports/{timing,util}.rpt` 独立读出：整机 WNS/WHS/失败端点、LUT/FF/RAMB36/DSP、
  以及**最长若干条 setup 路径各自的起点/终点/slack**。
- **关键问题**：整机 WNS 的下降（若有）出自哪条路径？改动前后最差路径是否换了模块？
  给出你从报告里读到的**原始证据**（路径的起点终点与 slack）。

**4. 【重点】核对一个 main 可能说错的地方**
- main 报告里有一句折算："省 7/101 × Stage1 占整轮 ~68.8% = 整轮约 −4.8% ⇒ 6.06 → 约 5.77 s"。
- **你自己独立算一遍这个"Stage1 占整轮的比例"**：需要
  ① 每记录的 Stage1 周期数（用你自己第 1 步的每块拍数 × 每记录块数 ÷ 每条处理的记录数）；
  ② 每记录的整轮实测周期数（用整轮秒数与记录数的**实测**值，注明你用的是哪次实测、哪份留证）。
- **明确指出 main 这个折算对不对**。若不对，给出你的数与算法。

【验收判据 —— 逐条给实际出处】
- 拍数模型：公式 + 每一项的状态/变量出处 + 数值，改前改后并列。
- OOC：两次的实际 rpt 路径与其中的数字（**布线后**）。
- 整机：两边的实际路径与数字。
- 折算复核：你的算式与数字，以及对 main 那句的判断。
- 任何数字都要能指到"哪个文件、哪一行/哪个字段"。

【看板】tools/agent_view.sh，`--agent stage1-verify-sta`：开始前 update、完成时 done。不要手工编辑 view.md。

【产出】报告 `logs/verify/stage1-verify-sta.md`；OOC 产物放 `logs/vivado/stage1-verify-sta/`。

【硬性禁止】
- **不做任何 Git 写操作**；不要跑 tools/verify_repo_binding.sh。
- **不改 `hw/ip/**`**（`git diff` 为空）；要跑改前版本就用 `git show e6c83b9^:路径 > <本机路径>` 取副本再指给探针。
- **不要重跑整机**（太慢）；只读现成的 reports。
- 不碰板卡；不碰 `clients/python/`。
- 不许把 main 报告里的数字当自己的结果。

【边界】你只回答"改动后的拍数/时序/资源到底是什么，整机 WNS 的下降归因于哪条路径"。
**不代表**功能等价（另有专人），**不代表**上板。