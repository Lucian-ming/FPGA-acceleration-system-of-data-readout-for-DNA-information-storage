# -*- coding: utf-8 -*-
"""Narration script — the single source of truth for timing and subtitles.

Each line is one TTS sentence and one subtitle cue.

写作口径（2026-10-30 重写）：
  旁白不复述画面上的字。画面负责给名词与数字，旁白负责给这些名词
  之间的关系、代价、以及为什么必须这样做。凡画面已经写出的数值，
  旁白只在需要解释其含义时才复述一遍。

事实边界：
  - PL 内是四级流水（Stage1/2/3 + LDPC）；Stage 2.5 的水印异或跑在 PS
    的板载 ARM 上；PC 只做验收，不复算码字。docs/01-architecture.md:32-50
  - 校验子由客户端在本地对回传码字重算，不是板端回传的校验位。
    clients/python/ldpc_pipeline.py:131-133
  - LDPC 信息位是 deinterleave 之后的末段 natural[PARITY_COLS:]。
    clients/python/ldpc_pipeline.py:167-175
  - P4/P16/K=2/最终配置 的计时口径是板端结果段 t_result，不是整机端到端；
    5.1 s 是定版口径的约数。docs/09-evidence-ledger.md:237
"""

VOICE = "zh-CN-YunyangNeural"   # 新闻播报腔，适合技术演示
RATE = "-22%"

SCENES = [
    {
        "id": "s1",
        "title": "问题",
        "lines": [
            "DNA 存储把比特写进碱基，一个碱基两位。",
            "测序只给一段 150 碱基的短读，还带错。",
            "先定位，再投票还原。",
        ],
    },
    {
        "id": "s2",
        "title": "流水线总览",
        "lines": [
            "PL 里四级流水，水印在 PS 补，验收在 PC。",
            "级间只传定长记录，接口窄才验证得动。",
        ],
    },
    {
        "id": "s3",
        "title": "一级：滑窗比对",
        "lines": [
            "比对在比特域做，碱基先按 2 比特展开。",
            "参考串不动，读出整段扫过去，步长是一。",
            "300 位逐位比，对上记一分，满分 150。",
            "零噪声才满，真实峰谷只差十几分。",
            "选路树五拍出最高分，位置与分数一起下传。",
        ],
    },
    {
        "id": "s4",
        "title": "二级：差分投票",
        "lines": [
            "投票把十万条记录叠成八万一千位。",
            "两层是同批碱基的高低比特，不是备份。",
            "噪声正负相消，信号逐轮累积。",
            "累加器整条任务不清零，门限 67 挡住低分。",
            "水印异或在 PS 上做，字节内低位优先。",
        ],
    },
    {
        "id": "s5",
        "title": "三级：5 比 4 解稀",
        "lines": [
            "解稀压的是码本冗余，不是数据。",
            "五位只有十六种合法模式，非法直接判错。",
            "码长缩两成，给纠错腾出校验位。",
        ],
    },
    {
        "id": "s6",
        "title": "LDPC 纠错",
        "lines": [
            "纠错用 DVB-S2 短码，参数写死在硬件里。",
            "消息整批刷新，硬判决不看置信度。",
            "校验子只数没满足的方程，全零才收。",
            "五十轮不收敛就原样上报，拒收是设计。",
        ],
    },
    {
        "id": "s7",
        "title": "客户端验收",
        "lines": [
            "校验子本地重算，摘要覆盖全文件。",
            "每级都留中间结果，失败能定位。",
        ],
    },
    {
        "id": "s8",
        "title": "实测结果",
        "lines": [
            "计时只算板端结果段，不含上传。",
            "26.5 秒压到 5.1 秒，上传从 4.27 秒到 0.40 秒。",
            "42 例零静默错误，长稳 262 轮无失败。",
        ],
    },
    {
        "id": "s9",
        "title": "收束",
        "lines": [
            "每一步都留下可核对的中间结果。",
            "四级在 PL，水印在 PS，验收在 PC。",
        ],
    },
]

# Extra hold time after the last line of each scene, so animations can land.
TAIL = {
    "s1": 0.7, "s2": 0.5, "s3": 0.6, "s4": 0.6, "s5": 0.6,
    "s6": 0.7, "s7": 0.5, "s8": 0.7, "s9": 1.5,
}
# Silence before the first line of each scene.
LEAD = {k: 0.45 for k in ("s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9")}
LEAD["s1"] = 0.9
LEAD["s9"] = 0.6
# Gap between consecutive lines inside a scene.
GAP = 0.24
