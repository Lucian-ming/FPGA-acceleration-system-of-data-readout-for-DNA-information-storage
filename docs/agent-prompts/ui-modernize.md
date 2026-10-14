# 上位机客户端界面现代化 —— 派发提示词（含防冲突硬规则）

**给谁用**：用户把本文**整段**交给另一个 agent（本文是自包含的，不需要它读别的规划文档）。
**写于**：2026-10-14。**项目**：FPGA 基因数据读出加速系统，仓库根 = 本文件所在的仓库根。

---

## 0. 一句话任务

把 `clients/python/gui_app.py` 这个 tkinter 界面的**外观**做得现代一点，
**行为一行都不许改**。

---

## 1. ⚠️ 先做这一步：确认没人在改同一个文件

**这个仓库是多人/多 agent 并行作业的。正在有别的 agent 修改 `gui_app.py` 与 `first.py`。**

动手前先跑：

```bash
git status --short -- clients/python/
```

- **如果 `gui_app.py` 或 `first.py` 显示为已修改（` M`）** ⇒ **立刻停下来**，
  把 `git status` 的输出写进你的最终答复并说明「当前有人在改同一文件，我没有动手」，
  **不要开始改**。
- 只有在 `gui_app.py` 是干净的时候才可以动手。

## 2. ⚠️ 你的工作范围：**只有 `clients/python/gui_app.py` 这一个文件**

**允许改**：`clients/python/gui_app.py`（唯一）。
**允许新增**：`clients/python/ui_theme.py`（如果你想单独放配色/样式；**仅此一个新文件**）。

**一律不许碰**（有其他 agent 或 main 在负责，改了就是冲突）：

| 不许碰 | 原因 |
| --- | --- |
| `clients/python/first.py` | 另一位 agent 正在改（进度回调、耗时估算） |
| `clients/python/ldpc_pipeline.py` | 核心判据路径，已冻结 |
| `clients/python/native_ldpc.py` | 参考实现，改它等于改判据 |
| `clients/python/tests/` | 另一位 agent 在改 |
| `clients/python/resources/`、`gui_app.spec`、`README.md` | 另一位 agent 在改 |
| `hw/`、`tools/`、`docs/` | 别人的范围 |
| 仓库根目录任何文件 | — |

**如果你认为某个改动非要在 `first.py` 里做**（比如某句状态文案）：**不要改**，
写进你的最终答复，让 main 去协调。

## 3. ⚠️ 绝对禁止 Git 写操作

**`git add` / `git commit` / `git push` / `git pull` / `git rebase` / `git checkout` /
`git stash` / `git restore` 一律禁止。** 也**不要**跑 `tools/verify_repo_binding.sh`
（它是 Git 绑定门禁，在这个沙箱里跑不了，会白费一轮）。

原因：这个仓库的工作树是**多个 agent 共享**的，任何 Git 写操作都会影响别人。
**只改文件，提交由 main 统一做。**

## 4. ⚠️ 看板登记（强制）

```bash
tools/agent_view.sh start  --agent ui-modernize --doing "..." --why "..." --next "..."
tools/agent_view.sh update --agent ui-modernize --doing "..." --next "..."
tools/agent_view.sh done   --agent ui-modernize --doing "..." --next "..."
```

**只能用 `ui-modernize` 这个名字**（用别的名字会跟别人撞车）。
**不要手工编辑 `view.md`**——它是脚本生成的。

---

## 5. 要做什么：只做外观，不动逻辑

现在的界面是 tkinter/ttk，能用但土。目标是**看上去专业一点**，不是重写。

### 5.1 建议做的（按性价比排序）

1. **统一主题与配色**：用 `ttk.Style().theme_use("clam")`（跨平台最好定制），
   定义一份调色板（背景/面板/主色/成功绿/失败红/等待琥珀/文字/次级文字），
   把所有硬编码的颜色收进常量或 `ui_theme.py`。
2. **状态色语义化**：现在的步进标签是 `relief="groove"` 的灰框。
   改成**胶囊/芯片样式**：未开始=灰、进行中=主色、完成=绿、**失败=红**。
   ⚠️ **「失败」必须一眼看得出来**（这个项目的核心判据就是"通过/失败"，
   失败要红得醒目，不许用灰色糊弄过去）。
3. **排版层级**：分区标题加粗；说明性文字用次级色、小一号；统一内边距与外边距的节奏。
4. **字体**：Windows 下用 `Microsoft YaHei UI`（中文界面），其它平台回落到默认；
   字号分三档（标题/正文/次要），不要到处都是默认字号。
5. **控件细节**：按钮统一宽度与内边距；输入框统一高度；主操作按钮（开始）视觉上更突出，
   危险操作（停止）用警示色。
6. **窗口行为**：设最小尺寸、允许合理的拉伸、启动时居中；
   **Windows 下开 DPI 感知**（`ctypes.windll.shcore.SetProcessDpiAwareness(1)`，
   用 try/except 包住，非 Windows 平台跳过），否则高分屏上字是糊的。
7. **进度反馈的观感**：进度条加圆角观感/配色；等待板端期间的不确定态滚动条要显眼
   （**只改样式，不要改它什么时候滚动——那是 `first.py` 的契约**）。

### 5.2 明确**不要**做的

- ❌ **不要改任何业务逻辑**：不改校验/失败判定、不改文件收发、不改参数含义、
  不改回调签名、不改线程模型、不改日志内容。
- ❌ **不要引入新依赖**：只能用标准库 + `numpy` + `Pillow`（`requirements.txt` 里已有的）。
  不要 pip 装第三方 UI 库。
- ❌ **不要换 GUI 框架**（不要换 PyQt/Web/…）。
- ❌ **不要删功能、不要删按钮**（包括你可能觉得没用的那些——有人在别处依赖它们）。
- ❌ **不要改窗口里显示的文案语义**（措辞可以更清楚，但不能改变它表达的事实）。
- ❌ 不要动打包配置。

---

## 6. 怎么自己验证（这个环境**能**跑 GUI）

环境里已经装好 `tkinter 8.6`、`xvfb-run` 与 `imagemagick`，所以**你可以真的把界面跑起来并截图**：

```bash
# 1) 语法
python3 -m py_compile clients/python/gui_app.py

# 2) 无头启动，确认不抛异常（跑 8 秒后自动杀掉）
cd clients/python && timeout 8 xvfb-run -a python3 gui_app.py ; echo "exit=$?"

# 3) 截图（另开一个 shell：先启动 GUI，再抓图）
cd clients/python && (xvfb-run -a --server-args="-screen 0 1280x900x24" python3 gui_app.py &) ; sleep 6
DISPLAY=:99 import -window root /tmp/ui_after.png     # 具体 display 号看 xvfb-run 输出
```

**截图要交出来**：把改前 / 改后的截图都放进 `logs/ui-modernize/`（`logs/` 在 .gitignore 内），
在最终答复里给出路径。**让用户能直接看到效果，而不是只能听你说"我改好了"。**

> 提示：`xvfb-run` 每次会挑一个空闲 display，用 `--server-args` 固定屏幕尺寸；
> 抓图时 `DISPLAY` 要对上。抓不到就退而求其次，**至少保证第 2 步的启动不抛异常**，
> 并如实说明截图没成功。

### 验收判据

- `python3 -m py_compile clients/python/gui_app.py` 通过。
- `timeout 8 xvfb-run -a python3 clients/python/gui_app.py` **不抛异常**（超时被杀是正常的）。
- `bash tools/test_client.sh` **PASS**（它基本不测 GUI，但你改坏了导入链它会红）。
- `bash tools/check_repo_hygiene.sh` **PASS**。
- 改前/改后截图（能截到就交，截不到要说明）。
- `git status --short` 里**只有** `clients/python/gui_app.py`（和可选的 `ui_theme.py`）
  是你改的；**出现别的文件就说明你越界了**。

---

## 7. 最终答复要包含

1. 改了哪些**视觉**维度（逐条）。
2. 上面 5 条验收判据的**实际输出**。
3. 截图路径（或说明为什么没有）。
4. **明确列出你没有做的事**：没碰任何逻辑、没碰 Git、没碰允许范围外的文件。
5. 如果你认为某处必须改 `first.py` 才能做好——写在"建议但未做"里，**不要自己动手**。
6. 你自己**无法验证**的部分（例如真实 Windows 下的字体/DPI 效果），如实说。

---

## 8. 背景（一句话，够你理解界面在做什么）

这个界面是上位机客户端：给 FPGA 板子发读段数据、等它处理、拿回结果、
**校验板端返回的码字是否已经纠对**（校验不过就是失败，没有 PC 侧兜底），
然后把还原出来的图像/音频/视频/文本显示出来。
所以界面上最重要的两个信息是：**任务跑到哪一步了**、**这一例通过了还是失败了**。
你的现代化要让这两件事**更容易一眼看清**。
