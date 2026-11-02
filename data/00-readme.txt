DNA 测试集（v2）—— 42 个用例，用于客户端全流程测试
=========================================================
来源：项目配套数据集 dna-multimedia-simulation-v2-20261013
随包位置：data/（42 个用例目录直接平铺在本目录下）


一、这里有什么
--------------
42 个用例 = 21 个资产 × {baseline, challenge}

  01_peppers ... 18_blue_sky   图像 / 音频 / 视频类（18 个资产）
  19_utf8_text                 文本类
  20_numeric_signal            数值信号类
  21_random_binary             随机二进制类

每个用例一个目录，里面有：

  read.fastq        读段数据
  watermark.txt     该资产对应的水印
  expected.txt      这一例的期望载荷 SHA-256、score_min、以及软件侧结果
  reference.jpg     软件侧译出来的结果，供肉眼比对
                    （图像类是真的 JPEG；19/20/21 是别的载荷，只是沿用这个扩展名）

顶层 00-index.tsv 是全部 42 例的汇总表：目录、资产、类别、期望 SHA、score_min、软件侧结果。
逐资产的来源 URL、许可说明与载荷哈希见同目录 sources.json。


二、怎么用
----------
客户端入口见 src/clients/；Python 依赖见 src/clients/python/requirements.txt。

1. 启动客户端，等窗口出来（第一次要 5~15 秒）。
2. 在客户端里点【浏览】，把
      水印文件  → 选某个用例目录里的  watermark.txt
      读段文件  → 选同一个用例目录里的  read.fastq
   （**水印和读段必须来自同一个用例目录**，配错了哈希必然不对）
3. 板端 IP/端口 保持 192.168.1.10 : 7。
4. 点【开始】。约 10 秒出结果。
5. 把界面上显示的哈希，与那一例 `expected.txt` 里的 SHA **逐字符比对**。


三、判读规则（重要）
--------------------
· **34 例是"应当通过"的**：哈希应当与期望值**一字不差**。
· **8 例是"预期失败"的**，它们在目录名和 `expected.txt` 里都标了：

      02_mandrill_challenge    03_tree_challenge      05_moon_challenge
      09_grass_challenge       11_beach_sand_challenge
      15_sea_waves_challenge   16_water_drops_challenge  19_utf8_text_challenge

  这 8 例在**软件侧**是记录在案的失败例——硬判决 LDPC 跑满 50 轮不收敛，
  软件自己也译不出来，所以**没有"应当得到"的正确哈希**。

  ⚠️ 板端是**另一套算法**（min-sum，不是软件那套比特翻转），**有可能把它们纠回来**：
      · 板上若纠回来了 → 得到一个能显示的图，是好结果；
      · 板上若也没纠回 → 板上会**保留原样发回**，哈希与期望值不同，**这是预期行为**，
        不是操作失误也不是板子坏了。

  换句话说：**这 8 例不能当"失败判据"用，只能当"看板端能不能多救回来几个"的观察项。**


四、耗时参考
------------
每个用例约 10 秒（板上约 6 秒）。42 例依次跑完约 7~8 分钟。
想快速冒烟，先跑 `01_peppers_baseline`（最简单、一定要过）。


五、来源与许可
--------------
· 01–12 图像：USC-SIPI Image Database（Misc / Textures），
  版权状态按其官方说明 https://sipi.usc.edu/database/copyright.php，
  **并非全部属于公有领域**。
· 13–16 音频：ESC-50（https://github.com/karolpiczak/ESC-50），
  整包为 CC BY-NC，ESC-10 子集为 CC BY；不得称为无条件商用。
· 17–18 视频：Xiph Derf 媒体库（https://media.xiph.org/video/derf/），
  逐片段可能另有说明。
· 19–21：项目自行合成的载荷，适用仓库根 license（MIT）。
逐项 URL、许可链接与载荷 SHA-256 见 sources.json。


六、如实说明的边界
------------------
· 这些数据是**仿真生成**的（in-silico），不是真实测序数据；它们证明的是
  编解码链路，不是生物学真实性。
· "期望 SHA" 来自数据集自带的 `validation.json`，是数据集**自己的软件解码器**
  算出来的；板端跑出来应当与它相同。板端整体验收仍以三层判据
  （架构 syndrome 全零 + 系统载荷 SHA）为准，见设计报告。
