> 脱敏副本，原件 `20261014T113614Z-caedbf84b6/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目（FPGA 基因数据读出加速系统）的客户端子 Agent，工作目录 <仓库根目录>。

【必读】先完整读 docs/agent-prompts/client.md（本任务的规划与阶段卡），以及 AGENTS.md 的开发规范（语言约定、文档地图、事实边界、常见陷阱）。不要读整个仓库，聚焦本任务。

【本轮范围：只做 P0，三件事，别铺开】
1. 修 clients/python/tests/test_client_core.py 的缺陷：`if __name__ == "__main__": unittest.main()` 在第 200 行，而 SE250GeometryTests（204 行）与 CLDPCAndAdaptivityTests（352 行）定义在它之后，导致直接运行该文件时这 13 个测试（共 25 个）静默不跑，却仍打印 OK。实测：直接跑 12 tests，discover 跑 25 tests。
2. 新增 tools/test_client.sh —— 客户端测试的统一入口：先对所有 clients/python/*.py 做语法检查（python3 -m py_compile 或 compileall），再用 unittest discovery 跑全部客户端测试，并**断言实际收集到的用例数不少于脚本里写死的下限（25）**，少于下限即 FAIL。下限旁边必须写注释说明为什么是 25、以及「新增测试没被收集到」正是要防的事。
3. 在 tools/README.md 的脚本表里登记 tools/test_client.sh（只加一行，格式仿照现有行；未登记的脚本会被 tools/check_repo_hygiene.sh 判红）。

【验收判据 —— 必须逐条给出实际输出，不接受「应该可以」】
- `python3 clients/python/tests/test_client_core.py` → 25 tests，OK
- `python3 -m unittest discover -s clients/python/tests -p "test_*.py"` → 25 tests，OK
- `bash tools/test_client.sh` → PASS，并打印实际用例数
- `bash tools/check_repo_hygiene.sh` → PASS
- **自证门禁有效**：临时把某一个测试改成必定失败（例如断言 1 == 2），确认 `bash tools/test_client.sh` **变红**并给出非零退出码，然后**恢复原样**。把变红时的输出也记进报告。永远绿的装饰性门禁不算交付。
- 另外确认 `bash tools/check_ip_packaging.sh` 仍然 PASS（你的改动不应影响它）

【看板 —— 强制】你已由 main 以 `--agent client-core` 登记。请用 tools/agent_view.sh 自行维护：
  开始动手前：tools/agent_view.sh update --agent client-core --doing "..." --next "..."
  中途换子任务/发现新情况时 update
  全部做完：tools/agent_view.sh done --agent client-core --doing "..." --next "..."
  不要用别的 --agent 名字，不要手工编辑 view.md（它是生成物）。

【产出】
- 改：clients/python/tests/test_client_core.py
- 增：tools/test_client.sh
- 改：tools/README.md（只加一行登记）
- 写报告：logs/client/p0-report.md（改了什么、五条判据的实际输出、以及你**没有**做什么）

【硬性禁止】
- **不要做任何 Git 写操作**（add/commit/push/rebase/checkout 一律禁止），Git 由 main 负责。也不要跑 tools/verify_repo_binding.sh（它是 Git 绑定门禁，在子 Agent 沙箱里跑不了，会白跑一轮）。
- 不要改 clients/python/ 下除 tests/ 以外的任何文件（本轮不需要）。
- 不要动 hw/、clients/python/resources/ 下的任何二进制、tools/run_g3.sh、tools/board/。
- 不要改 clients/python/native_ldpc.py（它是 L4 黄金的参考实现，改它等于改判据）。
- 不许静默跳过：任何被跳过的测试或不可用的后端都必须显式打印出来。

【边界】你只证明「测试能被完整收集并执行、入口可复现」。这**不代表**客户端功能已完备，也不代表它在板端跑通。