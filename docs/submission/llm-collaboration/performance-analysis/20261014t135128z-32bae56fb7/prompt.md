> 脱敏副本，原件 `20261014T135128Z-32bae56fb7/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目的**独立验收子 Agent（功能等价方向）**，工作目录 <仓库根目录>。

【你的立场：不采信任何现成结论】
main 刚刚改了 Stage1 的 RTL（提交 `e6c83b9`），声称"逐位等价、每块省 7 拍"。
**你要独立把它验一遍，不许引用、抄录或复述 main 报告里的任何数字作为你的结论。**
你的结论只能来自**你自己跑出来的输出**。发现 main 说错了，要明确指出。

【必读】AGENTS.md（规范、事实边界）；`docs/benchmarks/stage1-block-overhead-plan.md`（被验的改动说明，**当线索读，不要当证据**）；`git show e6c83b9` 看改动本身。

【改动是什么】`hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_pway.v` 的 `S_PREFILL`：
预充填发地址的组数由 `P_WAYS-1 = 15` 改成 `PREFILL_BODY = 8`（K=2 时），
声称"多发的 7 组返回的 tag 落在窗口外、被位置守卫丢弃，所以删掉不影响结果"。
**这个声称的核心就是这个"不影响"——你要把它证死或证伪。**

【本轮范围：只做功能等价验证，不做时序/资源（有另一位验收员负责那一半）】

**1. 独立复现差分仿真**
- 自己构建"旧版 vs 新版"两份 RTL 并同时例化、喂同一激励、逐位比对 `stage1_score` / `stage1_pos` / `stage1_cw`。
- 旧版从 `git show e6c83b9^:<路径>` 取。**不许直接用 `hw/experimental/` 下那份**（它可能是另一个版本，先核对 SHA 再决定）。
- 模块名是宏 `` `SRPE_BATCH_PWAY_MODNAME ``，可以在两份副本里分别替换成不同名字来同时例化。
- **激励要你自己设计**，不要只跑现成的 TB：至少覆盖 P_WAYS=16/PIPE_TREE=1（生产档），
  另外自己**构造能触及预充填边界的输入**——例如让被删掉的那 7 组地址的返回**恰好落进窗口**
  （如果可能）、`pos_base` 在窗口边界、STRIDE 边界、最后一块只用到 7 个位置的情形。
- **报告周期数差异**，并判断是否恰好等于每块 7 拍。

**2. 独立跑既有回归**
- `bash tools/run_sim.sh stage1_pway`（P4 与 P16 两条）
- `bash tools/run_sim.sh stage1_production`（LC6）
- ⚠️ `stage1_production_full`（LC50）**可能正在被 main 跑**，先 `pgrep -af vvp` 确认；若在跑就不要并发跑同一个，改跑 LC6 并说明。

**3. 独立核对"位置守卫"这个声称**
- 直接读 RTL，把预充填里那两处条件的语义写清楚：
  外层 `wm_tag_lc_qq == lc_idx` 与内层位置守卫 `(wm_tag_qq+k >= pos_base) && (wm_tag_qq+k < pos_base+WM_WINDOW_SIZE)`。
- **用你自己的探针**（例如在 TB 里对旧版数"真正落进窗口的写" vs 新版）证明：
  旧版里被删掉的那 7 组，其返回**确实全部落在窗口外**。**这是本次验收的核心命题。**

【验收判据 —— 逐条给实际输出，不接受"应该可以"】
- 差分仿真：给出你实际跑的命令、样本数、不匹配条数（应为 0）、以及周期数（旧/新）。
- 回归：`stage1_pway` 与 `stage1_production` 的实际 PASS/FAIL 与不匹配计数。
- 守卫命题：给出你的探针代码与输出，证明"删掉的 7 组不写窗口"。
- **反证测试（很重要）**：故意把 `PREFILL_BODY` 改成 **7**（少发一组）和 **9**（多发一组），
  分别跑差分仿真，**应该红**。如果改了还不红，说明你的判据没有牙齿——如实报告。
  跑完**恢复原状**并核对 `git diff` 为空。
- **结论只能用你自己的输出支撑**，并明确写"我独立得到 X，与 main 报告一致/不一致"。

【看板】tools/agent_view.sh，`--agent stage1-verify-sim`：开始前 update、完成时 done。不要手工编辑 view.md。

【产出】报告 `logs/verify/stage1-verify-sim.md`（自己建目录）。**不要改任何生产文件**（探针放 `/tmp` 或 `logs/`）。

【硬性禁止】
- **不做任何 Git 写操作**（尤其不许 commit/checkout/stash/restore）；不要跑 tools/verify_repo_binding.sh。
- **不改 `hw/ip/**` 下任何文件**（`git diff` 必须保持为空）。反证测试要在**副本**上做。
- 不碰板卡（不开 hw_server、不烧录、不跑 run_g3.sh、不占 <本机路径>
- 不碰 `clients/python/`（另一个 agent 正在改）。
- 不许把 main 报告里的数字当自己的结果。

【边界】你只回答"这次改动在**功能上**是否逐位等价、周期省了多少"。
**不代表**它能上板，**不代表**整机时序（另有专人）。