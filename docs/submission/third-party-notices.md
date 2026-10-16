# 第三方素材许可与再分发清单

盘点日期：2026-10-16

## 1. 范围与判定口径

本清单区分“能识别素材来源”“能识别版权人”“能证明具体许可和再分发权”三件事。文件名、上游项目名、网页可下载、用户提供，或 PDF 中出现版权标记，都不单独证明本仓库有权再分发。

盘点方法：

- 对仓库 955 条 Git 跟踪路径按扩展名和二进制签名盘点，重点检查资源二进制、板卡 PDF、压缩包、图片、数据集、黄金向量和导出制品。
- 阅读根目录 LICENSE、clients/python/resources/SOURCES.json 和 readme.txt、板卡资料 README 与 SHA256SUMS、数据集 manifest 与 SHA256SUMS、data/MANIFEST.md、hw/build/export/README.md 与 SHA256SUMS。
- 对仓库内 7 份跟踪 PDF 提取全文，检索版权、许可、保留权利等文字；对 ECO LED 压缩包检查成员清单；对可见的本地 BSP 副本阅读 lwIP 随附 COPYING。
- 未联网、未下载、未安装软件。没有在素材内找到可用授权文本的，明确列为“未能确定”，不把常见上游许可当作该文件已获证实的许可。

表中共列 32 个素材族：26 个至少有文件纳入 Git 跟踪，另 6 个只存在于本机忽略/未跟踪目录。按素材族统计，3 项能从本地许可文本或项目记录确定许可，29 项的具体许可或再分发授权未能确定。素材族允许包含同来源的多份文件，表中分别列明路径和可用哈希清单。

根目录 MIT LICENSE 明确只覆盖本仓库作者原创源码、脚本、测试和文档；它不自动覆盖厂商文件、外部数据、预编译程序、生成制品内的第三方 IP 或历史材料。

## 2. 客户端资源

SOURCES.json 已提供资源哈希和用途；它是溯源记录，不是许可文件。

| 素材 | 来源 | 许可判断与依据 | 能否再分发 | 本次处置建议 |
| --- | --- | --- | --- | --- |
| clients/python/resources/R5_6_LDPC_hard_decoder.exe；SHA-256 ceadd2f55445ebae8c042922f047777f4351cb2b9a186c1178279350ba9a7d71 | SOURCES.json 说明上游文件未记录，仓库无源码、构建脚本或 URL；docs/01-architecture.md 记为无源码的外部解码器 | 未能确定。检查了 SOURCES.json、resources/readme.txt 和客户端说明；没有许可证或原始发行版信息。根目录 MIT 不覆盖该外部程序 | 不确定 | 当前 GUI 不调用，建议从对外提交包删除；若仍需保留，仅在确认上游许可后再分发 |
| clients/python/resources/dvb_s2_r5_6.pchk；SHA-256 9b33ea42f3334e5fbc2aa3cb4b76d968a184da591c9dcb0284a29b3964c407dc | 外部 LDPC 解码器资源；精确上游项目、版本和 URL 未记录 | 未能确定。SOURCES.json 和 readme.txt 只说明它是 DVB-S2 5/6 校验矩阵；标准标识不等于数据文件许可 | 不确定 | 当前板端结果校验路径使用它；先仅本地使用，取得来源与许可或换成有明确授权的矩阵后再随包分发 |
| clients/python/resources/libc_ldpc.so；SHA-256 ce92dcc1026cb4e36b9dd9092c703e428f9ab59e4a4037ca4051e85688cb67a6 | 由仓库 clients/python/c_ldpc_accel.c 按 SOURCES.json 记录的 GCC 命令构建 | MIT。源码属于仓库原创代码，根目录 LICENSE 明确覆盖原创代码和测试 | 可以，随附根目录 MIT 版权和许可文本 | 可随提交分发；保留 MIT 声明。它不是第三方库 |
| clients/python/resources/libgcc_s_seh-1.dll；SHA-256 438ae82ffd621a2413199155574cc85681f8986f05420b1485aa4be936c3bc0b | 从 archive/submission_2025-11-07/演示文件/gui_app.exe 的历史 PyInstaller 包提取；MinGW-w64 GCC 的具体发行版和版本未记录 | 未能确定该二进制实际适用的许可。文件名指向的常见上游条款是 GPL-3.0-or-later 加 GCC Runtime Library Exception 3.1，但这只是检索线索；本仓库没有对应源包、版本号或许可文本 | 不确定 | 当前客户端不加载，建议从对外提交包删除；如仍分发，先取得精确版本的许可、例外文本及对应源代码/源码获取方式 |
| clients/python/resources/libstdc++-6.dll；SHA-256 72ce15df7c50e8d0ca57701b0b37394942e5348654505fcb993873b515dfd1d0 | 从历史 PyInstaller 包提取；MinGW-w64 C++ runtime 的发行版和版本未记录 | 未能确定该二进制的实际许可。常见 GCC libstdc++ 条款为 GPL-3.0-or-later 加 GCC Runtime Library Exception；SOURCES.json 没有能把此 DLL 对应到特定上游构建的证据 | 不确定 | 当前客户端不加载，建议从对外提交包删除；如保留，补齐精确上游版本和对应许可材料后再分发 |
| clients/python/resources/libwinpthread-1.dll；SHA-256 5bbef249a0d00e2d32c699d0bbe89f714ebeb872b3990a5cbeccb1d89f63e5e8 | 从历史 PyInstaller 包提取；MinGW-w64 winpthreads 的发行版和版本未记录 | 未能确定该二进制的实际许可。常见 winpthreads 来源可见 LGPL-2.1-or-later 条款，但此仓库没有对应源包或许可文本，不能据文件名确认 | 不确定 | 当前客户端不加载，建议从对外提交包删除；如保留，核对精确上游版本及 LGPL 履行要求 |
| clients/python/resources/permutation64800；SHA-256 42f751c6d95c782ccaa3171aacf354435f77bc4186e433f52e89827995416742 | 外部 LDPC 解码器资源；SOURCES.json 明确指出精确上游和版本未记录，仓库生成脚本只消费该表 | 未能确定。已查 SOURCES.json、readme.txt 和调用说明，未找到生成器、源项目或许可文件 | 不确定 | 当前板端回传解交织会用到；本地保留，取得可追溯来源与许可或以有明确许可的生成表替换后再随包分发 |

## 3. 板卡手册、原理图、AMD 资料与官方示例

下表中的 PDF 哈希来自各目录已跟踪的 SHA256SUMS。BKB220 两份资料的用户提供时间、字节大小和完整哈希另见 docs/board/bkb220/README.md。

| 素材 | 来源 | 许可判断与依据 | 能否再分发 | 本次处置建议 |
| --- | --- | --- | --- | --- |
| docs/board/bkb220/bkb220-product-manual-v1.1.pdf；SHA-256 40b50e666ecab4ee83fbcfb1eea816a04a0989f73b001d9b9432e4778c8cd086 | 用户于 2026-10-11 提供；没有来源 URL | 未能确定。提取 PDF 全文未检出版权或许可声明；本地也没有厂商许可文件 | 不确定 | 为本地板卡开发留存；对外提交建议以来源说明和必要规格摘录替代原 PDF，取得厂商许可后再附原件 |
| docs/board/bkb220/BK_B220_SchDoc.pdf；SHA-256 fb7947dfa762a58d7e6a178fc612d8ec48a1d05c677e60c357acc0697e8955a6 | 用户于 2026-10-12 提供的 Altium 原理图；没有来源 URL | 未能确定。PDF 提取文本无版权/许可声明，README 只记录来源为用户提供和校验结果 | 不确定 | 为本地板卡开发留存；对外提交建议链接来源或只保留项目需要引用的事实，未获许可前不再分发原理图 |
| （旧板 ZYNQ ECO 7010 资料，2026-10-16 已归档移出仓库）01_board_official/01_zynq_eco_hardware-spec.pdf；SHA-256 967c1019dfd8056c9f218360a758f7132e19ad3f4049fff05fcf80e27906134c | ECO 硬件规格发布页：https://z.shaonianxue.cn/9516.html；原始媒体元数据位于 （旧板 ZYNQ ECO 7010 资料，2026-10-16 已归档移出仓库）00_sources/media_manual_9517.json | 未能确定。提取全文没有找到许可授予或再分发条款；发布页和“官方资料”标签不等于开放许可 | 不确定 | 对外材料用来源链接代替 PDF；只有取得权利人授权后才随包附原件 |
| （旧板 ZYNQ ECO 7010 资料，2026-10-16 已归档移出仓库）01_board_official/02_zynq_eco_r5-schematic.pdf；SHA-256 bbd6b94b3756c578c5f334beec7c32bfabb7146a4b54a36ceb12c584a128491b | R5 原理图发布页：https://z.shaonianxue.cn/9514.html；元数据见 media_r5_9515.json | 未能确定。全文未检出许可/再分发声明 | 不确定 | 以来源链接和项目自身的引脚配置记录替代 PDF；未获许可前不对外分发 |
| （旧板 ZYNQ ECO 7010 资料，2026-10-16 已归档移出仓库）01_board_official/03_zynq_eco_r6-schematic.pdf；SHA-256 03e9072c6f7b9ebc3d8254942d062eb0e61c3a985c6e98334e5a623fb55c29f1 | 元数据链接为 https://admin.shaonianxue.cn/zynq_eco_r6_sch | 未能确定。全文未检出许可/再分发声明；README 未给出单独的权利许可 | 不确定 | 对外提交建议替换为来源链接和项目已验证的板级事实 |
| （旧板 ZYNQ ECO 7010 资料，2026-10-16 已归档移出仓库）02_amd_reference/DS187_XC7Z010-XC7Z020_DC-AC.pdf；SHA-256 61e245380c01d2b9cc1350d529265d185e04c1c0379b0fdb3adcba76585c8dac | AMD/Xilinx DS187 产品规格；本地 README 未记录该 PDF 的精确下载 URL | 版权人可确定：PDF 明示 © 2011–2020 Xilinx, Inc.，并指向 www.xilinx.com/legal.htm#tos；具体许可文本和对本文件的再分发授权未能确定。本次没有打开该外链 | 不确定 | 对外提交优先用 AMD 官方页面链接；未核实该文件条款前，仅本地参考，不随提交包附 PDF |
| （旧板 ZYNQ ECO 7010 资料，2026-10-16 已归档移出仓库）02_amd_reference/DS190_Zynq-7000_Overview.pdf；SHA-256 f5d9257f94fa6140d4a0519a0185e43fea1dc79c806378f24416fdf25c34ff98 | AMD/Xilinx DS190 产品概览；本地 README 未记录该 PDF 的精确下载 URL | 版权人可确定：PDF 明示 © 2012–2018 Xilinx, Inc.，并提及由 Xilinx 许可约束的 IP 核；本地没有授予本仓库再分发权的文本 | 不确定 | 对外提交使用官方链接；未确认 AMD/Xilinx 条款前不随提交包附 PDF |
| （旧板 ZYNQ ECO 7010 资料，2026-10-16 已归档移出仓库）03_examples/eco_led-official-example.zip；SHA-256 d85dfd6490440518d2952ba1eaa666fe97036b8ab989abcb803b4a1c44c176b6 | 官方 LED 示例附件：https://admin.shaonianxue.cn/wp-content/uploads/2022/04/2022041010402381.zip；来源元数据见 media_led_2261.json | 未能确定。只检查压缩包成员清单；包内没有 LICENSE、COPYING、NOTICE 或 README 授权说明。包含 Verilog、XDC、生成 bitstream 和 Vivado 工程输出 | 不确定 | 对外提交建议删除压缩包并保留上游链接；若需要分发源代码，先逐文件确认许可并补齐原始声明 |
| （旧板 ZYNQ ECO 7010 资料，2026-10-16 已归档移出仓库）04_photos/eco_r5-connector-labels.jpg；SHA-256 3a94cd4505da543a832700cd30faf6331fcb05b70a5e91a7b9f2135d99266a1a | ECO 产品资料页 https://z.shaonianxue.cn/product/962.html；图片文件的单独媒体 URL 未记录 | 未能确定。项目 README 将其列为板卡资料图片，没有许可文本；未找到可证明图片授权的记录 | 不确定 | 对外展示改用项目自行拍摄的板卡照片或上游链接；未确认授权前不复制该图 |
| （旧板 ZYNQ ECO 7010 资料，2026-10-16 已归档移出仓库）04_photos/eco-board-intro.png；SHA-256 8496297a716b17d9b27e875f2f243f32fd974702290f087da5d6a81a2b47b39c | ECO 产品资料页 https://z.shaonianxue.cn/product/962.html；图片文件的单独媒体 URL 未记录 | 未能确定。没有独立许可文件或图片授权记录 | 不确定 | 建议用自制图或官方页面链接替代，未确认授权前不随对外提交 |
| docs/submission/competition-guide-2026-fpga-amd.pdf；SHA-256 c6ad82acd4f7bdcd13bd412e232ed85d05f2a87dd5e2cdd04f9d219f88b569fc | 本机未跟踪副本。既有 compliance-notes.md 记录了 D:\下载 下的原始指南路径，但没有公共来源 URL | 未能确定。对本地 PDF 全文检索未找到版权或再分发许可声明；竞赛规则的事实用途不等于对文档原件的再分发许可 | 不确定 | 作为本地竞赛规则核对材料留存；公开提交时优先引用组委会来源链接，原件授权未确定前不主动附入对外包 |

## 4. 图片、历史演示和测试数据

| 素材 | 来源 | 许可判断与依据 | 能否再分发 | 本次处置建议 |
| --- | --- | --- | --- | --- |
| docs/images/images.jpg；SHA-256 ff27ca7faaab60b2d4d30b109f343354dd5bec25e2f83f11fd213ca2b703c265 | 仓库中没有记录该图片的原始来源 URL、作者或制作方式 | 未能确定。没有邻近的来源说明或许可声明，不能由其存放在 docs/ 推断属于原创 | 不确定 | 对外提交前查明来源；查不明时建议替换为项目自行制作的图 |
| docs/images/verification/failed_1060reads.jpg；SHA-256 722a07e2523e41e74fd7bb531df61b7dfbaa49a7150332c87e89103b343af51e；failed_no_rc.jpg；SHA-256 e43f6cd8f8294f191f5269f7ebaad7d2a36ebc1ea10b4eeef6af8a6e152dba1c；recovered_1080reads.jpg 与 recovered_51781reads_rc.jpg 均为 SHA-256 fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3 | 项目验证过程产物；两张 recovered 图逐字节相同，且状态文档将该哈希用作 D0/R0.83 JPEG 恢复判据 | 恢复图可确定为 R0.83 图像内容的逐字节副本；其原图权利来源未记录。失败图也没有单独的授权记录 | 不确定 | 保留在本地验证材料；对外展示可改用不含外部图像内容的示意图，或先确认 D0 原图授权 |
| （旧板 ZYNQ ECO 7010 资料，2026-10-16 已归档移出仓库）03_examples/tutorials/ECO_蜂鸣器上板演示.mp4；SHA-256 bc7135f50bfffa346e0e7bfe2529c1cad6306161d26eac59a3152208c907feab | 本地元数据记录的教程页 https://z.shaonianxue.cn/432.html 和媒体地址 https://admin.shaonianxue.cn/wp-content/uploads/2021/12/1640234875-307186186ede4e2.mp4 | 未能确定。页面/文件中没有可见的再分发许可；README 提到该视频，但 Git 不跟踪此文件 | 不确定 | 当前只是本机未跟踪文件；不要复制进提交包。对外材料保留来源链接即可 |
| tests/datasets/D0_image_mandrill/board_output.bin；SHA-256 a737e816c6f7d2632946c9ce7e143a33f71dc9863cfe3abade9547964ac327a7 | 来自 D0/R0.83 板测；docs/benchmarks/measured_board_multi_payload.md 将其归入 R0.83 数据集 | 未能确定。仓库未记录原始 Mandrill JPEG 的作者、上游数据库、许可或 URL；文件名和图像标签不足以识别授权 | 不确定 | 仅作本地历史对照；确认原图许可前不在新提交包内分发 |
| data/R0.83_data/；本机清单登记 8 个文件，单项 SHA-256 见 data/MANIFEST.md | 来源 URL 和原始数据权利人未在 MANIFEST.md 记录；约 54 MB 原始实验数据 | 未能确定。MANIFEST.md 记录文件与 SHA-256，并说明该目录被 .gitignore 排除；未发现许可或再分发声明 | 不确定 | 只用于本地构建/验证，不随提交；不修改该目录 |
| tests/datasets/D1_binary_pattern/source_payload.bin、D1_random_entropy/source_payload.bin、D1_structured_sparse/source_payload.bin、D1_text_manifesto/source_payload.bin、D2_controlled_noise/source_payload.bin；SHA-256 见对应 manifest.json 和 SHA256SUMS | 由 tools/generate_payload_dataset.py 生成；D1_text_manifesto 的文本内容写在生成器中，其他源载荷为项目生成的二值图案、随机数据或结构化位流 | MIT。仅这些源载荷的素材来源可归为项目原创；根目录 LICENSE 覆盖原创测试内容 | 可以，随附根目录 MIT 许可 | 可随提交分发；继续保留生成器、manifest 和校验清单 |
| 上述 D1/D2 数据集内其余 35 个跟踪文件；SHA-256 见各目录 SHA256SUMS 和 manifest.json | 由项目生成器编码、模拟测序和注入噪声；manifest 指向 tests/datasets/common/watermark.txt | 未能确定。尽管 D1/D2 的源载荷由项目生成，数据集中的序列和测序结果也以来源未确定的 R0.83 水印为输入；其派生结果不能仅凭生成器改列为 MIT | 不确定 | 可保留在仓库用于当前回归；对外分发前先确认 R0.83 水印许可，或改用有明确授权的水印重新生成整套数据和校验摘要 |
| tests/golden/d1_binary_pattern_se150/、d1_random_entropy_se150/、d1_structured_sparse_se150/、d1_text_manifesto_se150/、d2_controlled_noise_se150/；SHA-256 见各目录及 tests/golden/SHA256SUMS | 由项目黄金模型根据 D1/D2 派生数据生成；该链路使用同一份 R0.83 派生水印 | 未能确定。测试向量是项目代码生成，但其中间值可能承载共享水印内容；原始水印的许可未记录 | 不确定 | 保留作本地回归；对外分发前先确认水印许可或用获授权的水印重生成 |
| tests/datasets/common/watermark.txt；SHA-256 be9b7799dff00851263fcf53b2e3aafa4d28b27104f07c2c9adb96f9f156f7eb | tests/datasets/common/README.md 指明它由 data/R0.83_data/Source data/Watermark sequences/r0.83_watermark.txt 规范化生成 | 未能确定。原始水印的来源 URL 与许可没有记录；规范化不会消除上游权利问题 | 不确定 | 本地测试可继续使用；未确认原始水印授权前不随对外提交分发 |
| tests/golden/ 根目录、tests/golden/se250/、tests/golden/ldpc/ 中的 R0.83 基准向量和板测派生文件；SHA-256 见 tests/golden/SHA256SUMS 与 tests/golden/se250/SHA256SUMS | 由 R0.83 数据和历史板测记录生成 | 未能确定。生成器可确定，但源数据许可与原始内容权利未能确定；生成数据不自动获得独立授权 | 不确定 | 只留作本地回归和证据；取得 R0.83 数据许可后再决定是否分发 |

## 5. 构建制品、未跟踪的 BSP 副本与其它依赖

| 素材 | 来源 | 许可判断与依据 | 能否再分发 | 本次处置建议 |
| --- | --- | --- | --- | --- |
| hw/build/export/BOOT.bin；SHA-256 2c2ca645a90643b7fe86b9299a5e29c7195990561455ba5943bb93c7dbd20887；dna_accel.xsa；3b4f79a88773284a1ef3f904857232049451b4e7f7bf3902b6c396e26d35bc02；dna_lwip_app_b27.elf；58d84ad3cb0d0849399ca346d4804567dd1463350115f86b472fe6ad3e35af36；fsbl.elf；7d7c1c78ab252d7a1279acc6f8731553f798f61e54d21fd8b4bf071a1240432a；top_bd_wrapper.bit；fd5c401c288a0cb630c2c57990faeac6506d3807390f225159fb6b7d71ddae06 | hw/build/export/README.md 说明这是旧 ZYNQ ECO/P4 发布基线，由 Vivado/Vitis 和 AMD/Xilinx IP 生成；逐项哈希在同目录 SHA256SUMS | 未能确定整体制品的再分发许可。制品混合项目设计与厂商生成 IP、FSBL/BSP 或工具派生内容；当前目录没有覆盖全部嵌入部分的授权声明 | 不确定 | 当前 Git 已跟踪这些历史制品；本次不改动。对外比赛包建议仅本地构建/验收使用，不额外复制；要发布需按当前 Vitis/Vivado、IP 与 BSP 条款逐项确认 |
| hw/build/<run-id>/workspace/**/libsrc/lwip211_v1_8/src/lwip-2.1.1/ 的本机生成副本；当前扫描到 31 份内容相同的 COPYING，SHA-256 434d4cf7ba9338b06fd42b6bfe2c52301585df7c3a1a7f41a4f9d62ecd69e085 | Vitis 2022.2 生成的本地 BSP 工作区副本；版本路径标注 lwIP 2.1.1 | 可确定为随附 COPYING 文本中的三条件 BSD 风格许可：再分发源码/二进制须保留版权、条件和免责声明，并遵守不以作者名背书的条件。文件没有 SPDX 标识符，因此这里按原文描述，不额外声称 SPDX 代码 | 可以，须随代码/二进制附带该 COPYING 条款 | 这些副本位于被忽略的构建工作区，不随 Git 提交；若以后打包工作区，必须保留 COPYING 和适用声明 |
| hw/build/<run-id>/workspace/**/bsp/**/libsrc/ 与 Vivado 生成仿真库；本机 hw/build 当前约 109,194 个文件，未为整个忽略目录生成哈希清单 | 本地 Vitis/Vivado 2022.2 构建输出；包含 AMD/Xilinx 驱动、BSP 与仿真支持文件 | 未能确定为整个目录建立完整许可映射。搜索常见 LICENSE/COPYING/NOTICE 文件名发现 31 份同一 lwIP COPYING；其余厂商代码须按具体组件和工具许可核对，不能由 lwIP 条款覆盖 | 不确定 | 仅本地构建用，不要整体压缩进对外提交包；若要分发单个 BSP/仿真文件，先按文件来源补充许可清单 |
| archive/；本机历史目录，未被 Git 跟踪，共 19 个文件；逐文件 SHA-256 见第 6 节 | 2025 历史提交包、R0.83 数据压缩包与演示文件；目录中没有第三方许可台账 | 未能确定。目录混有图片、PDF、演示视频、EXE、FASTQ、RAR 与生成结果；没有足以证明第三方素材授权的索引 | 不确定 | 仅历史本机归档，不并入本次对外提交；保留原档案，不在此任务中移动或删除 |

## 6. 本机归档逐文件哈希

archive/ 不在 Git 跟踪范围。下列文件名与 SHA-256 记录的是本机盘点时现状，不构成来源或许可证明。目录中可能同时包含项目原创材料和第三方素材；目前不能据此给整包授予 MIT。

| 文件 | SHA-256 |
| --- | --- |
| archive/R0.83_data_source.rar | 7ed2e5ae978b742892ed79e51b3d4c34efb751ef5f530a774352d1fb60480894 |
| archive/submission_2025-11-07/069a9fb033ef3d47642e6aee8818b9dc.jpg | 4dd9a46272ad353e3f83dc0df4733d274ddd0208419c6a22b826145bc186ec77 |
| archive/submission_2025-11-07/309927374fc5eddde6b97e9cd998e577.png | c4b3bf9ff700363f0d04d03d187db7528fa96680b06e0553322c6fc1c140410b |
| archive/submission_2025-11-07/35f83b5023b881ead7fc1621b3e611c7.jpg | 3d9dffddd7bb8647eff3fd0d964bcb8b3297f25c22656a578e0a8d8b52243e46 |
| archive/submission_2025-11-07/5bcc86f5d3889be808822ea8fe0fe267.png | 48cfc7c9ac5e3d8984286d4266824ff6544648a396a9cc3c3722ea96558d151c |
| archive/submission_2025-11-07/DAN存储读出FPGA实现架构_49030_演示视频.mp4 | 6acef1059f79c1c189dd730f95abcf2fa2ba9f19e4cd970d20ab22fc69e217eb |
| archive/submission_2025-11-07/DNA存储读出FPGA实现架构_49030_承诺书.pdf | 2ec7a24741148e10d6508cc31abe60c0c006a1f2864af1ed4e276171c3e77c39 |
| archive/submission_2025-11-07/DNA存储读出FPGA实现架构_49030_技术文档.pdf | 9242246624c4db143abb4503421d9bee7fd4177d87831d0e89858ed1a3ca8f41 |
| archive/submission_2025-11-07/DNA存储读出FPGA实现架构_49030_海报.pptx | f932cc5c99c13c9b1ed99b05cb440322918596d6d7294728598d2715371aeaaa |
| archive/submission_2025-11-07/DNA存储读出FPGA实现架构_49030_重要代码.rar | 5375d874787eb3418018d1532858a8d5adfe875e32f2153b8df494c9f70c2eec |
| archive/submission_2025-11-07/图片1.jpg | 0987b236e5ba684744aceccab009a9d04da21e31bad07054f98dccc9de44fc0d |
| archive/submission_2025-11-07/微信图片.jpg | 23894fb0edfc0cad1f667bdb36f392d50bbab1e37742b935dfe4fbb4b366fde8 |
| archive/submission_2025-11-07/演示文件/dec_input.txt | 767d194809f9d89f9ba66e9194f198fe472dd32448a69bfc6327b180e2a0d108 |
| archive/submission_2025-11-07/演示文件/decoded_bits.txt | 0a2aa3b514b4b470c80a8affa64a5795dba34bbab134153c3d528c298c40e04f |
| archive/submission_2025-11-07/演示文件/decoded_image.jpg | fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3 |
| archive/submission_2025-11-07/演示文件/gui_app.exe | e4542d6ebeb3cea0107fde9e9aa2d0da84836eee5a0977bb1e676f4b6ec0372f |
| archive/submission_2025-11-07/演示文件/read.fastq | f66503ae9f91ce8980876520e5c93330586cfd2870336cc834b2fab352a37691 |
| archive/submission_2025-11-07/演示文件/result.txt | 767d194809f9d89f9ba66e9194f198fe472dd32448a69bfc6327b180e2a0d108 |
| archive/submission_2025-11-07/演示文件/watermark.txt | 79c64ec4a573b4bf5931653e8d1afd8bd512be0ef6b5b0a3cebf04072a87daed |

## 7. 未覆盖为“可分发”的外部依赖与发现范围

- 已跟踪源码只发现 tests/host/shim/lwip/err.h 与 tcp.h 两个主机侧接口桩；它们是供项目主机测试使用的最小声明，不是 vendored lwIP 实现。未发现跟踪字体文件（TTF/OTF/WOFF）。
- clients/python/requirements.txt 声明 numpy 和 Pillow，但没有将这些第三方 Python 包源码或 wheel vendoring 到仓库；本清单不代表已解析运行时安装包的各自许可。
- 本机 hw/build 和 archive 均有不跟踪内容。它们在 Git 提交中被排除，但不代表把这些目录另行打包时可以再分发。
- 竞赛指南本机有一份未跟踪 PDF 副本，但其官方来源 URL 与再分发条件未记录；厂商额外授权、MinGW 原始发行版和 R0.83 上游来源也仍未核实。本清单不声称已核实这些外部条件。

因此，建议对外提交优先携带项目自制源码、合成测试数据及其 MIT 许可与可复现入口；对外部解码器、LDPC 表、厂商资料、原始数据、历史媒体和预编译硬件制品，先取得明确许可，或用来源链接、项目自制替代物替换。
