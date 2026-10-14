> 脱敏副本，原件 `20261013T145616Z-c3a87d87c6/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

已完成 **22 条文档修订**：第 1–6 条、第 8–23 条均已落实；`docs/08-performance-and-strategy.md` 第 7 条按要求未触碰，用户说明该项已由 main 修改并提交。§2「待确认」未改。

逐条记录见 [docs-fix-report.md](<仓库根目录>/logs/audit/docs-fix-report.md)。

**额外调整：**在指定文档中更新了日期，并标明旧 F3、待办和测量数据属于历史快照，避免被读成当前状态；没有改动无关文件或代码。

**验证：**`bash tools/check_repo_hygiene.sh` 两次均 PASS（11 项）；`git diff --check` 无输出；仓库根目录没有 `.log`、`.jou`、`.str` 或 `.pb` 残留。未执行 Git 写操作、仿真、Vivado/XSim 或板卡操作。
