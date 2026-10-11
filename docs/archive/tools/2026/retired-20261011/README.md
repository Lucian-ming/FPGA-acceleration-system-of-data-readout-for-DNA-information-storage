# 已退役工具源码（2026-10-11）

按用户要求从现用工具区移出6个历史脚本。文件字节、执行权限和原有历史证据保留；校验：在本目录运行`sha256sum -c SHA256SUMS.txt`。

这些文件只用于追溯，脚本中的相对路径仍是原布局，不是可直接执行的新板入口。新板从[当前05计划](../../../../05-implementation-plan.md)和[现用工具索引](../../../../../tools/README.md)继续。

| 文件 | 原位置 | 大小 | 归档依据 |
|---|---|---|---|
| `extract_ldpc_dlls.py` | `tools/extract_ldpc_dlls.py` | 2,408 B | 历史gui_app.exe的一次性DLL提取；当前客户端运行库已保留，无现用调用者。 |
| `debug_vote_diff.py` | `tools/attic/debug_vote_diff.py` | 2,427 B | 已退役的BRAM票值定位脚本；保留TB的dump能力和历史源码，非现用验收入口。 |
| `debug_high_entropy.py` | `tools/attic/debug_high_entropy.py` | 39,656 B | 已退役的高熵失败诊断；结论和原始失败证据保留在entropy_and_d2_validation等文档中。 |
| `voter_page_split.py` | `tools/attic/voter_page_split.py` | 5,600 B | 已退役的B20跨4KB页参考表；结论已进入SE250历史研究和正式接口实现。 |
| `stress_test_suite.py` | `tools/stress_test_suite.py` | 27,329 B | 旧板压测依赖硬编码旧制品/目标，auto切SE250；新板改用严格完整包G3及故障探针编排。 |
| `switch_export.sh` | `tools/switch_export.sh` | 4,196 B | 只被旧压测调用，覆盖旧export/BSP头；与调用者一同退出现用区，新板每个profile使用独立成套包。 |
