> 脱敏副本，原件 `20261014T135456Z-e5e8dff608/{prompt.txt,answer.md}`。本机绝对路径、邮箱、凭据形模式及非白名单私网 IP 已替换；除脱敏与换行规范化外保留原文。

你是本项目的子 Agent，工作目录 <仓库根目录>。
任务：**从新的硬件 XSA 重建一份完整的、能被 `tools/run_g3.sh --strict-artifacts` 接受的软件制品包**。
（main 需要在板子上验收一次 Stage1 的 RTL 改动，这份包是前置条件。）

【输入（只读）】
- 新硬件包：`hw/build/bkb220-p16-k2-ldpc-prefillopt-20261014T124533Z-board-migrate/`
  - `export/bkb220_p16_k2_ldpc_prefillopt.xsa`（**就是它**，注意文件名与以往不同）
  - `export/top_bd_wrapper.bit`、`export/hardware_build_config.txt`、`reports/{timing,util}.rpt`
- **参考包**（结构照抄它，**不要改它**）：`hw/build/bkb220-p16-k2-ldpc-sw-20261014T104331Z-board-migrate/`
  —— 它是一份已被 `--strict-artifacts` 接受过的包，`manifest.json` / `SHA256SUMS` / `reports/source_manifest.json`
  的格式就是标准答案。**先把它读透再动手。**

【要产出什么】
新包目录：`hw/build/bkb220-p16-k2-ldpc-prefillopt-sw-<UTC时间戳>-board-migrate/`
其中 `export/` 至少要有：`dna_accel.xsa`、`top_bd_wrapper.bit`、`ps7_init.tcl`、`dna_lwip_app.elf`、
`fsbl.elf`、`BOOT.bin`、`boot.bif`；包根要有 `manifest.json`、`SHA256SUMS`、
`reports/source_manifest.json`，以及 `workspace/`（平台 + BSP + 应用工程）。

【怎么做】
1. 用 **WSL 的 Vitis/XSCT 2022.2**（`<本机路径>`）走 `sw/scripts/create_vitis.tcl`。
   运行前先读它，注意它已有一处**新 workspace 必需**的补步（先 `platform generate` 物化 BSP 头，
   再设 `TCP_WND` 并重新生成）。
2. 应用源码是 `sw/app/`（**权威源**）。**不要手改 `sw/app/`**；包内副本必须是它的拷贝。
3. ⚠️ **已知本机限制**：`app create` 在这个 XSCT 安装树上可能报
   `Socket create error. Operation not permitted`。参考包当年就是这么过来的——它改用
   **同一安装树的 ARM GCC** 直接编译 `sw/app/` 并链接新 BSP 的 `libxil.a`/`liblwip4.a`。
   你遇到同样错误就照做，**并把这条偏差写进报告**（不许假装走通了 `app create`）。
4. ⚠️ **打包格式的坑（这三个坑 main 今天刚踩过，别再踩）**：
   - `SHA256SUMS` 里的路径**必须是裸相对路径**，**不能带 `./` 前缀**
     （`g3_artifacts.py` 按裸名查表，带 `./` 会让它找不到 `manifest.json`）；
   - `reports/source_manifest.json` 必须是门禁 schema：`{"schema_version":1,"scope":...,"excluded_files":[...],"files":{相对路径:SHA256}}`，
     **不是**自定义字段名；
   - `manifest.json` 的 `tool_versions.vivado` 必须是**可核验的版本号**（如 `"2022.2"`），
     不能塞散文（如 `"2022.2 (not run)"`），否则门禁拒收。
   - **最省事的做法**：写完清单后跑
     `python3 tools/write_source_manifest.py --package <新包> --resign`
     它会按当前工作树重建 source_manifest、同步 `manifest.json` 里的哈希、并重签 + 自检 `SHA256SUMS`。
     先读这个脚本确认它做什么，再决定要不要手工兜底。
5. `manifest.json` 里要记：`board_id=bkb220`、`part=xc7z020clg400-2`、
   `parameters`（READ_BPS/NUM_LC/STRIDE/REF_LEN/BATCH/C_STAGE1_P_WAYS/C_STAGE1_PIPE_TREE 与
   参考包一致，另可加 `LDPC_DECODER: true`）、`artifacts` 六个路径、`tool_versions`、`source_manifest`。
   参考包的字段照抄。

【验收判据 —— 逐条给实际输出，不许"应该可以"】
- `tools/run_g3.sh --artifact-dir <新包> --xsdb <本机路径> --device xc7z020
   --strict-artifacts --uart-port <本机路径> --ip 192.168.1.10 --port 7
   --win-root <本机路径> --plan-only`
  ⇒ **必须通过制品门禁**（`--plan-only` 只做只读门禁校验，**不连板、不烧录、不建 run 目录**）。
  把实际输出贴进报告。
- `cd <新包> && sha256sum -c SHA256SUMS` ⇒ 全部 OK，给出计数。
- 核对 BSP 里确实生成了 `XPAR_LDPC_DECODER_0_BASEADDR`（应为 `0x43C30000`），给出你查的文件路径与值。
- 核对 `BOOT.bin` 用 bootgen readback 确认含 FSBL + bit + 应用 ELF。
- 核对包内 `top_bd_wrapper.bit` 与硬件包里的**逐字节相同**（SHA 相等）。
- **不许上板**：`--plan-only` 是唯一的允许入口；不要真烧录、不要开 hw_server 占板子。

【看板】tools/agent_view.sh，`--agent sw-pkg-prefillopt`：开始前 update、完成时 done。不要手工编辑 view.md。

【产出】新包目录 + 报告 `logs/package/prefillopt-sw-package.md`。

【硬性禁止】
- **不做任何 Git 写操作**；不要跑 tools/verify_repo_binding.sh。
- **不改 `sw/app/**`**（那是权威源）、**不改 `hw/ip/**`**、**不改参考包**、**不改 `hw/scripts/`**。
- **不碰板卡**（不开 hw_server、不烧录、不跑真 G3；只允许 `--plan-only`）。
- 不碰 `clients/python/`（另一个 agent 正在改）。
- 失败就是失败，不要用"编译通过"冒充"包可用"。

【边界】你只交付"一份门禁可接受的完整软件制品包"。**不代表**它已上板、**不代表**板端判据通过。