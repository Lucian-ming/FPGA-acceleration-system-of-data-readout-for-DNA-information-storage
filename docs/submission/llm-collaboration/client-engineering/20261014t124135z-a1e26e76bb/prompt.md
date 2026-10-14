> 脱敏副本，原件 `20261014T124135Z-a1e26e76bb/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目的客户端子 Agent，工作目录 <仓库根目录>。

【背景 —— 用户刚下的架构决定】
**LDPC 译码全部由 FPGA 片上完成，PC 端彻底不做译码；PC 若还需要"再译一次"就说明板端没纠对，那是失败，不允许 PC 兜底。**

我已经把核心改完了（`clients/python/ldpc_pipeline.py` 已重写，**不要改它**）。你只改界面与 CLI 两侧。

【已冻结的接口 —— 照这个用，不要改签名】
```python
from ldpc_pipeline import verify_board_result, BoardVerifyResult, BoardCodeRejected

res = verify_board_result(
    result_bits_path,          # Path：板端回传解包后的 64,800 个 0/1 文本（dec_input.txt）
    output_dir,                # Path
    input_bytes=None,          # Optional[int]：载荷字节数；None => 按 JPEG EOI 截断
    log=None,                  # Optional[Callable[[str], None]]
) -> BoardVerifyResult         # 字段：result_path, dec_input_path, decoded_bits_path,
                               #       payload_path, payload_bytes, failed_rows, total_rows,
                               #       属性 .verified
# 板端没纠对时抛 BoardCodeRejected(failed_rows, total_rows) —— **这是失败判据**
```
旧的 `run_ldpc_decoder` / `LDPCResult` / `SUPPORTED_BACKENDS` **已不存在**。

【本轮范围：`clients/python/gui_app.py` 与 `clients/python/first.py` 两个文件】

**1. 彻底去掉 PC 译码的界面与路径**
- 删掉后端选择器（`backend_var` 及那个 Combobox、`SUPPORTED_BACKENDS` 的一切引用）与相关参数预设字段。
- 删掉「仅跑译码」按钮与 `_run_ldpc_only`（连同它的入口）。它是不连板子重跑主机译码的遗留调试功能。
- 结果卡片与指标栏的文案改成反映真实分工：例如「片上 LDPC（板端）」而不是「极速译码」；
  主机那一步只叫「**校验**」，不要出现"译码/解码"字样。

**2. BoardCodeRejected 必须是**失败**，不是警告**
- 捕获它后，界面要**明确变红/判失败**（例如状态显示「✗ 板端未纠对：N/M 条校验行非零 —— 本用例失败」），
  **绝对不要**再退回任何主机侧译码、也不要"尽力而为地显示个图"。
- 成功时显示「✓ 板端已纠对（10800 条校验行全零）；PC 端未做译码」。

**3. 加「载荷字节数」输入（这条是修一个真实缺陷）**
- 现在界面**没有**这个字段，客户端默认按 JPEG 的 EOI 截断 —— **非图像载荷（音频/视频/文本/二进制）根本没有 EOI，截不出来**。
- 加一个整数输入框，对应 `input_bytes`；留空 => 沿用 JPEG EOI（R0.83 那条老判据仍要能用）。
- 取值范围 1..6750（`native_ldpc.MAX_PAYLOAD_BYTES`）。

**4. 结果展示按媒体类型分派（现在一律当图像塞给 PIL）**
- 载荷可能是 image / audio / video / text / binary。**只有图像才进 PIL 预览**。
- 其它类型：不要试图当图像显示（会报错或显示乱码），改为显示「已保存到 <路径>，N 字节」+ 一个「用系统默认程序打开」按钮。
- 判断方式别靠扩展名猜：优先看载荷头几个字节的魔数（JPEG `FF D8 FF`、PNG、GIF、RIFF/WAVE、ID3/`ftyp` 等），
  判不出来就当二进制处理。**判错也不要报错，降级成二进制显示即可。**

**5. 修流水线状态指示与进度条（这是你上一个版本的真 bug）**
- 现状：`first.py` 的 `progress.set_stage(...)` 传的是 `"UPLOAD"` / `"POST"` / **`"RESULT"`**，
  而 `gui_app.py` 的 `PIPELINE_STAGES` token 是 `CONFIG/WM/UPLOAD/POST/LDPC` ——
  **`"RESULT"` 根本不在表里**，那一次调用是空操作，所以最后一段永远不亮；`CONFIG`/`WM` 也从没人设过。
  ⇒ 用户实测「只能显示首状态和末状态」。
- 要求：**两侧 token 对齐**（改哪侧都行，但必须自证一致，例如加一条断言或共用一份常量）；
  `CONFIG` 与 `WM` 要真的被设置；**最后一段要按新架构命名**（不再是"极速译码"）。
- **进度条现在只跟上传走**：板上那 6 秒冻在 100% 毫无反馈。要求：等待板端结果期间给出
  **真实反馈**——例如「已等待 X 秒 / 预计 Y 秒」的实时计时 + 不确定态（indeterminate）滚动条。
  预计耗时用**当前实测口径**（下面给你数），不要用旧模型。

**6. 「预计硬件耗时」的旧模型是错的（差 17~19 倍），一并修**
- `first.py:estimate_processing_time` 现在写死 `t = 4.93s + 0.9396ms × 记录数`。
  实测：4,096 读段 → 0.65 s（模型给 12.63 s）；51,781 读段 → 5.89 s（模型给 102.24 s）。
- 换成基于**当前 K=2 + 片上 LDPC** 两点的线性式：`t ≈ 0.43 + 0.0526 ms × 记录数`
  （点：4096 记录→0.65 s；103616 记录→5.89 s）。**必须把这句的来历写进注释**
  （哪两点、哪一天测的、为什么旧式子作废），并注明**只有两个点，是粗估**。

【验收判据 —— 逐条给实际输出】
- `python3 -m py_compile clients/python/gui_app.py clients/python/first.py` 通过。
- `bash tools/test_client.sh` **PASS**（注意：另一个子 Agent 正在改 `clients/python/tests/`，
  若它导致的红不是你引起的，报告里说明即可，不要改 tests/）。
- `bash tools/check_repo_hygiene.sh` PASS。
- **端到端自测（不需要板子）**：用真实留证 `<本机路径>`
  走一遍你的新代码路径，确认载荷 SHA == `fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3`；
  再用 `<本机路径>`（未收敛）
  确认**被判失败**且界面走的是失败分支。把两条的实际输出写进报告。
- 报告里逐条写：改了什么、**哪些是你在本环境无法验证的**（WSL 无 tkinter，GUI 交互你验不了，如实说）。

【看板】tools/agent_view.sh，`--agent gui-fpga-only`：开始前 update、完成时 done。不要手工编辑 view.md。

【产出】改：`clients/python/gui_app.py`、`clients/python/first.py`；报告 `logs/client/gui-fpga-only-report.md`。

【硬性禁止】
- **不做任何 Git 写操作**；不要跑 tools/verify_repo_binding.sh（子 Agent 沙箱里跑不了）。
- **不要改 `clients/python/ldpc_pipeline.py`**（已冻结）。
- 不要改 `clients/python/tests/`、`clients/python/resources/`、`clients/python/README.md`、`gui_app.spec`（那是另一位子 Agent 的范围）。
- **不要删任何文件**（`c_ldpc.py` 等由 main 决定，另有 4 个离线工具在 import 它）。
- 不碰 `hw/`、`tools/`、`clients/python/native_ldpc.py`。
- 不许把失败伪装成通过。

【边界】你只交付「界面与 CLI 反映新架构、失败判得出来」。**不代表**板端已验证。