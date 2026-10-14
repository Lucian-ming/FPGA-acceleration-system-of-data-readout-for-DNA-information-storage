> 脱敏副本，原件 `20261013T235538Z-02136f8309/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

已完成 `k2-plumbing` 子任务，只修改指定的 6 个文件；未执行 Git 写操作，也未触碰 main 负责的 RTL、testbench 和仿真脚本。

| 文件 | 删除内容 |
|---|---|
| [Dna_accelerator_core_v1_0.v](<仓库根目录>/hw/ip/Dna_accelerator_core_1_0/hdl/Dna_accelerator_core_v1_0.v) | K 参数声明、传给 `srpe_batch_pway` 的覆盖项，以及描述旧 K 选项的注释 |
| [component.xml](<仓库根目录>/hw/ip/Dna_accelerator_core_1_0/component.xml) | 对应的 modelParameter 和 parameter 条目 |
| [Dna_accelerator_core_v1_0.tcl](<仓库根目录>/hw/ip/Dna_accelerator_core_1_0/xgui/Dna_accelerator_core_v1_0.tcl) | GUI 参数、校验与 modelParameter 更新过程，以及旧 K 注释 |
| [bd.tcl](<仓库根目录>/hw/scripts/bd.tcl) | K 默认值、全局覆盖、IP CONFIG 设置和回读项 |
| [build.tcl](<仓库根目录>/hw/scripts/build.tcl) | K 构建选项、整数检查项、取值/P_WAYS 校验、全局变量和构建摘要项 |
| [run_vivado_build.sh](<仓库根目录><本机路径>) | usage 中的 `stage1_bases_per_cycle` 选项 |

**验收结果**

- `bash -n tools/run_vivado_build.sh`：`PASS`
- `tclsh` 的 `info complete`：`bd.tcl`、`build.tcl`、XGUI Tcl 均输出 `1`
- `component.xml`：`XML_PARSE_OK; C_STAGE1_BASES_PER_CYCLE absent`
- CR 计数：wrapper `436 → 436`；XGUI `214 → 214`，均未变化。
- `git diff --stat`：

  ```text
   hw/ip/Dna_accelerator_core_1_0/component.xml                | 10 ----------
   .../hdl/Dna_accelerator_core_v1_0.v                         |  4 ----
   .../xgui/Dna_accelerator_core_v1_0.tcl                      | 13 -------------
   hw/scripts/bd.tcl                                           |  5 -----
   hw/scripts/build.tcl                                        |  8 ++------
   tools/run_vivado_build.sh                                   |  2 +-
   6 files changed, 3 insertions(+), 39 deletions(-)
  ```

- 全树 `/bin/grep -rn "BASES_PER_CYCLE\|bases_per_cycle" hw/ip hw/scripts tools/run_vivado_build.sh` 的命中仅在 main 负责的 `hw/ip/Dna_accelerator_core_1_0/hdl/srpe_batch_pway.v`；六个目标文件的定向检查输出：`PASS: no K identifiers in the six target files`。
- `git diff --check`：`PASS`

`tools/check_ip_packaging.sh` 退出码为 `1`。其余静态检查均通过；唯一失败是预期中的 `AssertionError: 生产Pway算法与本轮P14机械迁移契约不符`，属于 main 负责重写的迁移断言，没有发现其他失败。

未运行 Vivado、XSim 或板测，符合任务约束；没有其他未完成项。
