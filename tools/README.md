# tools/ 仓库维护门禁索引

> **目录说明**：本目录（`tools/`）仅保留仓库级维护与门禁脚本。项目构建、板测、自检与仿真脚本已按权威提交包布局统一归置于 `src/tools/`（详见 [`src/tools/readme.md`](../src/tools/readme.md)）。历史探索与比对工具归档于 `docs/history/`。

---

## 仓库维护脚本清单

| 脚本名称 | 语言 | 职责与使用说明 |
| :--- | :---: | :--- |
| `agent_view.sh` | Bash | **多 Agent 看板运维工具**。支持 `start`, `update`, `block`, `done`, `refresh`, `show`。内部采用 `flock` 串行化状态写入，`show` 为只读安全路径（不加锁、不建目录、不重渲染）。**禁止手工编辑根目录 `view.md`**。 |
| `verify_repo_binding.sh` | Bash | **Git 仓库与远端绑定门禁**。在动手前与交接前必须执行，核验 checkout 路径、分支 `main`、远端 `origin` URL、GitHub 凭据与读写权限；支持 `--remote`（核验远端推送权限）与 `--require-synced`（核验 `main...origin/main` 为 0/0）。 |
| `check_repo_hygiene.sh` | Bash | **代码卫生门禁检查器**。检查仓库根目录工具残留、工具登记一致性、文档命名编号、未跟踪大文件覆盖、文件行号引用悬空或越界等规范。 |

---

## 项目工程脚本指引

- **构建、复现、板测与仿真入口**：请查阅 [`src/tools/readme.md`](../src/tools/readme.md)（含 `run_sim.sh`、`run_g3.sh`、`make_artifact_package.py` 等）。
- **历史演进与对照实验脚本**：请查阅 `docs/history/`（含 `bench-cpu-tools/`、`milestones/`、`experiments/` 等）。
