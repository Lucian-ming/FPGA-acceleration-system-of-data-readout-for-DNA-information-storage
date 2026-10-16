#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""现代化工业级 DNA 读出加速系统上位机客户端 (Tkinter/TTK GUI)。

系统交互与协议映射架构（docs/05 §C1）：
=============================================================================
1. 定位与职责：
   本 GUI 是比赛现场演示（Demo）与工业化控制台的统一入口，将底层复杂的 TCP 自定义
   二态协议与多级流水线抽象为对用户友好的全流程控制界面。
2. 五段式流水线与板端协议交互对应关系：
   - CONFIG: 任务配置握手。向板端下发 PKT_CONFIG，传递 read_bps（150/250）、
             num_reads、score_min 等参数，校验板端返回的 0 成功码与 CAPS 能力；
   - WM:     水印预载。将 10,125 字节水印流（PKT_WM）下发至板端 DDR 并预载进 Stage1 BRAM；
   - UPLOAD: 读段上传。调用 first.py 将 FASTQ/FASTA 碱基解析并打包为 40B/64B 二进制
             块（PKT_BATCH），按批次流式写入板端接收 FIFO 与 DDR 缓冲区；
   - POST:   启动流水线。下发 PKT_POST 触发硬件加速执行，轮询阻塞等待板端完成 Stage1/2/3
             计算并回传 8,100 字节的 Stage3 反稀疏化码字流（PKT_RESULT）；
   - LDPC:   FPGA 片上 LDPC 完成纠错并回传码字；PC 只检查 syndrome 并提取载荷，
             不执行译码，也不在板端未收敛时兜底。
3. 演示与闭环验证：
   - 对板端已纠正码字提取出的载荷计算 SHA-256，并与 R0.83 黄金载荷比较；
   - 现场呈现图像预览或非图像文件信息、吞吐率与各级耗时指标。
=============================================================================
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import Callable, Dict, Optional, Tuple

import numpy as np

# 确保脚本所在目录位于模块搜索路径首位，方便引用同级模块
CLIENTS_PY_DIR = Path(__file__).resolve().parent
if str(CLIENTS_PY_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENTS_PY_DIR))

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter.scrolledtext import ScrolledText
except ImportError as exc:
    print(
        "[ERROR] 未检测到 Tkinter 图形界面运行库！\n"
        "  - 若在 Linux/WSL 环境下，请运行: sudo apt update && sudo apt install -y python3-tk\n"
        "  - 若在 Windows 环境下，请确保 Python 安装时勾选了 'tcl/tk and IDLE'。\n"
        f"详细异常: {exc}",
        file=sys.stderr,
    )
    sys.exit(1)

from first import (
    ClientConfig,
    MAX_TOTAL_READS,
    OperationCancelled,
    PIPELINE_STAGE_TOKENS,
    ProgressCallbacks,
    ReadFileInfo,
    analyze_reads_file,
    estimate_processing_time,
    format_metric_report,
    run_client,
)
from ldpc_pipeline import BoardCodeRejected, BoardVerifyResult, verify_board_result
from native_ldpc import MAX_PAYLOAD_BYTES, PayloadGuess, infer_payload
from task_protocol import SUPPORTED_READ_BASES, default_score_min

from ui_theme import (
    COLOR_BORDER,
    COLOR_BORDER_LIGHT,
    COLOR_CARD_ALT,
    COLOR_CARD_BG,
    COLOR_DANGER,
    COLOR_DANGER_BG,
    COLOR_DANGER_BORDER,
    COLOR_DANGER_HOVER,
    COLOR_DANGER_TEXT,
    COLOR_HEADER_BG,
    COLOR_INFO,
    COLOR_INFO_BG,
    COLOR_PRIMARY,
    COLOR_PRIMARY_BG,
    COLOR_PRIMARY_BORDER,
    COLOR_PRIMARY_HOVER,
    COLOR_SUCCESS,
    COLOR_SUCCESS_BG,
    COLOR_SUCCESS_BORDER,
    COLOR_SUCCESS_TEXT,
    COLOR_TEXT_MUTED,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_WARNING,
    COLOR_WARNING_BG,
    COLOR_WARNING_TEXT,
    COLOR_WINDOW_BG,
    LOG_TAG_COLORS,
    LOG_TERMINAL_BG,
    LOG_TERMINAL_FG,
    LOG_TERMINAL_SELECT,
    STEP_PALETTE,
    FontRegistry,
    RoundedButton,
    RoundedCard,
    RoundedMetricTile,
    RoundedPill,
    RoundedStatusBanner,
    apply_modern_theme,
    center_window,
    draw_rounded_rect,
)

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

# R0.83 黄金载荷哈希常数
GOLDEN_PAYLOAD_SHA256 = "fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3"

PIPELINE_STAGES = [
    ("CONFIG", "1. 任务配置"),
    ("WM", "2. 水印预载"),
    ("UPLOAD", "3. 读段上传"),
    ("POST", "4. FPGA 加速"),
    ("LDPC", "5. 片上 LDPC（板端）"),
]
assert tuple(token for token, _ in PIPELINE_STAGES) == PIPELINE_STAGE_TOKENS


def detect_payload_media_type(payload: bytes) -> str:
    """根据载荷魔数识别常见媒体；无法确认时返回 binary。"""
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if payload.startswith(b"BM"):
        return "image/bmp"
    if payload.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if payload.startswith(b"RIFF") and payload[8:12] == b"WAVE":
        return "audio/wav"
    if payload.startswith(b"ID3") or (
        len(payload) >= 2 and payload[0] == 0xFF and payload[1] & 0xE0 == 0xE0
    ):
        return "audio/mpeg"
    if payload.startswith(b"OggS"):
        return "audio/ogg"
    if payload.startswith(b"fLaC"):
        return "audio/flac"
    if payload[4:8] == b"ftyp":
        return "video/mp4"
    if payload.startswith(b"RIFF") and payload[8:12] == b"AVI ":
        return "video/avi"
    if payload.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm-or-matroska"
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return "binary"
    if text and all(char.isprintable() or char in "\t\r\n" for char in text):
        return "text"
    return "binary"


class DNAAcceleratorApp(tk.Tk):
    """工业级 DNA 加速系统控制台主窗口 (现代化柔和圆角视觉与交互系统)。"""

    def __init__(self) -> None:
        super().__init__()
        self.title("FPGA DNA 数据读出硬件加速系统 - 工业控制台")

        # 运行时状态 ----------------------------------------------------
        self._defaults = ClientConfig()
        self._worker: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._log_queue: Queue[str] = Queue()

        self._read_info: Optional[ReadFileInfo] = None
        self._last_verify_result: Optional[BoardVerifyResult] = None
        self._preview_photo: Optional["ImageTk.PhotoImage"] = None
        self._start_time: float = 0.0
        self._is_running: bool = False
        self._board_wait_started_at: Optional[float] = None
        self._expected_hw_seconds: float = 0.0

        # Tk 变量 -------------------------------------------------------
        self.ip_var = tk.StringVar(value=self._defaults.ip)
        self.port_var = tk.StringVar(value=str(self._defaults.port))
        self.conn_status_var = tk.StringVar(value="未检测连接")

        self.watermark_var = tk.StringVar(value=str(self._defaults.watermark))
        self.reads_var = tk.StringVar(value=str(self._defaults.reads))
        self.output_var = tk.StringVar(value=str(self._defaults.out))
        self.input_bytes_var = tk.StringVar(value="")
        self.dev_mode_var = tk.BooleanVar(value=False)

        # 几何与参数
        self.geom_mode_var = tk.StringVar(value="auto")
        self.score_min_var = tk.StringVar(value="auto")
        self.orient_var = tk.StringVar(value="both")
        self.batch_var = tk.StringVar(value=str(self._defaults.batch))
        self.send_count_var = tk.IntVar(value=self._defaults.total or 4096)
        self.full_scale_var = tk.BooleanVar(value=False)

        self.skip_wm_var = tk.BooleanVar(value=False)
        self.post_var = tk.BooleanVar(value=True)

        # 探测与自适应看板
        self.spec_badge_var = tk.StringVar(value="等待选择测序文件...")
        self.est_time_var = tk.StringVar(value="--")

        # 流水线与指标
        self.status_var = tk.StringVar(value="就绪")
        self.active_stage_var = tk.StringVar(value="")
        self.upload_percent_var = tk.StringVar(value="0%")
        self.upload_hint_var = tk.StringVar(value="等待开始任务")
        self.timer_var = tk.StringVar(value="00:00")

        # 毫秒级指标度量
        self.metric_upload_var = tk.StringVar(value="--")
        self.metric_fpga_var = tk.StringVar(value="--")
        self.metric_verify_var = tk.StringVar(value="--")
        self.metric_total_var = tk.StringVar(value="--")
        self.payload_hash_var = tk.StringVar(value="--")

        # 步进器标题缓存
        self._step_titles: Dict[str, str] = {token: title for token, title in PIPELINE_STAGES}

        # 现代化主题、字体注册与高分屏居中初始化
        self.fonts: FontRegistry = apply_modern_theme(self)
        center_window(self, width=1240, height=860)

        # 界面构建
        self._build_ui()
        self._process_log_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # 启动后尝试探测默认文件
        self.after(300, self._auto_detect_default_reads)

    def _build_ui(self) -> None:
        """构建整体用户界面布局。"""
        container = ttk.Frame(self, style="Window.TFrame", padding=10)
        container.pack(fill="both", expand=True)

        # 顶部品牌标头栏
        self._build_header_bar(container)

        # 左右分栏面板
        paned = ttk.PanedWindow(container, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # 左侧控制面板 (权重 3)
        left_frame = ttk.Frame(paned, style="Window.TFrame", padding=4)
        paned.add(left_frame, weight=3)

        # 右侧结果与监控面板 (权重 4)
        right_frame = ttk.Frame(paned, style="Window.TFrame", padding=4)
        paned.add(right_frame, weight=4)

        # 构建左侧各功能卡片
        self._build_conn_card(left_frame)
        self._build_files_card(left_frame)
        self._build_params_card(left_frame)
        self._build_action_card(left_frame)

        # 构建右侧各监控卡片
        self._build_pipeline_card(right_frame)
        self._build_preview_card(right_frame)
        self._build_log_card(right_frame)

        # 确保初始分栏比例协调 (左侧 ~490px, 右侧充分展示流水线与日志)
        self.after(50, lambda: paned.sashpos(0, 490))

    def _build_header_bar(self, parent: ttk.Frame) -> None:
        """顶部现代化系统标头栏，展现产品标识与实时总览状态。"""
        header_card = RoundedCard(
            parent,
            title="",
            radius=12,
            bg_color=COLOR_HEADER_BG,
            border_color=COLOR_BORDER_LIGHT,
            auto_height=True,
            padding=10,
        )
        header_card.pack(fill="x", pady=(0, 8))

        inner = header_card.inner

        # 左侧标题与副标题
        left_box = tk.Frame(inner, bg=COLOR_HEADER_BG)
        left_box.pack(side="left")

        title_lbl = tk.Label(
            left_box,
            text="FPGA DNA 数据读出硬件加速系统",
            bg=COLOR_HEADER_BG,
            fg=COLOR_TEXT_PRIMARY,
            font=self.fonts.app_title,
        )
        title_lbl.pack(anchor="w")

        sub_lbl = tk.Label(
            left_box,
            text="上位机控制台 | SE150 / SE250 双几何自适应流水线 · 软硬件全流程闭环验证",
            bg=COLOR_HEADER_BG,
            fg=COLOR_TEXT_SECONDARY,
            font=self.fonts.caption,
        )
        sub_lbl.pack(anchor="w")

        # 右侧状态徽章 (柔和圆角胶囊组件)
        right_box = tk.Frame(inner, bg=COLOR_HEADER_BG)
        right_box.pack(side="right", fill="y")

        self.top_status_badge = RoundedPill(
            right_box,
            text="系统就绪",
            bg_color=COLOR_CARD_ALT,
            fg_color=COLOR_TEXT_SECONDARY,
            border_color=COLOR_BORDER_LIGHT,
            font=self.fonts.body_bold,
            radius=10,
            height=28,
            width=116,
        )
        self.top_status_badge.pack(side="right", padx=(8, 0))

        profile_badge = RoundedPill(
            right_box,
            text="R0.83 Baseline",
            bg_color=COLOR_PRIMARY_BG,
            fg_color=COLOR_PRIMARY,
            border_color=COLOR_PRIMARY_BORDER,
            font=self.fonts.caption_bold,
            radius=10,
            height=28,
            width=110,
        )
        profile_badge.pack(side="right")

    # ------------------------------------------------------------- 左侧构建
    def _build_conn_card(self, parent: ttk.Frame) -> None:
        card = RoundedCard(parent, title="板端连接配置", radius=10, title_font=self.fonts.card_header)
        card.pack(fill="x", pady=(0, 6))

        row1 = ttk.Frame(card.inner)
        row1.pack(fill="x")

        ttk.Label(row1, text="IP 地址:").pack(side="left")
        ttk.Entry(row1, textvariable=self.ip_var, width=15).pack(side="left", padx=(4, 10))

        ttk.Label(row1, text="端口:").pack(side="left")
        ttk.Entry(row1, textvariable=self.port_var, width=7).pack(side="left", padx=(4, 10))

        RoundedButton(
            row1,
            text="测试连接",
            command=self._test_connection,
            bg_color=COLOR_CARD_ALT,
            hover_color=COLOR_PRIMARY_BG,
            fg_color=COLOR_TEXT_PRIMARY,
            border_color=COLOR_BORDER_LIGHT,
            radius=6,
            width=80,
            height=28,
            font=self.fonts.body,
        ).pack(side="left", padx=(0, 6))

        self.conn_badge = RoundedPill(
            row1,
            text="未检测连接",
            bg_color=COLOR_CARD_ALT,
            fg_color=COLOR_TEXT_SECONDARY,
            border_color=COLOR_BORDER_LIGHT,
            font=self.fonts.caption,
            radius=8,
            height=26,
            width=92,
        )
        self.conn_badge.pack(side="left", padx=2)

    def _build_files_card(self, parent: ttk.Frame) -> None:
        card = RoundedCard(parent, title="数据源与自适应探测", radius=10, title_font=self.fonts.card_header)
        card.pack(fill="x", pady=(0, 6))

        # 文件选择网格
        grid = ttk.Frame(card.inner)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)

        self._add_file_row(grid, 0, "水印序列", self.watermark_var, self._choose_watermark)
        self._add_file_row(grid, 1, "测序 Reads", self.reads_var, self._choose_reads)
        self._add_file_row(grid, 2, "输出目录", self.output_var, self._choose_output)

        # 探测结果现代柔和圆角横幅
        badge_box = RoundedCard(
            card.inner,
            title="",
            radius=8,
            bg_color=COLOR_PRIMARY_BG,
            border_color=COLOR_PRIMARY_BORDER,
            auto_height=True,
            padding=8,
        )
        badge_box.pack(fill="x", pady=(8, 0))
        badge_inner = badge_box.inner
        badge_inner.columnconfigure(1, weight=1)

        tk.Label(
            badge_inner,
            text="数据规格:",
            bg=COLOR_PRIMARY_BG,
            fg=COLOR_PRIMARY,
            font=self.fonts.body_bold,
        ).grid(row=0, column=0, sticky="w", padx=(6, 4), pady=(4, 2))

        tk.Label(
            badge_inner,
            textvariable=self.spec_badge_var,
            bg=COLOR_PRIMARY_BG,
            fg=COLOR_PRIMARY,
            font=self.fonts.body_bold,
        ).grid(row=0, column=1, sticky="w", padx=4, pady=(4, 2))

        tk.Label(
            badge_inner,
            text="预计硬件耗时:",
            bg=COLOR_PRIMARY_BG,
            fg=COLOR_TEXT_SECONDARY,
            font=self.fonts.caption,
        ).grid(row=1, column=0, sticky="w", padx=(6, 4), pady=(0, 4))

        tk.Label(
            badge_inner,
            textvariable=self.est_time_var,
            bg=COLOR_PRIMARY_BG,
            fg=COLOR_TEXT_PRIMARY,
            font=self.fonts.caption_bold,
        ).grid(row=1, column=1, sticky="w", padx=4, pady=(0, 4))

        btn_box = tk.Frame(badge_inner, bg=COLOR_PRIMARY_BG)
        btn_box.grid(row=0, column=2, rowspan=2, sticky="e", padx=(8, 4))
        RoundedButton(
            btn_box,
            text="重新探测",
            command=self._manual_detect_reads,
            bg_color=COLOR_CARD_BG,
            hover_color=COLOR_PRIMARY_BG,
            fg_color=COLOR_PRIMARY,
            border_color=COLOR_PRIMARY_BORDER,
            radius=6,
            width=76,
            height=28,
            font=self.fonts.caption_bold,
        ).pack(side="right")

    def _build_params_card(self, parent: ttk.Frame) -> None:
        card = RoundedCard(parent, title="自适应流水线参数", radius=10, title_font=self.fonts.card_header)
        card.pack(fill="x", pady=(0, 6))

        dev_mode_bar = ttk.Frame(card.inner)
        dev_mode_bar.pack(fill="x", pady=(0, 4))
        ttk.Checkbutton(
            dev_mode_bar,
            text="开发模式",
            variable=self.dev_mode_var,
            command=self._on_toggle_dev_mode,
        ).pack(side="left")

        g = ttk.Frame(card.inner)
        self._params_grid = g
        g.pack(fill="x")
        g.columnconfigure(1, weight=1)
        g.columnconfigure(3, weight=1)

        # 几何模式与读长
        geom_label = ttk.Label(g, text="几何规格:")
        geom_label.grid(row=0, column=0, sticky="w", pady=4)
        geom_cb = ttk.Combobox(
            g,
            textvariable=self.geom_mode_var,
            values=["auto (自适应)", "150 (SE150)", "250 (SE250)"],
            state="readonly",
            width=14,
        )
        geom_cb.grid(row=0, column=1, sticky="w", padx=(4, 8), pady=4)
        geom_cb.bind("<<ComboboxSelected>>", self._on_geom_changed)

        # 匹配阈值
        score_label = ttk.Label(g, text="分数阈值:")
        score_label.grid(row=0, column=2, sticky="w", pady=4)
        sbox = ttk.Frame(g)
        sbox.grid(row=0, column=3, sticky="w", padx=4, pady=4)
        ttk.Entry(sbox, textvariable=self.score_min_var, width=8).pack(side="left")
        RoundedButton(
            sbox,
            text="推荐",
            command=self._apply_recommended_score,
            bg_color=COLOR_CARD_ALT,
            hover_color=COLOR_PRIMARY_BG,
            fg_color=COLOR_TEXT_PRIMARY,
            border_color=COLOR_BORDER_LIGHT,
            radius=6,
            width=46,
            height=26,
            font=self.fonts.caption,
        ).pack(side="left", padx=2)

        # 测序方向与批大小
        orient_label = ttk.Label(g, text="测序方向:")
        orient_label.grid(row=1, column=0, sticky="w", pady=4)
        orient_cb = ttk.Combobox(
            g,
            textvariable=self.orient_var,
            values=["both (正反双向-必需)", "forward (仅正向)"],
            state="readonly",
            width=14,
        )
        orient_cb.grid(row=1, column=1, sticky="w", padx=(4, 8), pady=4)
        orient_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_estimate())

        batch_label = ttk.Label(g, text="传输批大小:")
        batch_label.grid(row=1, column=2, sticky="w", pady=4)
        batch_entry = ttk.Entry(g, textvariable=self.batch_var, width=8)
        batch_entry.grid(row=1, column=3, sticky="w", padx=4, pady=4)

        # 发送条数与全量选择
        ttk.Label(g, text="发送条数:").grid(row=2, column=0, sticky="w", pady=4)
        cnt_box = ttk.Frame(g)
        cnt_box.grid(row=2, column=1, sticky="w", padx=(4, 8), pady=4)
        self.send_spin = ttk.Spinbox(
            cnt_box,
            from_=1,
            to=MAX_TOTAL_READS,
            textvariable=self.send_count_var,
            width=8,
        )
        self.send_spin.pack(side="left")
        self.send_spin.bind("<KeyRelease>", lambda e: self._refresh_estimate())
        self.send_spin.bind("<<Increment>>", lambda e: self._refresh_estimate())
        self.send_spin.bind("<<Decrement>>", lambda e: self._refresh_estimate())

        self.full_cb = ttk.Checkbutton(
            cnt_box,
            text="全量",
            variable=self.full_scale_var,
            command=self._on_toggle_full_scale,
        )
        self.full_cb.pack(side="left", padx=(6, 0))

        input_bytes_label = ttk.Label(g, text="载荷字节数:")
        input_bytes_label.grid(row=3, column=0, sticky="w", pady=4)
        input_bytes_entry = ttk.Entry(g, textvariable=self.input_bytes_var, width=10)
        input_bytes_entry.grid(
            row=3, column=1, sticky="w", padx=(4, 8), pady=4
        )
        input_bytes_hint = ttk.Label(
            g,
            text=(
                "留空=客户端自动识别格式与长度（不确定时会提示）；"
                f"填了按该字节数截取（1..{MAX_PAYLOAD_BYTES}）"
            ),
            style="Muted.TLabel",
        )
        input_bytes_hint.grid(row=3, column=2, columnspan=2, sticky="w", padx=4, pady=4)

        self._dev_mode_grid_widgets = [
            geom_label,
            geom_cb,
            score_label,
            sbox,
            orient_label,
            orient_cb,
            batch_label,
            batch_entry,
            input_bytes_label,
            input_bytes_entry,
            input_bytes_hint,
        ]

        # 复选框选项
        chk_box = ttk.Frame(card.inner)
        chk_box.pack(fill="x", pady=(6, 0))
        self.skip_wm_check = ttk.Checkbutton(
            chk_box,
            text="跳过水印预载 (仅调试)",
            variable=self.skip_wm_var,
        )
        self.post_check = ttk.Checkbutton(
            chk_box,
            text="发送 POST 触发硬件流水线",
            variable=self.post_var,
        )
        self.post_check.pack(side="left")

        preset_bar = ttk.Frame(card.inner)
        self.preset_bar = preset_bar
        preset_bar.pack(fill="x", pady=(8, 0))
        RoundedButton(
            preset_bar,
            text="保存参数预设...",
            command=self._save_parameter_preset,
            bg_color=COLOR_CARD_ALT,
            hover_color=COLOR_PRIMARY_BG,
            fg_color=COLOR_TEXT_PRIMARY,
            border_color=COLOR_BORDER_LIGHT,
            radius=6,
            width=110,
            height=28,
            font=self.fonts.body,
        ).pack(side="left")
        RoundedButton(
            preset_bar,
            text="加载参数预设...",
            command=self._load_parameter_preset,
            bg_color=COLOR_CARD_ALT,
            hover_color=COLOR_PRIMARY_BG,
            fg_color=COLOR_TEXT_PRIMARY,
            border_color=COLOR_BORDER_LIGHT,
            radius=6,
            width=110,
            height=28,
            font=self.fonts.body,
        ).pack(side="left", padx=6)

        self._dev_mode_pack_widgets = [
            (self.skip_wm_check, {"side": "left", "padx": (0, 14)}),
            (self.preset_bar, {"fill": "x", "pady": (8, 0)}),
        ]
        self._on_toggle_dev_mode()

    def _build_action_card(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, style="Window.TFrame", padding=(2, 6))
        card.pack(fill="x", pady=(4, 0))

        self.start_button = RoundedButton(
            card,
            text="▶  启动硬件加速全流水线",
            command=self.start_processing,
            bg_color=COLOR_PRIMARY,
            hover_color=COLOR_PRIMARY_HOVER,
            fg_color="#ffffff",
            radius=10,
            height=42,
            font=self.fonts.card_header,
        )
        self.start_button.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.stop_button = RoundedButton(
            card,
            text="⏹  停止任务",
            command=self.stop_processing,
            bg_color=COLOR_DANGER,
            hover_color=COLOR_DANGER_HOVER,
            fg_color="#ffffff",
            radius=10,
            height=42,
            font=self.fonts.card_header,
        )
        self.stop_button.configure(state="disabled")
        self.stop_button.pack(side="left", padx=2)

    def _add_file_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command: Callable[[], None],
    ) -> None:
        ttk.Label(parent, text=f"{label}:").grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=6, pady=3)
        RoundedButton(
            parent,
            text="浏览...",
            command=command,
            bg_color=COLOR_CARD_ALT,
            hover_color=COLOR_PRIMARY_BG,
            fg_color=COLOR_TEXT_PRIMARY,
            border_color=COLOR_BORDER_LIGHT,
            radius=6,
            width=64,
            height=26,
            font=self.fonts.body,
        ).grid(row=row, column=2, sticky="e", pady=3)

    # ------------------------------------------------------------- 右侧构建
    def _build_pipeline_card(self, parent: ttk.Frame) -> None:
        card = RoundedCard(parent, title="硬件流水线状态与性能指标", radius=10, title_font=self.fonts.card_header)
        card.pack(fill="x", pady=(0, 6))

        # 1. 现代柔和圆角胶囊步进器 (Capsule Stepper)
        stepper = tk.Frame(card.inner, bg=COLOR_CARD_BG)
        stepper.pack(fill="x", pady=(0, 8))
        self.step_labels = {}
        for token, title in PIPELINE_STAGES:
            pill = RoundedPill(
                stepper,
                text=f"○ {title}",
                bg_color=STEP_PALETTE["idle"]["bg"],
                fg_color=STEP_PALETTE["idle"]["fg"],
                border_color=STEP_PALETTE["idle"]["border"],
                font=self.fonts.caption,
                radius=10,
                height=30,
            )
            pill.pack(side="left", expand=True, fill="x", padx=3)
            self.step_labels[token] = pill

        # 2. 进度条与实时计时器
        prog_box = ttk.Frame(card.inner)
        prog_box.pack(fill="x", pady=(2, 6))
        prog_box.columnconfigure(0, weight=1)

        self.upload_bar = ttk.Progressbar(prog_box, maximum=100)
        self.upload_bar.grid(row=0, column=0, sticky="ew")

        ttk.Label(
            prog_box,
            textvariable=self.upload_percent_var,
            width=6,
            font=self.fonts.body_bold,
        ).grid(row=0, column=1, sticky="e", padx=(8, 10))

        ttk.Label(
            prog_box,
            textvariable=self.timer_var,
            style="Timer.TLabel",
        ).grid(row=0, column=2, sticky="e")

        # 3. 动态柔和圆角状态横幅 (随运行与判据结果动态平滑变色)
        self.status_banner = RoundedStatusBanner(
            card.inner,
            status_var=self.status_var,
            hint_var=self.upload_hint_var,
            fonts=self.fonts,
            radius=8,
            height=38,
        )
        self.status_banner.pack(fill="x", pady=(0, 6))

        # 4. 毫秒级性能指标微卡片 (2x2 网格圆角微卡片)
        metrics_box = ttk.Frame(card.inner)
        metrics_box.pack(fill="x", pady=(2, 0))
        for col in range(2):
            metrics_box.columnconfigure(col, weight=1)

        t1 = RoundedMetricTile(metrics_box, "上行传输耗时 (Tx)", self.metric_upload_var, self.fonts, radius=8, height=52)
        t1.grid(row=0, column=0, sticky="nsew", padx=3, pady=3)

        t2 = RoundedMetricTile(metrics_box, "板端运算与回传 (HW)", self.metric_fpga_var, self.fonts, radius=8, height=52)
        t2.grid(row=0, column=1, sticky="nsew", padx=3, pady=3)

        t3 = RoundedMetricTile(metrics_box, "PC 端校验耗时 (Verify)", self.metric_verify_var, self.fonts, radius=8, height=52)
        t3.grid(row=1, column=0, sticky="nsew", padx=3, pady=3)

        t4 = RoundedMetricTile(metrics_box, "端到端总耗时 (E2E)", self.metric_total_var, self.fonts, radius=8, height=52)
        t4.grid(row=1, column=1, sticky="nsew", padx=3, pady=3)

    def _build_preview_card(self, parent: ttk.Frame) -> None:
        card = RoundedCard(parent, title="板端结果校验与载荷展示", radius=10, title_font=self.fonts.card_header)
        card.pack(fill="x", pady=(0, 6))

        top_bar = ttk.Frame(card.inner)
        top_bar.pack(fill="x", pady=(0, 4))

        ttk.Label(top_bar, text="载荷 SHA-256:").pack(side="left")
        self.hash_label = tk.Label(
            top_bar,
            textvariable=self.payload_hash_var,
            font=self.fonts.mono_body,
            bg=COLOR_CARD_BG,
            fg=COLOR_TEXT_PRIMARY,
        )
        self.hash_label.pack(side="left", padx=(6, 0))

        # 图像预览容器 (柔和圆角卡片)
        self.preview_container = RoundedCard(
            card.inner,
            title="",
            radius=8,
            bg_color=COLOR_CARD_ALT,
            border_color=COLOR_BORDER_LIGHT,
            auto_height=False,
            height=130,
            padding=6,
        )
        self.preview_container.pack(fill="x", pady=6)

        self.preview_label = tk.Label(
            self.preview_container.inner,
            text="[完成板端结果校验后显示载荷信息]",
            bg=COLOR_CARD_ALT,
            fg=COLOR_TEXT_SECONDARY,
            font=self.fonts.body,
            anchor="center",
        )
        self.preview_label.pack(expand=True, fill="both")

        # 按钮条
        action_bar = ttk.Frame(card.inner)
        action_bar.pack(fill="x", pady=(4, 0))

        RoundedButton(
            action_bar,
            text="打开输出目录",
            command=self._open_output_dir,
            bg_color=COLOR_CARD_ALT,
            hover_color=COLOR_PRIMARY_BG,
            fg_color=COLOR_TEXT_PRIMARY,
            border_color=COLOR_BORDER_LIGHT,
            radius=6,
            width=96,
            height=28,
            font=self.fonts.body,
        ).pack(side="left")

        self.open_payload_button = RoundedButton(
            action_bar,
            text="用系统默认程序打开",
            command=self._open_payload_external,
            bg_color=COLOR_CARD_ALT,
            hover_color=COLOR_PRIMARY_BG,
            fg_color=COLOR_TEXT_PRIMARY,
            border_color=COLOR_BORDER_LIGHT,
            radius=6,
            width=134,
            height=28,
            font=self.fonts.body,
        )
        self.open_payload_button.configure(state="disabled")
        self.open_payload_button.pack(side="left", padx=6)

    def _build_log_card(self, parent: ttk.Frame) -> None:
        card = RoundedCard(
            parent,
            title="运行诊断日志",
            radius=10,
            auto_height=False,
            title_font=self.fonts.card_header,
        )
        card.pack(fill="both", expand=True, pady=(0, 6))

        tool_bar = ttk.Frame(card.inner)
        tool_bar.pack(fill="x", pady=(0, 4))

        lbl_hint = ttk.Label(tool_bar, text="实时通信与协议诊断输出", style="Muted.TLabel")
        lbl_hint.pack(side="left")

        RoundedButton(
            tool_bar,
            text="清空日志",
            command=self._clear_logs,
            bg_color=COLOR_CARD_ALT,
            hover_color=COLOR_PRIMARY_BG,
            fg_color=COLOR_TEXT_PRIMARY,
            border_color=COLOR_BORDER_LIGHT,
            radius=6,
            width=70,
            height=26,
            font=self.fonts.caption,
        ).pack(side="right")

        self.log_text = ScrolledText(
            card.inner,
            height=10,
            state="disabled",
            font=self.fonts.mono_body,
            bg=LOG_TERMINAL_BG,
            fg=LOG_TERMINAL_FG,
            insertbackground="#ffffff",
            selectbackground=LOG_TERMINAL_SELECT,
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=8,
            pady=6,
        )
        self.log_text.pack(fill="both", expand=True)

        # 配置日志颜色高亮标签
        for tag, cfg in LOG_TAG_COLORS.items():
            font = self.fonts.mono_bold if cfg.get("bold") else self.fonts.mono_body
            self.log_text.tag_configure(tag, foreground=cfg["fg"], font=font)

    # ----------------------------------------------------------- 交互与自适应
    def _choose_watermark(self) -> None:
        path = filedialog.askopenfilename(
            title="选择水印文件",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialdir=Path(self.watermark_var.get()).parent,
        )
        if path:
            self.watermark_var.set(path)

    def _choose_reads(self) -> None:
        path = filedialog.askopenfilename(
            title="选择测序 FASTQ 文件",
            filetypes=[("FASTQ files", "*.fastq;*.fq"), ("Text files", "*.txt"), ("All files", "*.*")],
            initialdir=Path(self.reads_var.get()).parent,
        )
        if path:
            self.reads_var.set(path)
            self._detect_reads(Path(path))

    def _choose_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="选择输出结果文件",
            initialfile="dec_input.txt",
            initialdir=Path(self.output_var.get()).parent,
        )
        if path:
            self.output_var.set(path)

    def _save_parameter_preset(self) -> None:
        path = filedialog.asksaveasfilename(
            title="保存参数预设",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="client-preset.json",
        )
        if not path:
            return

        preset = {
            "schema_version": 1,
            "parameters": {
                "ip": self.ip_var.get(),
                "port": self.port_var.get(),
                "geom_mode": self.geom_mode_var.get(),
                "score_min": self.score_min_var.get(),
                "orient": self.orient_var.get(),
                "batch": self.batch_var.get(),
                "send_count": self.send_count_var.get(),
                "full_scale": self.full_scale_var.get(),
                "dev_mode": self.dev_mode_var.get(),
                "input_bytes": self.input_bytes_var.get(),
                "skip_watermark": self.skip_wm_var.get(),
                "post": self.post_var.get(),
            },
        }
        try:
            Path(path).write_text(
                json.dumps(preset, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            messagebox.showerror("保存失败", f"无法写入参数预设: {exc}")
            return

        self._append_log(f"[INFO] 参数预设已保存: {path}")
        messagebox.showinfo("保存完成", f"参数预设已保存到:\n{path}")

    def _load_parameter_preset(self) -> None:
        path = filedialog.askopenfilename(
            title="加载参数预设",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            preset = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(preset, dict):
                raise ValueError("预设文件顶层必须是 JSON 对象")
            if preset.get("schema_version") != 1:
                raise ValueError("不支持的参数预设版本")
            values = preset.get("parameters")
            if not isinstance(values, dict):
                raise ValueError("缺少 parameters 对象")

            def read_integer(key: str) -> int:
                raw = values[key]
                if isinstance(raw, bool):
                    raise ValueError(f"{key} 必须是整数")
                if isinstance(raw, int):
                    return raw
                if isinstance(raw, str) and raw.isdigit():
                    return int(raw)
                raise ValueError(f"{key} 必须是整数")

            ip = values["ip"]
            port = read_integer("port")
            geom_mode = values["geom_mode"]
            score_min = str(values["score_min"])
            orient = values["orient"]
            batch = read_integer("batch")
            send_count = read_integer("send_count")
            full_scale = values["full_scale"]
            dev_mode = values.get("dev_mode", False)
            input_bytes_raw = values.get("input_bytes", "")
            if input_bytes_raw is None:
                input_bytes_raw = ""
            if isinstance(input_bytes_raw, bool):
                raise ValueError("input_bytes 必须为空或为整数")
            if isinstance(input_bytes_raw, int):
                input_bytes_raw = str(input_bytes_raw)
            if not isinstance(input_bytes_raw, str):
                raise ValueError("input_bytes 必须为空或为整数")
            input_bytes = input_bytes_raw.strip()
            skip_watermark = values["skip_watermark"]
            post = values["post"]

            if not isinstance(ip, str):
                raise ValueError("ip 必须是字符串")
            if not 0 < port < 65536:
                raise ValueError("port 必须在 1..65535")
            if geom_mode not in ("auto (自适应)", "150 (SE150)", "250 (SE250)"):
                raise ValueError("geom_mode 无效")
            if score_min and (not score_min.isdigit() or int(score_min) > 1023):
                raise ValueError("score_min 必须为空或在 0..1023")
            if orient not in ("both (正反双向-必需)", "forward (仅正向)"):
                raise ValueError("orient 无效")
            if batch <= 0:
                raise ValueError("batch 必须为正整数")
            if not 0 < send_count <= MAX_TOTAL_READS:
                raise ValueError(f"send_count 必须在 1..{MAX_TOTAL_READS}")
            if input_bytes and (
                not input_bytes.isdigit()
                or not 1 <= int(input_bytes) <= MAX_PAYLOAD_BYTES
            ):
                raise ValueError(f"input_bytes 必须为空或在 1..{MAX_PAYLOAD_BYTES}")
            if not all(isinstance(flag, bool) for flag in (full_scale, dev_mode, skip_watermark, post)):
                raise ValueError("full_scale、dev_mode、skip_watermark 和 post 必须是布尔值")
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            messagebox.showerror("加载失败", f"参数预设无效或无法读取:\n{exc}")
            return

        self.ip_var.set(ip)
        self.port_var.set(str(port))
        self.geom_mode_var.set(geom_mode)
        self.score_min_var.set(score_min)
        self.orient_var.set(orient)
        self.batch_var.set(str(batch))
        self.send_count_var.set(send_count)
        self.full_scale_var.set(full_scale)
        self.dev_mode_var.set(dev_mode)
        self.input_bytes_var.set(input_bytes)
        self.skip_wm_var.set(skip_watermark)
        self.post_var.set(post)
        self._on_toggle_dev_mode()
        self.send_spin.configure(state="disabled" if full_scale else "normal")
        self._refresh_estimate()
        self._append_log(f"[INFO] 参数预设已加载: {path}")

    def _auto_detect_default_reads(self) -> None:
        path = Path(self.reads_var.get()).expanduser()
        if path.is_file():
            self._detect_reads(path)

    def _manual_detect_reads(self) -> None:
        path = Path(self.reads_var.get()).expanduser()
        if not path.is_file():
            messagebox.showerror("文件不存在", f"测序文件未找到: {path}")
            return
        self._detect_reads(path)

    def _detect_reads(self, path: Path) -> bool:
        try:
            self.spec_badge_var.set("正在采样分析测序文件...")
            self.update_idletasks()
            info = analyze_reads_file(path)
            self._read_info = info

            bps_str = f"{info.detected_read_bps} bp" if info.detected_read_bps else "未知读长"
            spec_name = "SE150" if info.detected_read_bps == 150 else ("SE250" if info.detected_read_bps == 250 else "自定义")
            self.spec_badge_var.set(f"{spec_name} ({bps_str}) | 共 {info.total_reads:,} 条源读段")

            # 自动调整发送条数与几何参数
            if self.full_scale_var.get() or self.send_count_var.get() <= 0:
                self.send_count_var.set(info.total_reads)

            # 若几何模式为 auto，同步推荐阈值
            if self.geom_mode_var.get().startswith("auto"):
                if info.suggested_score_min is not None:
                    self.score_min_var.set(str(info.suggested_score_min))

            self._refresh_estimate()
            self._append_log(f"[INFO] 成功分析测序文件: {path.name} ({info.total_reads:,} 条, {bps_str})")
            return True
        except Exception as exc:
            self.spec_badge_var.set("分析失败")
            messagebox.showerror("探测失败", f"分析测序文件出错: {exc}")
            return False

    def _on_geom_changed(self, event=None) -> None:
        mode = self.geom_mode_var.get()
        if "150" in mode:
            self.score_min_var.set(str(default_score_min(150)))
        elif "250" in mode:
            self.score_min_var.set(str(default_score_min(250)))
        elif "auto" in mode and self._read_info and self._read_info.suggested_score_min:
            self.score_min_var.set(str(self._read_info.suggested_score_min))
        self._refresh_estimate()

    def _apply_recommended_score(self) -> None:
        bps = self._resolve_read_bps()
        self.score_min_var.set(str(default_score_min(bps)))

    def _on_toggle_full_scale(self) -> None:
        if self.full_scale_var.get():
            if self._read_info:
                self.send_count_var.set(self._read_info.total_reads)
            self.send_spin.configure(state="disabled")
        else:
            self.send_spin.configure(state="normal")
        self._refresh_estimate()

    def _resolve_read_bps(self, mode: Optional[str] = None) -> int:
        if mode is None:
            mode = self.geom_mode_var.get()
        if "150" in mode:
            return 150
        if "250" in mode:
            return 250
        if self._read_info and self._read_info.detected_read_bps:
            return self._read_info.detected_read_bps
        return 150

    def _effective_config_values(self) -> Tuple[str, int, int, str, int, bool, Optional[int]]:
        """集中解析开发/普通模式实际传给任务的参数。"""
        dev_mode = self.dev_mode_var.get()
        geom_mode = self.geom_mode_var.get() if dev_mode else "auto"
        read_bps = self._resolve_read_bps(geom_mode)

        if dev_mode:
            try:
                batch = int(self.batch_var.get())
                if batch <= 0:
                    raise ValueError
            except ValueError:
                raise ValueError("批大小必须是正整数。")

            input_bytes_raw = self.input_bytes_var.get().strip()
            if not input_bytes_raw:
                input_bytes: Optional[int] = None
            elif not input_bytes_raw.isdigit() or not 1 <= int(input_bytes_raw) <= MAX_PAYLOAD_BYTES:
                raise ValueError(
                    f"载荷字节数必须留空，或输入 1..{MAX_PAYLOAD_BYTES} 的整数。"
                )
            else:
                input_bytes = int(input_bytes_raw)

            score_min_raw = self.score_min_var.get().strip()
            score_min = (
                int(score_min_raw)
                if score_min_raw.isdigit()
                else default_score_min(read_bps)
            )
            orient = "both" if "both" in self.orient_var.get() else "forward"
            batch_value = batch
            skip_wm = self.skip_wm_var.get()
        else:
            score_min = default_score_min(read_bps)
            orient = "both"
            batch_value = self._defaults.batch
            skip_wm = False
            input_bytes = None

        return geom_mode, read_bps, score_min, orient, batch_value, skip_wm, input_bytes

    def _on_toggle_dev_mode(self) -> None:
        """显示或隐藏高级参数，并按当前模式收紧参数网格。"""
        skip_wm_widget, skip_wm_pack_options = self._dev_mode_pack_widgets[0]
        _, preset_pack_options = self._dev_mode_pack_widgets[1]

        if self.dev_mode_var.get():
            for widget in self._dev_mode_grid_widgets:
                widget.grid()
            self._params_grid.columnconfigure(1, weight=1)
            self._params_grid.columnconfigure(3, weight=1)

            # 重排复选框，使开发选项位于常用的 POST 选项之前。
            self.post_check.pack_forget()
            skip_wm_widget.pack(**skip_wm_pack_options)
            self.post_check.pack(side="left")
            self.preset_bar.pack(**preset_pack_options)
        else:
            for widget in self._dev_mode_grid_widgets:
                widget.grid_remove()
            self._params_grid.columnconfigure(1, weight=0)
            self._params_grid.columnconfigure(3, weight=0)
            skip_wm_widget.pack_forget()
            self.preset_bar.pack_forget()

        self._refresh_estimate()

    def _refresh_estimate(self) -> None:
        try:
            count = int(self.send_count_var.get())
            orient = self._effective_config_values()[3]
            sec = estimate_processing_time(count, orient=orient)
            self.est_time_var.set(f"~{sec:.1f} 秒（两点实测粗估）")
        except Exception:
            self.est_time_var.set("--")

    def _test_connection(self) -> None:
        ip = self.ip_var.get().strip()
        try:
            port = int(self.port_var.get().strip())
        except ValueError:
            messagebox.showerror("错误", "端口必须为数字")
            return

        self.conn_status_var.set("正在连接...")
        self.conn_badge.set_visuals(
            text="正在连接...",
            bg_color=COLOR_PRIMARY_BG,
            fg_color=COLOR_PRIMARY,
            border_color=COLOR_PRIMARY_BORDER,
        )
        self.update_idletasks()

        def do_ping():
            t0 = time.perf_counter()
            try:
                s = socket.create_connection((ip, port), timeout=1.5)
                s.close()
                dt_ms = (time.perf_counter() - t0) * 1000
                self.after(0, lambda: self.conn_status_var.set(f"🟢 在线 ({dt_ms:.1f} ms)"))
                self.after(0, lambda: self.conn_badge.set_visuals(
                    text=f"🟢 在线 ({dt_ms:.1f} ms)",
                    bg_color=COLOR_SUCCESS_BG,
                    fg_color=COLOR_SUCCESS_TEXT,
                    border_color=COLOR_SUCCESS_BORDER,
                ))
                self.after(0, lambda: self._append_log(f"[INFO] 成功连通板端 {ip}:{port} (RTT {dt_ms:.1f} ms)"))
            except Exception as exc:
                error_text = str(exc)
                self.after(0, lambda: self.conn_status_var.set("🔴 离线 / 拒绝"))
                self.after(0, lambda: self.conn_badge.set_visuals(
                    text="🔴 离线 / 拒绝",
                    bg_color=COLOR_DANGER_BG,
                    fg_color=COLOR_DANGER_TEXT,
                    border_color=COLOR_DANGER_BORDER,
                ))
                self.after(0, lambda error_text=error_text: self._append_log(
                    f"[WARN] 无法连接到 {ip}:{port}: {error_text}"
                ))

        threading.Thread(target=do_ping, daemon=True).start()

    # ------------------------------------------------------------- 任务执行
    def start_processing(self) -> None:
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("正在运行", "任务正在执行中，请等待或点击停止。")
            return

        try:
            port = int(self.port_var.get())
            if not (0 < port < 65536):
                raise ValueError
        except ValueError:
            messagebox.showerror("参数错误", "端口需在 1-65535 之间。")
            return

        try:
            send_count = int(self.send_count_var.get())
            if send_count <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("参数错误", "发送条数必须是正整数。")
            return

        watermark_path = Path(self.watermark_var.get()).expanduser()
        reads_path = Path(self.reads_var.get()).expanduser()
        output_path = Path(self.output_var.get()).expanduser()

        if not reads_path.is_file():
            messagebox.showerror("文件错误", "FASTQ 文件不存在。")
            return

        if not self._read_info or self._read_info.path != reads_path:
            if not self._detect_reads(reads_path):
                return

        try:
            _, read_bps, score_min, orient, batch, skip_wm, input_bytes = (
                self._effective_config_values()
            )
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        if not skip_wm and not watermark_path.is_file():
            messagebox.showerror("文件错误", "水印文件不存在。")
            return

        output_path.parent.mkdir(parents=True, exist_ok=True)

        effective_source_reads = min(send_count, self._read_info.total_reads)
        self._expected_hw_seconds = estimate_processing_time(
            effective_source_reads,
            orient=orient,
        )

        config = ClientConfig(
            ip=self.ip_var.get().strip() or self._defaults.ip,
            port=port,
            watermark=watermark_path,
            reads=reads_path,
            out=output_path,
            batch=batch,
            total=self._read_info.total_reads,
            send_limit=send_count,
            skip_wm=skip_wm,
            post=self.post_var.get(),
            format=self._read_info.format,
            orient=orient,
            read_bps=read_bps,
            score_min=score_min,
            result_timeout=max(
                180.0,
                estimate_processing_time(effective_source_reads, orient=orient) * 2.0 + 30.0,
            ),
        )

        self._reset_progress()
        self._append_log("=" * 60)
        self._append_log(f"[INFO] 启动硬件加速流水线: {read_bps}bp | score_min={score_min} | {send_count}条 | {orient}")
        self._update_status("正在启动任务 ...")

        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")

        self._start_time = time.perf_counter()
        self._is_running = True
        self._update_timer()

        self._stop_event = threading.Event()
        self._worker = threading.Thread(
            target=self._run_client_task,
            args=(config, input_bytes),
            daemon=True,
        )
        self._worker.start()

    def stop_processing(self) -> None:
        if self._stop_event is None or self._stop_event.is_set():
            return
        self._append_log("[INFO] 收到用户中止请求，正在通知后台任务 ...")
        self._stop_event.set()

    def _run_client_task(self, config: ClientConfig, input_bytes: Optional[int]) -> None:
        def log_fn(message: str) -> None:
            self._log_queue.put(message)

        def verify_log_fn(message: str) -> None:
            # verify_board_result 先写中间 .bin；最终路径和长度由本方法确定后再记录。
            if message.startswith("[板端校验] 已保存载荷 "):
                return
            log_fn(message)

        callbacks = ProgressCallbacks(
            update_status=lambda msg: self.after(0, self._update_status, msg),
            update_upload=lambda sent, total: self.after(0, self._update_upload_progress, sent, total),
            update_stage_label=lambda stage: self.after(0, self._set_active_stage, stage),
        )

        try:
            stats = run_client(config, log=log_fn, progress=callbacks, stop_event=self._stop_event)
            log_fn(format_metric_report(stats))

            # 记录网络与 FPGA 硬件阶段耗时
            self.after(0, lambda: self.metric_upload_var.set(f"{stats.t_batches:.2f} s"))
            self.after(0, lambda: self.metric_fpga_var.set(f"{stats.t_result:.2f} s"))

            if not config.post:
                self.after(0, self._on_run_complete, True, None)
                return

            self.after(0, self._update_status, "正在校验板端回传码字与载荷...")
            verify_started = time.perf_counter()
            try:
                # 留空时先完整读取信息位，交给 infer_payload 决定边界；显式长度仍按原值截取。
                verify_input_bytes = MAX_PAYLOAD_BYTES if input_bytes is None else input_bytes
                result = verify_board_result(
                    Path(config.out),
                    Path(config.out).resolve().parent,
                    input_bytes=verify_input_bytes,
                    log=verify_log_fn,
                )
            except BoardCodeRejected as exc:
                elapsed_ms = (time.perf_counter() - verify_started) * 1000
                self.after(0, lambda: self.metric_verify_var.set(f"{elapsed_ms:.1f} ms"))
                self.after(0, self._show_board_code_rejected, exc)
                self.after(0, self._on_run_complete, False, "BoardCodeRejected")
                return

            decoded_bits = result.decoded_bits_path.read_text(encoding="ascii")
            info_bits = np.frombuffer(decoded_bits.encode("ascii"), dtype=np.uint8) - ord("0")
            inferred = infer_payload(info_bits)
            if input_bytes is None:
                payload_guess = inferred
                payload = inferred.data
            else:
                # 仅借助魔数建议后缀；明确长度对应的载荷字节保持原样。
                payload = result.payload_path.read_bytes()
                media_type = inferred.media_type
                extension = inferred.extension
                if media_type == "application/octet-stream":
                    media_type = detect_payload_media_type(payload)
                    extension = {
                        "image/jpeg": ".jpg",
                        "image/png": ".png",
                        "image/gif": ".gif",
                        "image/bmp": ".bmp",
                        "image/tiff": ".tiff",
                        "audio/wav": ".wav",
                        "audio/mpeg": ".mp3",
                        "audio/ogg": ".ogg",
                        "audio/flac": ".flac",
                        "video/mp4": ".mp4",
                        "video/avi": ".avi",
                        "video/webm-or-matroska": ".mkv",
                        "text": ".txt",
                        "binary": ".bin",
                    }.get(media_type, ".bin")
                payload_guess = PayloadGuess(
                    data=payload,
                    media_type=media_type,
                    extension=extension,
                    length_certain=True,
                    method=f"用户显式指定 {input_bytes} 字节；格式按魔数识别",
                )

            if (
                not payload_guess.extension.startswith(".")
                or Path(payload_guess.extension).name != payload_guess.extension
            ):
                raise ValueError(f"载荷推断返回了无效扩展名: {payload_guess.extension!r}")
            payload_path = result.payload_path.with_name(
                f"decoded_payload{payload_guess.extension}"
            )
            payload_path.write_bytes(payload)
            if payload_path != result.payload_path:
                result.payload_path.unlink(missing_ok=True)
            result.payload_path = payload_path
            result.payload_bytes = len(payload)

            certainty = "确定" if payload_guess.length_certain else "不确定"
            log_fn(
                f"[PAYLOAD] 识别格式：{payload_guess.media_type}；建议扩展名：{payload_guess.extension}；"
                f"长度是否确定：{certainty}；判定依据：{payload_guess.method}"
            )
            if not payload_guess.length_certain:
                log_fn("[WARN] 载荷长度靠去尾零推测，可能不准。")
            log_fn(f"[板端校验] 已保存载荷 {result.payload_path}（{result.payload_bytes} 字节）")

            elapsed_ms = (time.perf_counter() - verify_started) * 1000
            self.after(0, lambda: self.metric_verify_var.set(f"{elapsed_ms:.1f} ms"))
            self.after(0, self._handle_board_verify_result, result, payload_guess)
            self.after(0, self._on_run_complete, True, None)
        except OperationCancelled:
            log_fn("[INFO] 任务已被用户取消")
            self.after(0, self._on_run_complete, False, "Operation cancelled")
        except Exception as exc:
            log_fn(f"[ERROR] {exc}")
            self.after(0, self._on_run_complete, False, str(exc))

    # ------------------------------------------------------------- 回调与状态
    def _update_step_capsule(self, token: str, state: str) -> None:
        """更新单个步进胶囊的视觉状态 (idle / active / done / failed)。"""
        pill = self.step_labels.get(token)
        if not pill:
            return
        palette = STEP_PALETTE.get(state, STEP_PALETTE["idle"])
        title = self._step_titles.get(token, token)
        prefix = palette["prefix"]
        font = self.fonts.caption_bold if state != "idle" else self.fonts.caption
        pill.set_visuals(
            text=f"{prefix} {title}",
            bg_color=palette["bg"],
            fg_color=palette["fg"],
            border_color=palette["border"],
            font=font,
        )

    def _on_run_complete(self, success: bool, error: Optional[str]) -> None:
        active_stage = self.active_stage_var.get()
        self._is_running = False
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self._set_active_stage("")

        dt_total = time.perf_counter() - self._start_time
        self.metric_total_var.set(f"{dt_total:.2f} s")

        if success:
            if self._last_verify_result is not None and self._last_verify_result.verified:
                for token, _ in PIPELINE_STAGES:
                    self._update_step_capsule(token, "done")
                self._append_log(f"[INFO] 板端结果校验完成！总耗时: {dt_total:.2f}s")
                self._update_status(
                    f"✓ 板端已纠对（{self._last_verify_result.total_rows} 条校验行全零）；"
                    "PC 端未做译码",
                    success=True,
                )
            elif self._last_verify_result is not None:
                self._update_step_capsule("LDPC", "failed")
                self._append_log("[ERROR] 板端 syndrome 非零，不能报告校验通过。")
                self._update_status("板端结果校验未通过", failed=True)
            else:
                self._append_log(f"[INFO] 上传流程完成，未触发板端处理。总耗时: {dt_total:.2f}s")
                self._update_status("上传完成（未触发 POST）")
        else:
            if error == "Operation cancelled":
                self._append_log("[INFO] 任务已取消")
                self._update_status("任务已取消")
            elif error == "BoardCodeRejected":
                # 具体失败数由 _show_board_code_rejected 显示；不弹出可被误读成警告的提示框。
                pass
            else:
                # 标记当前执行中的阶段失败
                if active_stage in self.step_labels:
                    self._update_step_capsule(active_stage, "failed")
                self._update_status("运行失败", failed=True)
                messagebox.showerror("运行失败", error or "未知错误")

        self._worker = None
        self._stop_event = None

    def _set_active_stage(self, stage: str) -> None:
        stage_token = (stage or "").upper()
        self.active_stage_var.set(stage_token)

        stage_order = [token for token, _ in PIPELINE_STAGES]
        if stage_token in stage_order:
            curr_idx = stage_order.index(stage_token)
            for idx, token in enumerate(stage_order):
                if idx < curr_idx:
                    self._update_step_capsule(token, "done")
                elif idx == curr_idx:
                    self._update_step_capsule(token, "active")
                else:
                    self._update_step_capsule(token, "idle")

        if stage_token == "LDPC":
            if self._board_wait_started_at is None:
                self._board_wait_started_at = time.perf_counter()
            self.upload_bar.stop()
            self.upload_bar.configure(mode="indeterminate")
            self.upload_bar.start(12)
            self.upload_percent_var.set("运行中")
            self._update_board_wait_progress()
        else:
            self._board_wait_started_at = None
            self.upload_bar.stop()
            self.upload_bar.configure(mode="determinate")

    def _update_board_wait_progress(self) -> None:
        if self.active_stage_var.get() != "LDPC" or self._board_wait_started_at is None:
            return
        elapsed = time.perf_counter() - self._board_wait_started_at
        self.upload_hint_var.set(
            f"已等待 {elapsed:.0f} 秒 / 预计约 {self._expected_hw_seconds:.1f} 秒（粗估）"
        )
        if self._is_running:
            self.after(1000, self._update_board_wait_progress)

    def _update_status(
        self,
        message: str,
        *,
        failed: bool = False,
        success: bool = False,
    ) -> None:
        self.status_var.set(message)
        if failed:
            self.status_banner.set_theme_mode("failed")
            self.top_status_badge.set_visuals(
                text="✗ 校验未通过",
                bg_color=COLOR_DANGER_BG,
                fg_color=COLOR_DANGER_TEXT,
                border_color=COLOR_DANGER_BORDER,
            )
        elif success:
            self.status_banner.set_theme_mode("success")
            self.top_status_badge.set_visuals(
                text="✓ 板端纠对通过",
                bg_color=COLOR_SUCCESS_BG,
                fg_color=COLOR_SUCCESS_TEXT,
                border_color=COLOR_SUCCESS_BORDER,
            )
        elif self._is_running:
            self.status_banner.set_theme_mode("running")
            self.top_status_badge.set_visuals(
                text="● 硬件运行中",
                bg_color=COLOR_PRIMARY_BG,
                fg_color=COLOR_PRIMARY,
                border_color=COLOR_PRIMARY_BORDER,
            )
        else:
            self.status_banner.set_theme_mode("idle")
            self.top_status_badge.set_visuals(
                text="系统就绪",
                bg_color=COLOR_CARD_ALT,
                fg_color=COLOR_TEXT_SECONDARY,
                border_color=COLOR_BORDER_LIGHT,
            )

    def _update_upload_progress(self, sent: int, total: int) -> None:
        total = max(total, 1)
        percent = int((sent / total) * 100)
        percent = max(0, min(100, percent))
        self.upload_bar.stop()
        self.upload_bar.configure(mode="determinate")
        self.upload_bar.configure(value=percent)
        self.upload_percent_var.set(f"{percent}%")
        self.upload_hint_var.set(f"已发送 {sent:,}/{total:,} 条读段")

    def _reset_progress(self) -> None:
        self.upload_bar.stop()
        self.upload_bar.configure(mode="determinate", value=0)
        self._board_wait_started_at = None
        self.upload_percent_var.set("0%")
        self.upload_hint_var.set("等待传输")
        self.metric_upload_var.set("--")
        self.metric_fpga_var.set("--")
        self.metric_verify_var.set("--")
        self.metric_total_var.set("--")
        self.payload_hash_var.set("--")
        self.hash_label.configure(fg=COLOR_TEXT_PRIMARY)
        self._update_status("就绪")
        self.status_banner.set_theme_mode("idle")
        self._last_verify_result = None
        self._preview_photo = None
        self.preview_label.configure(image="", text="[完成板端结果校验后显示载荷信息]")
        self.open_payload_button.configure(state="disabled")
        for token, _ in PIPELINE_STAGES:
            self._update_step_capsule(token, "idle")

    def _update_timer(self) -> None:
        if self._is_running:
            elapsed = int(time.perf_counter() - self._start_time)
            mins = elapsed // 60
            secs = elapsed % 60
            self.timer_var.set(f"{mins:02d}:{secs:02d}")
            self.after(500, self._update_timer)

    # ------------------------------------------------------------- 载荷与输出
    def _show_board_code_rejected(self, error: BoardCodeRejected) -> None:
        self._last_verify_result = None
        self._preview_photo = None
        self.payload_hash_var.set("板端结果校验失败")
        self.hash_label.configure(fg=COLOR_DANGER_TEXT)
        self.preview_label.configure(image="", text="板端未纠对；未生成或展示载荷。")
        self.open_payload_button.configure(state="disabled")

        # 将 LDPC 阶段标红，前序阶段保持已完成绿
        for token, _ in PIPELINE_STAGES:
            if token == "LDPC":
                self._update_step_capsule(token, "failed")
            else:
                self._update_step_capsule(token, "done")

        self._update_status(
            f"✗ 板端未纠对：{error.failed_rows}/{error.total_rows} 条校验行非零 —— 本用例失败",
            failed=True,
        )

    def _handle_board_verify_result(
        self,
        result: BoardVerifyResult,
        payload_guess: Optional[PayloadGuess] = None,
    ) -> None:
        self._last_verify_result = result
        payload = result.payload_path.read_bytes()
        sha256 = hashlib.sha256(payload).hexdigest()
        is_golden = sha256 == GOLDEN_PAYLOAD_SHA256
        status_txt = f"{sha256[:16]}...{sha256[-8:]}" + (
            " [R0.83 逐字节吻合]" if is_golden else " [板端校验通过]"
        )
        self.payload_hash_var.set(status_txt)
        self.hash_label.configure(fg=COLOR_SUCCESS_TEXT if is_golden else COLOR_PRIMARY)
        media_type = (
            payload_guess.media_type if payload_guess else detect_payload_media_type(payload)
        )
        self._append_log(f"[VERIFY] 载荷 SHA-256: {sha256}；类型: {media_type}")
        if is_golden:
            self._append_log("[GOLDEN] 载荷与 R0.83 黄金基线逐字节吻合。")

        payload_details = ""
        if payload_guess is not None:
            certainty = "确定" if payload_guess.length_certain else "不确定"
            payload_details = (
                f"\n识别格式：{payload_guess.media_type}"
                f"\n建议扩展名：{payload_guess.extension}"
                f"\n长度是否确定：{certainty}"
                f"\n判定依据：{payload_guess.method}"
            )
            if not payload_guess.length_certain:
                payload_details += "\n载荷长度靠去尾零推测，可能不准。"

        media_labels = {
            "audio/mpeg": "音频 MP3",
            "audio/wav": "音频 WAV",
            "audio/ogg": "音频 Ogg",
            "audio/flac": "音频 FLAC",
            "video/mp4": "视频 MP4",
            "video/avi": "视频 AVI",
            "video/x-msvideo": "视频 AVI",
            "video/webm-or-matroska": "视频 WebM/Matroska",
            "text": "文本",
            "text/plain; charset=utf-8": "文本（UTF-8）",
            "application/pdf": "PDF",
            "application/zip": "ZIP",
            "binary": "二进制",
            "application/octet-stream": "二进制",
        }
        if media_type.startswith("image/"):
            if Image is not None and ImageTk is not None:
                try:
                    with Image.open(result.payload_path) as im:
                        im.load()
                        w, h = im.size
                        scale = min(220 / max(w, 1), 120 / max(h, 1))
                        thumbnail = im.resize(
                            (max(1, int(w * scale)), max(1, int(h * scale))),
                            Image.Resampling.LANCZOS,
                        )
                    self._preview_photo = ImageTk.PhotoImage(thumbnail)
                    self.preview_label.configure(
                        image=self._preview_photo,
                        text=(
                            f"已保存到 {result.payload_path}，{result.payload_bytes} 字节"
                            f"{payload_details}"
                        ),
                        compound="top",
                    )
                except Exception:
                    self._show_saved_payload(
                        result, "二进制（无法预览）", payload_guess
                    )
            else:
                self._show_saved_payload(
                    result, "图片（PIL 不可用，按文件打开）", payload_guess
                )
        else:
            self._show_saved_payload(
                result, media_labels.get(media_type, "二进制"), payload_guess
            )
        self.open_payload_button.configure(state="normal")

    def _show_saved_payload(
        self,
        result: BoardVerifyResult,
        media_label: str,
        payload_guess: Optional[PayloadGuess] = None,
    ) -> None:
        self._preview_photo = None
        details = ""
        if payload_guess is not None:
            certainty = "确定" if payload_guess.length_certain else "不确定"
            details = (
                f"\n识别格式：{payload_guess.media_type}"
                f"\n建议扩展名：{payload_guess.extension}"
                f"\n长度是否确定：{certainty}"
                f"\n判定依据：{payload_guess.method}"
            )
            if not payload_guess.length_certain:
                details += "\n载荷长度靠去尾零推测，可能不准。"
        self.preview_label.configure(
            image="",
            text=(
                f"已保存到 {result.payload_path}，{result.payload_bytes} 字节\n"
                f"载荷类型：{media_label}{details}"
            ),
        )

    def _open_output_dir(self) -> None:
        out_dir = Path(self.output_var.get()).expanduser().parent
        self._open_path(out_dir)

    def _open_payload_external(self) -> None:
        if self._last_verify_result and self._last_verify_result.payload_path.is_file():
            self._open_path(self._last_verify_result.payload_path)
        else:
            messagebox.showinfo("提示", "尚未生成已校验的载荷文件。")

    def _open_path(self, path: Path) -> None:
        try:
            if os.name == "nt":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.run(["open", str(path)], check=False)
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
        except Exception as exc:
            messagebox.showerror("打开失败", f"无法打开路径: {exc}")

    # ------------------------------------------------------------- 日志与退出
    def _append_log(self, message: str) -> None:
        text = message.rstrip("\n") + "\n"
        self.log_text.configure(state="normal")

        tag = None
        if text.startswith("[GOLDEN]"):
            tag = "GOLDEN"
        elif text.startswith("[INFO]"):
            tag = "INFO"
        elif text.startswith("[WARN]"):
            tag = "WARN"
        elif text.startswith("[ERROR]"):
            tag = "ERROR"
        elif text.startswith("[FPGA]"):
            tag = "FPGA"
        elif text.startswith("[VERIFY]"):
            tag = "VERIFY"

        if tag:
            self.log_text.insert("end", text, tag)
        else:
            self.log_text.insert("end", text)

        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_logs(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _process_log_queue(self) -> None:
        try:
            while True:
                message = self._log_queue.get_nowait()
                self._append_log(message)
        except Empty:
            pass
        finally:
            self.after(150, self._process_log_queue)

    def _on_close(self) -> None:
        if self._worker and self._worker.is_alive():
            if messagebox.askyesno("正在运行", "后台任务仍在运行，确认强行退出？"):
                self.stop_processing()
                self.destroy()
        else:
            self.destroy()


def main() -> None:
    app = DNAAcceleratorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
