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
   - LDPC:   极速软判/硬判译码。调用 C 原生扩展（c_ldpc / ldpc_pipeline）完成 DVB-S2
             硬判决校验，消除残留误码并还原出 JPEG 图像字节流。
3. 演示与闭环验证：
   - 内置 GOLDEN_IMAGE_SHA256 对还原出的 JPEG 图像进行逐字节 SHA-256 校验；
   - 现场直观呈现图像复原、误码收敛轮数、吞吐率与各级毫秒级度量指标。
=============================================================================
"""

from __future__ import annotations

import hashlib
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import Callable, Optional

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
    ProgressCallbacks,
    ReadFileInfo,
    analyze_reads_file,
    estimate_processing_time,
    format_metric_report,
    run_client,
)
from ldpc_pipeline import LDPCResult, run_ldpc_decoder
from task_protocol import SUPPORTED_READ_BASES, default_score_min

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

# R0.83 黄金图像哈希常数
GOLDEN_IMAGE_SHA256 = "fcd0cf90bd680e7bbdc203e3398119504da0897acac9e2117008b4efb6b1f2c3"

PIPELINE_STAGES = [
    ("CONFIG", "1. 任务配置"),
    ("WM", "2. 水印预载"),
    ("UPLOAD", "3. 读段上传"),
    ("POST", "4. FPGA 加速"),
    ("LDPC", "5. 极速译码"),
]


class DNAAcceleratorApp(tk.Tk):
    """工业级 DNA 加速系统控制台主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.title("FPGA DNA 数据读出硬件加速系统 - 工业控制台")
        self.geometry("1180x820")
        self.minsize(980, 720)

        # 运行时状态 ----------------------------------------------------
        self._defaults = ClientConfig()
        self._worker: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._log_queue: Queue[str] = Queue()

        self._read_info: Optional[ReadFileInfo] = None
        self._last_ldpc_result: Optional[LDPCResult] = None
        self._preview_photo: Optional["ImageTk.PhotoImage"] = None
        self._start_time: float = 0.0
        self._is_running: bool = False

        # Tk 变量 -------------------------------------------------------
        self.ip_var = tk.StringVar(value=self._defaults.ip)
        self.port_var = tk.StringVar(value=str(self._defaults.port))
        self.conn_status_var = tk.StringVar(value="未检测连接")

        self.watermark_var = tk.StringVar(value=str(self._defaults.watermark))
        self.reads_var = tk.StringVar(value=str(self._defaults.reads))
        self.output_var = tk.StringVar(value=str(self._defaults.out))

        # 几何与参数
        self.geom_mode_var = tk.StringVar(value="auto")
        self.score_min_var = tk.StringVar(value="auto")
        self.orient_var = tk.StringVar(value="both")
        self.batch_var = tk.StringVar(value=str(self._defaults.batch))
        self.send_count_var = tk.IntVar(value=self._defaults.total or 4096)
        self.full_scale_var = tk.BooleanVar(value=False)
        self.backend_var = tk.StringVar(value="auto")

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
        self.metric_ldpc_var = tk.StringVar(value="--")
        self.metric_total_var = tk.StringVar(value="--")
        self.image_hash_var = tk.StringVar(value="--")

        # 界面构建
        self._setup_styles()
        self._build_ui()
        self._process_log_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # 启动后尝试探测默认文件
        self.after(300, self._auto_detect_default_reads)

    def _setup_styles(self) -> None:
        style = ttk.Style(self)
        # 支持的主题回退
        themes = style.theme_names()
        if "clam" in themes:
            style.theme_use("clam")

        style.configure("Header.TLabel", font=("Helvetica", 11, "bold"))
        style.configure("Badge.TLabel", font=("Helvetica", 10, "bold"), foreground="#0d47a1")
        style.configure("Timer.TLabel", font=("Courier", 14, "bold"), foreground="#1565c0")
        style.configure("MetricVal.TLabel", font=("Helvetica", 11, "bold"), foreground="#2e7d32")
        style.configure("Accent.TButton", font=("Helvetica", 10, "bold"))

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=8)
        container.pack(fill="both", expand=True)

        # 左右分栏
        paned = ttk.PanedWindow(container, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # 左侧控制面板
        left_frame = ttk.Frame(paned, padding=6)
        paned.add(left_frame, weight=3)

        # 右侧结果与监控面板
        right_frame = ttk.Frame(paned, padding=6)
        paned.add(right_frame, weight=4)

        # 构建左侧
        self._build_conn_card(left_frame)
        self._build_files_card(left_frame)
        self._build_params_card(left_frame)
        self._build_action_card(left_frame)

        # 构建右侧
        self._build_pipeline_card(right_frame)
        self._build_preview_card(right_frame)
        self._build_log_card(right_frame)

    # ------------------------------------------------------------- 左侧构建
    def _build_conn_card(self, parent: ttk.Frame) -> None:
        card = ttk.LabelFrame(parent, text="板端连接配置", padding=8)
        card.pack(fill="x", pady=(0, 6))

        row1 = ttk.Frame(card)
        row1.pack(fill="x")

        ttk.Label(row1, text="IP 地址:").pack(side="left")
        ttk.Entry(row1, textvariable=self.ip_var, width=16).pack(side="left", padx=(4, 12))

        ttk.Label(row1, text="端口:").pack(side="left")
        ttk.Entry(row1, textvariable=self.port_var, width=8).pack(side="left", padx=(4, 12))

        ttk.Button(row1, text="测试连接", command=self._test_connection).pack(side="left", padx=4)
        ttk.Label(row1, textvariable=self.conn_status_var, font=("Helvetica", 9)).pack(side="left", padx=6)

    def _build_files_card(self, parent: ttk.Frame) -> None:
        card = ttk.LabelFrame(parent, text="数据源与自适应探测", padding=8)
        card.pack(fill="x", pady=(0, 6))

        # 文件选择网格
        grid = ttk.Frame(card)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)

        self._add_file_row(grid, 0, "水印序列", self.watermark_var, self._choose_watermark)
        self._add_file_row(grid, 1, "测序 Reads", self.reads_var, self._choose_reads)
        self._add_file_row(grid, 2, "输出目录", self.output_var, self._choose_output)

        # 探测结果徽章横幅
        badge_box = ttk.Frame(card, padding=(4, 6, 4, 4))
        badge_box.pack(fill="x", pady=(6, 0))

        ttk.Label(badge_box, text="数据规格:").grid(row=0, column=0, sticky="w")
        ttk.Label(badge_box, textvariable=self.spec_badge_var, style="Badge.TLabel").grid(
            row=0, column=1, sticky="w", padx=(6, 0)
        )

        ttk.Label(badge_box, text="预计硬件耗时:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(badge_box, textvariable=self.est_time_var, font=("Helvetica", 9, "bold")).grid(
            row=1, column=1, sticky="w", padx=(6, 0), pady=(4, 0)
        )

        btn_box = ttk.Frame(badge_box)
        btn_box.grid(row=0, column=2, rowspan=2, sticky="e", padx=(10, 0))
        ttk.Button(btn_box, text="重新探测", command=self._manual_detect_reads).pack(side="right")

    def _build_params_card(self, parent: ttk.Frame) -> None:
        card = ttk.LabelFrame(parent, text="自适应流水线参数", padding=8)
        card.pack(fill="x", pady=(0, 6))

        g = ttk.Frame(card)
        g.pack(fill="x")
        g.columnconfigure(1, weight=1)
        g.columnconfigure(3, weight=1)

        # 几何模式与读长
        ttk.Label(g, text="几何规格:").grid(row=0, column=0, sticky="w", pady=3)
        geom_cb = ttk.Combobox(
            g,
            textvariable=self.geom_mode_var,
            values=["auto (自适应)", "150 (SE150)", "250 (SE250)"],
            state="readonly",
            width=14,
        )
        geom_cb.grid(row=0, column=1, sticky="w", padx=(4, 8), pady=3)
        geom_cb.bind("<<ComboboxSelected>>", self._on_geom_changed)

        # 匹配阈值
        ttk.Label(g, text="分数阈值:").grid(row=0, column=2, sticky="w", pady=3)
        sbox = ttk.Frame(g)
        sbox.grid(row=0, column=3, sticky="w", padx=4, pady=3)
        ttk.Entry(sbox, textvariable=self.score_min_var, width=8).pack(side="left")
        ttk.Button(sbox, text="推荐", width=4, command=self._apply_recommended_score).pack(side="left", padx=2)

        # 测序方向与批大小
        ttk.Label(g, text="测序方向:").grid(row=1, column=0, sticky="w", pady=3)
        orient_cb = ttk.Combobox(
            g,
            textvariable=self.orient_var,
            values=["both (正反双向-必需)", "forward (仅正向)"],
            state="readonly",
            width=14,
        )
        orient_cb.grid(row=1, column=1, sticky="w", padx=(4, 8), pady=3)
        orient_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_estimate())

        ttk.Label(g, text="传输批大小:").grid(row=1, column=2, sticky="w", pady=3)
        ttk.Entry(g, textvariable=self.batch_var, width=8).grid(row=1, column=3, sticky="w", padx=4, pady=3)

        # 发送条数与全量选择
        ttk.Label(g, text="发送条数:").grid(row=2, column=0, sticky="w", pady=3)
        cnt_box = ttk.Frame(g)
        cnt_box.grid(row=2, column=1, sticky="w", padx=(4, 8), pady=3)
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

        # LDPC 译码后端
        ttk.Label(g, text="LDPC 后端:").grid(row=2, column=2, sticky="w", pady=3)
        backend_cb = ttk.Combobox(
            g,
            textvariable=self.backend_var,
            values=["auto (极速C优先)", "c_accel (C原生加速)", "native (纯Python)", "external (外部EXE)"],
            state="readonly",
            width=12,
        )
        backend_cb.grid(row=2, column=3, sticky="w", padx=4, pady=3)

        # 复选框选项
        chk_box = ttk.Frame(card)
        chk_box.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(chk_box, text="跳过水印预载 (仅调试)", variable=self.skip_wm_var).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(chk_box, text="发送 POST 触发硬件流水线", variable=self.post_var).pack(side="left")

    def _build_action_card(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent, padding=8)
        card.pack(fill="x", pady=(4, 0))

        self.start_button = ttk.Button(
            card,
            text="▶  启动硬件加速全流水线",
            command=self.start_processing,
            style="Accent.TButton",
        )
        self.start_button.pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=6)

        self.stop_button = ttk.Button(
            card,
            text="⏹  停止任务",
            command=self.stop_processing,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=4, ipady=6)

        self.ldpc_only_button = ttk.Button(
            card,
            text="⚡  仅重跑 LDPC 译码",
            command=self._run_ldpc_only,
        )
        self.ldpc_only_button.pack(side="left", padx=(6, 0), ipady=6)

    def _add_file_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command: Callable[[], None],
    ) -> None:
        ttk.Label(parent, text=f"{label}:").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=6, pady=2)
        ttk.Button(parent, text="浏览...", width=7, command=command).grid(row=row, column=2, sticky="e", pady=2)

    # ------------------------------------------------------------- 右侧构建
    def _build_pipeline_card(self, parent: ttk.Frame) -> None:
        card = ttk.LabelFrame(parent, text="硬件流水线状态与性能指标", padding=8)
        card.pack(fill="x", pady=(0, 6))

        # 1. 五段式步进标签
        stepper = ttk.Frame(card)
        stepper.pack(fill="x", pady=(0, 6))
        self.step_labels = {}
        for idx, (token, title) in enumerate(PIPELINE_STAGES):
            lbl = ttk.Label(
                stepper,
                text=f" {title} ",
                relief="groove",
                padding=(4, 2),
                font=("Helvetica", 9),
            )
            lbl.pack(side="left", expand=True, fill="x", padx=1)
            self.step_labels[token] = lbl

        # 2. 进度条与实时计时器
        prog_box = ttk.Frame(card)
        prog_box.pack(fill="x", pady=(2, 4))
        prog_box.columnconfigure(0, weight=1)

        self.upload_bar = ttk.Progressbar(prog_box, maximum=100)
        self.upload_bar.grid(row=0, column=0, sticky="ew")

        ttk.Label(prog_box, textvariable=self.upload_percent_var, width=6, font=("Helvetica", 10, "bold")).grid(
            row=0, column=1, sticky="e", padx=(6, 8)
        )
        ttk.Label(prog_box, textvariable=self.timer_var, style="Timer.TLabel").grid(
            row=0, column=2, sticky="e"
        )

        hint_box = ttk.Frame(card)
        hint_box.pack(fill="x")
        ttk.Label(hint_box, textvariable=self.status_var, font=("Helvetica", 10, "bold")).pack(side="left")
        ttk.Label(hint_box, textvariable=self.upload_hint_var, foreground="#555").pack(side="right")

        # 3. 毫秒级性能指标表格
        metrics = ttk.Frame(card, padding=(0, 6, 0, 0))
        metrics.pack(fill="x")
        for i in range(4):
            metrics.columnconfigure(i, weight=1)

        ttk.Label(metrics, text="上行传输:").grid(row=0, column=0, sticky="w")
        ttk.Label(metrics, textvariable=self.metric_upload_var, style="MetricVal.TLabel").grid(row=0, column=1, sticky="w")

        ttk.Label(metrics, text="FPGA 运算:").grid(row=0, column=2, sticky="w")
        ttk.Label(metrics, textvariable=self.metric_fpga_var, style="MetricVal.TLabel").grid(row=0, column=3, sticky="w")

        ttk.Label(metrics, text="LDPC 译码:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(metrics, textvariable=self.metric_ldpc_var, style="MetricVal.TLabel").grid(row=1, column=1, sticky="w", pady=(4, 0))

        ttk.Label(metrics, text="总端到端:").grid(row=1, column=2, sticky="w", pady=(4, 0))
        ttk.Label(metrics, textvariable=self.metric_total_var, style="MetricVal.TLabel").grid(row=1, column=3, sticky="w", pady=(4, 0))

    def _build_preview_card(self, parent: ttk.Frame) -> None:
        card = ttk.LabelFrame(parent, text="图像还原与黄金校验结果", padding=8)
        card.pack(fill="x", pady=(0, 6))

        top_bar = ttk.Frame(card)
        top_bar.pack(fill="x", pady=(0, 4))

        ttk.Label(top_bar, text="图片 SHA-256:").pack(side="left")
        self.hash_label = ttk.Label(
            top_bar,
            textvariable=self.image_hash_var,
            font=("Courier", 9, "bold"),
            foreground="#333",
        )
        self.hash_label.pack(side="left", padx=(4, 0))

        # 图像预览画布 / Label
        self.preview_container = ttk.Frame(card, height=130, relief="sunken")
        self.preview_container.pack(fill="x", pady=4)
        self.preview_container.pack_propagate(False)

        self.preview_label = ttk.Label(
            self.preview_container,
            text="[暂无图像 - 完成任务后自动渲染预览]",
            anchor="center",
        )
        self.preview_label.pack(expand=True, fill="both")

        # 按钮条
        action_bar = ttk.Frame(card)
        action_bar.pack(fill="x", pady=(4, 0))

        ttk.Button(action_bar, text="打开输出目录", command=self._open_output_dir).pack(side="left")
        ttk.Button(action_bar, text="全尺寸查看图像", command=self._open_image_external).pack(side="left", padx=6)

    def _build_log_card(self, parent: ttk.Frame) -> None:
        card = ttk.LabelFrame(parent, text="运行诊断日志", padding=6)
        card.pack(fill="both", expand=True)

        tool_bar = ttk.Frame(card)
        tool_bar.pack(fill="x", pady=(0, 4))
        ttk.Button(tool_bar, text="清空日志", command=self._clear_logs).pack(side="right")

        self.log_text = ScrolledText(card, height=10, state="disabled", font=("Courier", 9))
        self.log_text.pack(fill="both", expand=True)

        # 配置日志颜色高亮标签
        self.log_text.tag_configure("INFO", foreground="#2e7d32")
        self.log_text.tag_configure("WARN", foreground="#e65100")
        self.log_text.tag_configure("ERROR", foreground="#c62828")
        self.log_text.tag_configure("FPGA", foreground="#0277bd")
        self.log_text.tag_configure("LDPC", foreground="#6a1b9a")
        self.log_text.tag_configure("GOLDEN", foreground="#1565c0", font=("Courier", 9, "bold"))

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

    def _resolve_read_bps(self) -> int:
        mode = self.geom_mode_var.get()
        if "150" in mode:
            return 150
        if "250" in mode:
            return 250
        if self._read_info and self._read_info.detected_read_bps:
            return self._read_info.detected_read_bps
        return 150

    def _refresh_estimate(self) -> None:
        try:
            count = int(self.send_count_var.get())
            orient = "both" if "both" in self.orient_var.get() else "forward"
            sec = estimate_processing_time(count, orient=orient)
            self.est_time_var.set(f"~{sec:.1f} 秒 (模型估算)")
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
        self.update_idletasks()

        def do_ping():
            t0 = time.perf_counter()
            try:
                s = socket.create_connection((ip, port), timeout=1.5)
                s.close()
                dt_ms = (time.perf_counter() - t0) * 1000
                self.after(0, lambda: self.conn_status_var.set(f"🟢 在线 ({dt_ms:.1f} ms)"))
                self.after(0, lambda: self._append_log(f"[INFO] 成功连通板端 {ip}:{port} (RTT {dt_ms:.1f} ms)"))
            except Exception as exc:
                self.after(0, lambda: self.conn_status_var.set("🔴 离线 / 拒绝"))
                self.after(0, lambda: self._append_log(f"[WARN] 无法连接到 {ip}:{port}: {exc}"))

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
            batch = int(self.batch_var.get())
            if batch <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("参数错误", "批大小必须是正整数。")
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

        if not self.skip_wm_var.get() and not watermark_path.is_file():
            messagebox.showerror("文件错误", "水印文件不存在。")
            return
        if not reads_path.is_file():
            messagebox.showerror("文件错误", "FASTQ 文件不存在。")
            return

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not self._read_info or self._read_info.path != reads_path:
            if not self._detect_reads(reads_path):
                return

        read_bps = self._resolve_read_bps()
        score_min_raw = self.score_min_var.get().strip()
        score_min = int(score_min_raw) if score_min_raw.isdigit() else default_score_min(read_bps)
        orient = "both" if "both" in self.orient_var.get() else "forward"

        config = ClientConfig(
            ip=self.ip_var.get().strip() or self._defaults.ip,
            port=port,
            watermark=watermark_path,
            reads=reads_path,
            out=output_path,
            batch=batch,
            total=self._read_info.total_reads,
            send_limit=send_count,
            skip_wm=self.skip_wm_var.get(),
            post=self.post_var.get(),
            format=self._read_info.format,
            orient=orient,
            read_bps=read_bps,
            score_min=score_min,
            result_timeout=max(180.0, estimate_processing_time(send_count, orient=orient) * 2.0 + 30.0),
        )

        self._reset_progress()
        self._append_log("=" * 60)
        self._append_log(f"[INFO] 启动硬件加速流水线: {read_bps}bp | score_min={score_min} | {send_count}条 | {orient}")
        self._update_status("正在启动任务 ...")

        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.ldpc_only_button.configure(state="disabled")

        self._start_time = time.perf_counter()
        self._is_running = True
        self._update_timer()

        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._run_client_task, args=(config,), daemon=True)
        self._worker.start()

    def stop_processing(self) -> None:
        if self._stop_event is None or self._stop_event.is_set():
            return
        self._append_log("[INFO] 收到用户中止请求，正在通知后台任务 ...")
        self._stop_event.set()

    def _run_client_task(self, config: ClientConfig) -> None:
        def log_fn(message: str) -> None:
            self._log_queue.put(message)

        callbacks = ProgressCallbacks(
            update_status=lambda msg: self.after(0, self._update_status, msg),
            update_upload=lambda sent, total: self.after(0, self._update_upload_progress, sent, total),
            update_stage_label=lambda stage: self.after(0, self._set_active_stage, stage),
        )

        try:
            self.after(0, self._set_active_stage, "CONFIG")
            stats = run_client(config, log=log_fn, progress=callbacks, stop_event=self._stop_event)
            log_fn(format_metric_report(stats))

            # 记录网络与 FPGA 硬件阶段耗时
            self.after(0, lambda: self.metric_upload_var.set(f"{stats.t_batches:.2f} s"))
            self.after(0, lambda: self.metric_fpga_var.set(f"{stats.t_result:.2f} s"))

            # 进入 LDPC 译码阶段
            self.after(0, self._set_active_stage, "LDPC")
            self.after(0, self._update_status, "执行 LDPC 极速译码 ...")

            backend = self._resolve_backend_mode()
            t_ldpc_start = time.perf_counter()
            ldpc_result = run_ldpc_decoder(
                Path(config.out),
                output_dir=Path(config.out).resolve().parent,
                backend=backend,
                log=log_fn,
            )
            t_ldpc = (time.perf_counter() - t_ldpc_start) * 1000
            self.after(0, lambda: self.metric_ldpc_var.set(f"{t_ldpc:.1f} ms ({ldpc_result.backend})"))

            # 完成
            self.after(0, self._handle_ldpc_result, ldpc_result)
            self.after(0, self._on_run_complete, True, None)
        except OperationCancelled:
            log_fn("[INFO] 任务已被用户取消")
            self.after(0, self._on_run_complete, False, "Operation cancelled")
        except Exception as exc:
            log_fn(f"[ERROR] {exc}")
            self.after(0, self._on_run_complete, False, str(exc))

    def _resolve_backend_mode(self) -> str:
        b = self.backend_var.get()
        if "c_accel" in b:
            return "c_accel"
        if "native" in b:
            return "native"
        if "external" in b:
            return "external"
        return "auto"

    def _run_ldpc_only(self) -> None:
        out_file = Path(self.output_var.get()).expanduser()
        if not out_file.is_file():
            messagebox.showerror("文件不存在", f"结果文件未找到: {out_file}\n请先运行全流水线或指定已有 dec_input.txt。")
            return

        backend = self._resolve_backend_mode()
        self._set_active_stage("LDPC")
        self._append_log(f"[INFO] 启动单独 LDPC 译码: {out_file} (模式: {backend})")

        def do_decode():
            def log_fn(message: str) -> None:
                self._log_queue.put(message)

            t0 = time.perf_counter()
            try:
                res = run_ldpc_decoder(out_file, output_dir=out_file.parent, backend=backend, log=log_fn)
                dt_ms = (time.perf_counter() - t0) * 1000
                self.after(0, lambda: self.metric_ldpc_var.set(f"{dt_ms:.1f} ms ({res.backend})"))
                self.after(0, self._handle_ldpc_result, res)
                self.after(0, lambda: messagebox.showinfo("LDPC 译码完成", f"译码成功！耗时: {dt_ms:.1f} ms"))
            except Exception as exc:
                log_fn(f"[LDPC-ERROR] {exc}")
                self.after(0, lambda: messagebox.showerror("LDPC 失败", str(exc)))
            finally:
                self.after(0, self._set_active_stage, "")

        threading.Thread(target=do_decode, daemon=True).start()

    # ------------------------------------------------------------- 回调与状态
    def _on_run_complete(self, success: bool, error: Optional[str]) -> None:
        self._is_running = False
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.ldpc_only_button.configure(state="normal")
        self._set_active_stage("")

        dt_total = time.perf_counter() - self._start_time
        self.metric_total_var.set(f"{dt_total:.2f} s")

        if success:
            self._append_log(f"[INFO] 全流水线处理完成！总耗时: {dt_total:.2f}s")
            self._update_status("全流程运行完成")
        else:
            if error == "Operation cancelled":
                self._append_log("[INFO] 任务已取消")
                self._update_status("任务已取消")
            else:
                self._update_status("运行异常终止")
                messagebox.showerror("运行失败", error or "未知错误")

        self._worker = None
        self._stop_event = None

    def _set_active_stage(self, stage: str) -> None:
        stage_token = (stage or "").upper()
        self.active_stage_var.set(stage_token)

        for token, lbl in self.step_labels.items():
            if token == stage_token:
                lbl.configure(background="#1976d2", foreground="white", font=("Helvetica", 9, "bold"))
            else:
                lbl.configure(background="#f0f0f0", foreground="#333", font=("Helvetica", 9))

    def _update_status(self, message: str) -> None:
        self.status_var.set(message)

    def _update_upload_progress(self, sent: int, total: int) -> None:
        total = max(total, 1)
        percent = int((sent / total) * 100)
        percent = max(0, min(100, percent))
        self.upload_bar.configure(value=percent)
        self.upload_percent_var.set(f"{percent}%")
        self.upload_hint_var.set(f"已发送 {sent:,}/{total:,} 条读段")

    def _reset_progress(self) -> None:
        self.upload_bar.configure(value=0)
        self.upload_percent_var.set("0%")
        self.upload_hint_var.set("等待传输")
        self.metric_upload_var.set("--")
        self.metric_fpga_var.set("--")
        self.metric_ldpc_var.set("--")
        self.metric_total_var.set("--")
        self.image_hash_var.set("--")
        self.hash_label.configure(foreground="#333")

    def _update_timer(self) -> None:
        if self._is_running:
            elapsed = int(time.perf_counter() - self._start_time)
            mins = elapsed // 60
            secs = elapsed % 60
            self.timer_var.set(f"{mins:02d}:{secs:02d}")
            self.after(500, self._update_timer)

    # ------------------------------------------------------------- 图像与输出
    def _handle_ldpc_result(self, result: LDPCResult) -> None:
        self._last_ldpc_result = result
        img_bytes = result.image_path.read_bytes()
        sha256 = hashlib.sha256(img_bytes).hexdigest()

        # 校验哈希并高亮
        is_golden = (sha256 == GOLDEN_IMAGE_SHA256)
        status_txt = f"{sha256[:16]}...{sha256[-8:]}" + (" [PASS 逐位吻合]" if is_golden else " [可还原]")
        self.image_hash_var.set(status_txt)
        self.hash_label.configure(foreground="#2e7d32" if is_golden else "#1565c0")

        self._append_log(f"[LDPC] 解码图像 SHA-256: {sha256}")
        if is_golden:
            self._append_log("[GOLDEN] 恭喜！板端回传还原图像与 R0.83 黄金基线 100% 逐位吻合！")

        # 渲染缩略图
        if Image is not None and ImageTk is not None:
            try:
                im = Image.open(result.image_path)
                # 保持纵横比缩放到 120px 高度
                w, h = im.size
                scale = min(220 / max(w, 1), 120 / max(h, 1))
                new_w = max(1, int(w * scale))
                new_h = max(1, int(h * scale))
                im_thumb = im.resize((new_w, new_h), Image.Resampling.LANCZOS)
                self._preview_photo = ImageTk.PhotoImage(im_thumb)
                self.preview_label.configure(image=self._preview_photo, text="")
            except Exception as exc:
                self.preview_label.configure(image="", text=f"预览加载失败: {exc}")
        else:
            self.preview_label.configure(image="", text=f"图像已保存至 {result.image_path.name}")

    def _open_output_dir(self) -> None:
        out_dir = Path(self.output_var.get()).expanduser().parent
        self._open_path(out_dir)

    def _open_image_external(self) -> None:
        if self._last_ldpc_result and self._last_ldpc_result.image_path.is_file():
            self._open_path(self._last_ldpc_result.image_path)
        else:
            messagebox.showinfo("提示", "尚未生成还原图像文件。")

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
        elif text.startswith("[ERROR]") or text.startswith("[LDPC-ERROR]"):
            tag = "ERROR"
        elif text.startswith("[FPGA]"):
            tag = "FPGA"
        elif text.startswith("[LDPC]"):
            tag = "LDPC"

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
