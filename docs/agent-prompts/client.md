# 上位机客户端（`clients/python/`）优化 · 改进 · 补齐 —— 规划与派发

**用户指示（2026-10-14）**：写一个规划把 PC 端客户端做优化改进补齐，计划好后派一个子 Agent 执行。

本文件既是**规划**（要做哪些、按什么顺序、判据是什么），也是**派发阶段卡的底稿**。
动手前必须完整读 `AGENTS.md` 与 `docs/agent-prompts/readme.md`。

---

## 0. 现状盘点（2026-10-14 实测，不是凭印象）

| 文件 | 行数 | 职责 |
| --- | ---: | --- |
| `first.py` | 758 | CLI 与共享核心：读段解析、位平面打包、水印、TCP 收发、指标报告 |
| `gui_app.py` | 965 | tkinter GUI：连接/文件/参数卡、流水线进度、图像预览、哈希校验、日志 |
| `fast_readout.py` | 260 | 高性能向量化读出（numpy + LUT），自称与 `first.py` **逐位等价** |
| `task_protocol.py` | 214 | 任务模型 `TaskSpec`/`TaskCaps`、配置拒绝码 |
| `ldpc_pipeline.py` | 243 | 译码流水线，三个后端（native / c_accel / external）的分派 |
| `native_ldpc.py` | 177 | 纯 Python DVB-S2 R=5/6 硬判决译码参考实现 |
| `c_ldpc.py` | 162 | C 加速后端（ctypes 载 `libc_ldpc.so`） |
| `protocol.py` | 154 | 线上协议 |
| `tests/test_client_core.py` | ~400 | 7 个 unittest 类 |

---

## 1. 已确认的缺口（每条都有实测依据，不是猜测）

### G1 ★ 一半以上的测试**从未被执行过**

```
$ python3 clients/python/tests/test_client_core.py
Ran 12 tests ... OK

$ python3 -m unittest discover -s clients/python/tests -p "test_*.py"
Ran 25 tests ... OK
```

原因：`tests/test_client_core.py` 的 `if __name__ == "__main__": unittest.main()`
在**第 200 行**，而 `SE250GeometryTests`（204 行）与 `CLDPCAndAdaptivityTests`（352 行）
定义在它**后面**。模块自上而下执行 ⇒ `unittest.main()` 被调用时这两个类还不存在，
**13 个测试（25 个中的 13 个）静默不跑**。

> 这和 `tools/README.md` 开头那条教训同源：**无人可见的脚本等于结论不存在；
> 没人跑的测试等于没有这个测试。** 而且这里更坏——它**打印 OK**。

### G2 预编译二进制**没有同源校验**

`clients/python/resources/` 里入库了 `libc_ldpc.so`（Linux）与
`R5_6_LDPC_hard_decoder.exe` + 三个 MinGW DLL（Windows）。仓库对**制品包**有严格的
「SHA / manifest / 源码同源」门禁，对**客户端这两份二进制却没有**：
- 没有任何机制证明 `libc_ldpc.so` 出自当前的 `c_ldpc_accel.c`；
- `c_ldpc.py` 的候选名里有 `c_ldpc.dll`，但**库里没有 Windows 版 C 加速库** ⇒
  Windows 侧 `auto` 会静默退到纯 Python（比 C 慢一个量级），而用户看不出原因。

### G3 `fast_readout` 与 `first.py` 的「逐位等价」**没有回归**

它自称 Bit-Exact，`run_g3.sh` 用的也是 `fast_readout` 这条快路径，
GUI/CLI 走的是 `first.py` 那条。**两条路如果分叉，没有任何测试会红。**
现有 `tests/test_client_core.py` 里 `fast_readout` 出现 0 次。

### G4 三个 LDPC 后端**没有真实交叉比对**

`LDPCBackendTests` 全是 `mock`，只验「分派逻辑选对了哪个后端」，
不验「三个后端给出相同结果」。而 `CLDPCAndAdaptivityTests` 里那条真实比对
又正好落在 G1 的静默区里。

### G5 没有测试入口，也没有接进任何门禁

仓库有 `tools/run_sim.sh`（RTL+主机侧回归）与 `check_*.sh`，客户端测试**不在其中**。
没有一条命令能回答「客户端现在是不是好的」。

### G6 客户端没有面向使用者的文档

`docs/02/04` 是**协议契约**（给实现者看），不是**使用说明**。
换个人拿到这个仓库，不知道 GUI 怎么起、三个后端怎么选、失败长什么样。

---

## 2. 工作项（按优先级，P0 先做）

| 项 | 内容 | 验收判据 |
| --- | --- | --- |
| **P0-1** | 修 G1：把 `unittest.main()` 挪到文件末尾（或删掉，改由统一入口发现） | 直接跑与 discover 都是 **25/25 PASS** |
| **P0-2** | 加统一测试入口 `tools/test_client.sh`：先做语法检查、再 discovery 跑全部客户端测试；**断言收集到的用例数不少于登记值**（防「新增测试没被收到」重演） | 一条命令 PASS/FAIL；用例数下限写死在脚本里并有注释说明为何 |
| **P0-3** | 登记进 `tools/README.md`；并在 `AGENTS.md`／`docs/06` 的相应位置指过去 | 卫生门禁 PASS（未登记脚本会红） |
| **P1-1** | 补 G3：`fast_readout` vs `first.py` 的**逐位等价**回归——真实 FASTQ/plain 样本 + 边界（空文件、非 4 的整数倍、含 N、大小写、`--orient both/forward`、`read_bps 150/250`） | 每一组两路输出**逐字节相同**；不符即 FAIL 并打印首个不符偏移 |
| **P1-2** | 补 G4：三个后端的**真实**交叉比对（native 必跑；c_accel 存在时必跑；external 仅在 `resources` 齐全时跑，否则明确 skip 并记账） | 同一输入的载荷 SHA 三方相同；缺失后端要**显式报告跳过**而不是静默通过 |
| **P2-1** | 补 G2：`clients/python/resources/` 加 `SHA256SUMS` + `SOURCES.json`（记录各自的上游源文件与构建命令），`c_ldpc.py` 载库前校验；`build_c_accel.sh` 重编后刷新清单 | 篡改 `.so` 会被载入前拦下；清单与源文件对得上 |
| **P2-2** | 补 G2 的 Windows 半边：**要么**给出 `c_ldpc.dll` 的构建方法并产出，**要么**在 `c_ldpc.py` 里对「Windows 下 C 加速不可用」给出**可见警告**（不许静默降级） | 二选一，但必须**显式**；不得留「静默慢」 |
| **P3-1** | 补 G6：`clients/python/README.md` 使用说明（GUI/CLI 起法、三后端与选择规则、常见失败与含义、数据集与阈值口径） | 新人只读这一页能跑通 smoke |
| **P3-2** | GUI 的实际短板（**先测后改，别凭猜**）：多轮/批量数据集跑、结果历史与对比、失败样本归档、参数预设存读。**先写清哪几条真缺**，再动手 | 每条改动都要有对应的可复现操作步骤与判据 |

**明确不做**（避免摊子铺大）：
- 不重写 GUI 框架、不换 tkinter；
- 不动 `protocol.py` / `task_protocol.py` 的**线协议**（改了就是板端契约变更，属另一条线）；
- 不动 `native_ldpc.py` 的算法语义（它是 L4 黄金的参考实现，动它等于动判据）；
- 不碰 `hw/`、`tools/run_g3.sh`、`tools/board/`（板级验收路径另有其人）。

---

## 3. 派发阶段卡（给子 Agent）

**通道**：用户级 MCP `codex-luna`（`codex_run` / `codex_status`），固定 `gpt-6-luna` + max。
**不要**用 Agent 工具派子会话。

**看板**：`--agent client-core`（workspace-write 任务，**自行登记** `start` / `update` / `done`：
`tools/agent_view.sh start --agent client-core --doing ... --why ... --next ...`）。

**sandbox**：`workspace-write`。
**Git**：**任何 Git 写操作都不要做**（add/commit/push/rebase 一律禁止），由 main 按路径提交。

**第一轮只做 P0**（一轮一出口，不要一次铺开）：
1. 修 `tests/test_client_core.py` 的 `unittest.main()` 位置问题；
2. 新增 `tools/test_client.sh`；
3. 登记 `tools/README.md`。

**验收要求**（必须逐条给出实测输出，不接受"应该可以"）：
- `python3 clients/python/tests/test_client_core.py` → 25 tests，OK；
- `python3 -m unittest discover -s clients/python/tests -p "test_*.py"` → 25 tests，OK；
- `bash tools/test_client.sh` → PASS，且打印实际用例数；
- `bash tools/check_repo_hygiene.sh` → PASS（未登记脚本会红）；
- 故意把某个测试改成失败，确认 `tools/test_client.sh` **变红**（自证门禁有效，不是永远绿的装饰）。

**产出路径**：
- 改：`clients/python/tests/test_client_core.py`
- 增：`tools/test_client.sh`、`tools/README.md`（只在脚本表里加一行）
- 报告：`logs/client/p0-report.md`（写清改了什么、四条判据的实际输出、以及你**没有**做什么）

**禁止**：改 `clients/python/` 下除 `tests/` 以外的任何文件（P0 不需要）；
改 `hw/`、`tools/run_g3.sh`、`tools/board/`；跑 Git 写操作。

---

## 4. 已知边界与纪律（派发时必须一并附上）

1. **`clients/python/resources/` 里的二进制是既有制品**，P0 不碰。P2 要动它们时，
   必须先把「当前值与用途」列清楚再改，并保留原件。
2. **`native_ldpc.py` 是 L4 黄金的参考实现**（见 `docs/benchmarks/ldpc-decoder-l4.md`）。
   任何让它与 RTL 行为一致化的"优化"都是改判据，不做。
3. **`fast_readout.py` 是 `run_g3.sh` 的快路径**。P1-1 若发现它与 `first.py` 不一致，
   **不要单方面改任何一边**——先报告，由 main 判定哪一边是准的（板端留证用的就是它）。
4. **不许静默降级**：后端不可用、测试被跳过、用例被收集不到，都必须**打印出来**。
   这条是本项目反复踩过的坑（G1 就是「打印 OK 却少跑一半」）。
5. 客户端时间测量要注明**在哪台机器、哪个后端**；`t_result` 之类以板端自报为准。
