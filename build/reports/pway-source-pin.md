# Stage1 P-way 源码冻结值：为什么提交包与开发仓库不同

日期：2026-10-30  
对象：`src/hw/ip/dna_accelerator_core_1_0/hdl/srpe_batch_pway.v`  
门禁：`src/tools/check_ip_packaging.sh` 的 `PRODUCTION_PWAY_SHA256`

## 结论

提交包里的冻结值是 `03a78b21846061dfbc8736b656d8af9cacd6fd636f52ea5b0927a2e44f10feb6`，
开发仓库里是 `54104a968458ab884b51fc254698f0e569c9b31b8d4639e7a554e7bf7171057a`。

两份文件**只差一行注释**：第 6 行说明顶层模块名。其余逐字节相同（同为 32,443 B）。

| | 提交包 | 开发仓库 |
| --- | --- | --- |
| 文件字节数 | 32,443 | 32,443 |
| 原始 SHA-256 | `03a78b21…` | `54104a96…` |
| **去注释去空白 SHA-256** | `c5f1ccf5…` | `c5f1ccf5…` |
| 第 6 行注释里的顶层名 | `dna_accelerator_core_v1_0` | `Dna_accelerator_core_v1_0` |

去注释去空白后的 SHA 完全相同（`c5f1ccf54e20f7fc7c87b8cfea522446a9136629ad407bfd4753e8996630b74a`），
说明这是**纯注释差异，不是源码漂移**。

## 为什么会差这一行

两份文件各自说的都是**自己那棵树里的真话**：

- 开发仓库的顶层文件是 `hw/ip/Dna_accelerator_core_1_0/hdl/Dna_accelerator_core_v1_0.v`，
  `module Dna_accelerator_core_v1_0`（首字母大写）。
- 提交包按竞赛指南 §3.3.5.4 的小写命名要求，顶层改名成
  `hw/ip/dna_accelerator_core_1_0/hdl/dna_accelerator_core.v`，
  `module dna_accelerator_core_v1_0`，`component.xml` 的 `spirit:modelName` 同步为小写。

注释跟着各自树的顶层名走。两边的模块名本身都由宏 `SRPE_BATCH_PWAY_MODNAME` 给出，
**没有任何代码标识符因这次改名而变化**。

因此两棵树的冻结值必然不同：把它统一成同一个值，等于要求其中一棵树的注释写错名字。
修正方式是**按树各自钉住自己的值**，而不是让某一份文件去迁就另一棵树。

## 为什么这个值可以改

提交包里的 `03a78b21…` 是**制品实际出片的那一份源码**：
`build/artifact/reports/source_manifest.json` 记录的
`hw/ip/dna_accelerator_core_1_0/hdl/srpe_batch_pway.v` 就是这个值。
包内 `check_ip_packaging.sh` 钉住它，校验的正是「出片源码 = 门禁认可的源码」。

## 改动前后的行为证据

改冻结值的前提是行为等价，不是「看着一样」。证据来自生产等价回归
`tools/run_sim.sh stage1_production_full`（它在包内实测的就是 `03a78b21…` 这份文件）：

| 档位 | round=0 | round=1 | 判据 |
| --- | --- | --- | --- |
| LC=6 | P4 = 258,875 拍 / P16 = 93,739 拍 | 同左 | PASS |
| LC=50 | P4 = 1,680,956 拍 / P16 = 304,653 拍 | 同左 | PASS |

两档都通过 `tb_dna_stage1_p16_equivalence.v` 的七项判据：
独立符号滑窗 oracle 三重逐位比对（score/pos/cw）、末组不满 957 bp、步进 807、
补零、反向用例、并列零分、复位再任务。P4 是计算基准，P16 是对照实现；
两者拍数不同但输出逐位一致，正是本门禁要证明的「微架构改了、结果没改」。

接口用例 `tb_dna_stage1_p16_interface.v` 在 LC=6 下 P4/P16 各两轮 AXIS 握手的
记录数均为 64，P4 252,147 拍 / P16 86,992 拍，同样 PASS。

> 这两张表的数字必须在**同一份文件**上取得才有意义。本表取自提交包（`03a78b21…`）。
> 由于两棵树的去注释 SHA 相同，同一结论对开发仓库那份文件同样成立；
> 但开发仓库的门禁仍钉自己的 `54104a96…`，两者不混用。

## 改冻结值时要求做什么

门禁会显式拒绝未经确认的源码变更，提示要确认两件事：

1. **跑过等价回归**（LC6 与 LC50 两档，即 `tools/run_sim.sh stage1_production_full`）；
2. **改动理由有落处**（本文即落处）。

这两条都在本文件里给出了可核对的数字与路径。反过来说，
**没有这两个前提就改冻结值，等于把「出片源码变了」这件事藏起来**——
而这条门禁存在的全部意义，就是让它藏不掉。
