# -*- coding: utf-8 -*-
"""Regenerate the per-line tables in narration.md from build/timeline.json.

The prose sections (画面性质 / 材料冲突 / 术语口径) live in TAIL below and are
kept verbatim, so the tables can never drift from the measured TTS timing.

    python3 src/gen_narration.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(ROOT, "build")

CN_NUM = "一二三四五六七八九"

TAIL = """
---

## 画面性质：哪些是实测、哪些是示意

分三类，避免把原理图当成测量结果读：

**A. 项目报告给出的数值（照抄，不改写）**
SE150（150 bp = 300 bit，2 bit/碱基）；参考串 40,500 符号 = 81,000 bit；50 段 × 957 bp、步距 807、重叠 150；
候选起点 0..40,350（40,351 个）；输入 103,616 条记录（= 51,781 × 2 + 54 条对齐填充）；
第一批 64 条读出；16 窗口 / 周期；累加器 −512..+511；判决 `vote > 0 → 1`；得分门限 67；
Stage 3 码本重量 ≤ 2、81,000 → 64,800 bit = 8,100 B、1,013 拍 × 64 bit；
LDPC DVB-S2 R=5/6、64,800 = 54,000 + 10,800；载荷上限 6,750 B；
42 用例 26 PASS / 16 SAFE_NOCONV / 0 静默错误；
P4 26.5 s → P16 8.95 s（2.97×）→ K=2 6.06 s → 最终 ≈5.1 s；上传 4.27 s → 0.40 s（≈10.7×）；
连续运行 2 h / 262 轮 / 0 失败（2026.1 制品）。

**B. 由画面显示的数值直接算出来的（可复核）**
- 2.97× = 26.5 / 8.95；≈10.7× = 4.27 / 0.40；≈5.2× 核心加速 = 26.5 / 5.1。
- 每层 40,500 × 2 = 81,000；81,000 / 5 × 4 = 64,800；64,800 / 8 = 8,100 B；64,800 / 64 = 1,013 拍。

**C. 纯原理示意（画面里都打了「示意」标签）**
- S1 的双螺旋、碎片序列与错配位置：示意，不是真实读出文件。
- S3 的得分曲线形状、逐位 `+1/+0`、16 窗口的具体得分值（58/61/…/74）：示意；
  只有「噪声 59–62」「峰值典型值 ≈75」「满分 150」三个数字来自项目报告。
- S4 的累加器动画、S5 的码本与异或门、S6 的小 Tanner 图（6 变量 / 4 校验）
  与逐轮校验子条柱：示意，不是实测迭代序列，也不是实际校验矩阵。
- S8 的条长按对数刻度映射，条旁标注的才是实测秒数。

## 材料冲突（未擅自改口径，仅记录）

1. **Stage 4 LDPC 在哪一侧做。**
   `docs/08-performance-and-strategy.md`（:38、:113）与
   `docs/reference/ldpc-onchip-handoff-2026-10-14.md`（:58）仍写着「上位机 LDPC 0.653 s」，
   并把「LDPC 与下一轮重叠」列为待办；而 `docs/01-architecture.md`（27、35–36、48、160–170 行）
   写明 Stage 4 LDPC 在 PL 上（`ldpc_decoder_0`），上位机只校验校验子与提取载荷，没有 PC 端译码兜底。
   视频按 `docs/01` 的现架构讲（S6「纠错在 PL 上做」、S7 上位机只做双判据），
   0.653 s 这一条没有进片；`docs/08` 是未更新的旧记录。
2. **2 小时长稳轮数。** `docs/09` :210 记 274 轮（较早的 P16 包），:266 记 262 轮（2026.1 制品）。
   两次是不同的运行，视频用 262，对应 2026.1 制品，不与 274 混用。
3. **历史长稳不入片（按作者要求）。** 早期 v1.1 的 8 小时长稳（1,736 轮）与更早的
   1,750 轮记录都属旧版本，视频只呈现最终版制品的 2 小时 / 262 轮，不再并列历史版本，
   也不做任何跨版本累加。
4. **6,624 B 与 6,750 B。** `docs/01` 的参考载荷 `Milk coronet.jpg` 是 6,624 B；
   6,750 B 是 54,000 bit 信息位换算出的**载荷上限**。性能矩阵跑的是 6,624 B 的原始载荷，
   所以 S8 的坐标轴写 6,624 B，S2/S7 的上限仍写 6,750 B，两者不是同一件事。
5. **计时口径。** P4/P16/K=2 的数字来自 `t_result` 中位数
   （POST 发出 → 8,100 B 收齐，**不含**上传与 LDPC），见
   `docs/benchmarks/bkb220-p4-p16-performance-matrix.md:58`；
   它不是端到端墙钟，S8 的标题按这个口径写。
6. **5.1 s 是定版口径的约数。** `docs/09` :237 记录的是最终配置的板端结果段；
   视频沿用项目自己的定版表述「约 5.1 s / 5.2×」，不与 5,148 ms、4.92 s 等其它场次混用。

## 术语口径

- Stage 1 的分数一律叫「得分 / 匹配得分（0..150）」，不叫「相关系数」。
- Stage 2 的 81,000 bit 是**两个 40,500 位的位平面（A / B）**，不是两份副本、不是交织。
- LDPC 是**硬判决** Flooding Min-Sum，不讲软信息、不提 BCH。
- 校验子**每轮重算，可能波动**，不接受「单调下降」的说法。
- 不收敛 = 保留 Stage 3 码字交回 + 上位机拒绝 → `SAFE_NOCONV`，不算错误。
- 板载 ARM（PS）不是上位机；上位机只指 PC 侧。
- PL 内是**四级**流水（Stage 1/2/3 + LDPC）；Stage 2.5 水印异或在 PS。不写「三级硬件流水」。
"""


def main():
    d = json.load(open(os.path.join(BUILD, "timeline.json")))
    total = d["total"]
    nlines = d["lines"]
    out = ["# 旁白稿与逐句时间表", ""]
    out.append("成片：`dna-readout-explainer.mp4`，%.2f s（时间轴 %.3f s），%d 句旁白 / %d 个场景。"
               % (total, total, nlines, len(d["scenes"])))
    out += ["", "- 语音：edge-tts `%s`，语速 `%s`。" % ("zh-CN-YunyangNeural", "-22%")]
    out.append("- 时间来自 TTS 实测时长（`src/script.py` → `build/timeline.json`），"
               "字幕与画面都以它为准。")
    out.append("- 下表 `起始` 是全局绝对秒（与画面、字幕同一坐标系）。")
    out += ["", "读法：`起始` / `时长` 来自 `build/timeline.json` 的 `lines[i].start` / `dur`。",
            "总表由 `src/gen_narration.py` 生成，不要手改数字。", ""]

    for si, sc in enumerate(d["scenes"]):
        a = sc["start"]
        b = a + sc["dur"]
        out += ["## %02d %s（%.3f – %.3f s）" % (si + 1, sc["title"], a, b), "",
                "| # | 起始 | 时长 | 旁白 |", "|---|---|---|---|"]
        for ln in sc["lines"]:
            out.append("| %d | %.2f | %.2f | %s |"
                       % (ln["index"] + 1, ln["start"], ln["dur"], ln["text"]))
        out.append("")

    out.append(TAIL.strip("\n"))
    out.append("")
    path = os.path.join(ROOT, "narration.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print("wrote %s  (%.2f s, %d lines)" % (path, total, nlines))


if __name__ == "__main__":
    main()
