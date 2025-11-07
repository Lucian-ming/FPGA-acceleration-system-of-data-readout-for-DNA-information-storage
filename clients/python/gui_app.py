#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tkinter GUI wrapper around the DNA accelerator client workflow."""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from queue import Empty, Queue
from typing import Callable, Optional

import sys

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from first import (
    ClientConfig,
    MAX_TOTAL_READS,
    OperationCancelled,
    ProgressCallbacks,
    ReadFileInfo,
    analyze_reads_file,
    format_metric_report,
    run_client,
)
from ldpc_pipeline import LDPCResult, run_ldpc_decoder

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover - optional visual dependency
    Image = None
    ImageTk = None

CLIENT_STAGE_HINTS = {
    "UPLOAD": "发送读段数据",
    "POST": "触发加速器处理",
    "RESULT": "接收并保存结果",
    "IDLE": "准备接收",
}


class DNAAcceleratorApp(tk.Tk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("DNA Accelerator Client")
        self.geometry("960x760")
        self.minsize(820, 640)

        # Runtime state -----------------------------------------------------
        self._defaults = ClientConfig()
        self._worker: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._log_queue: Queue[str] = Queue()

        self._read_info: Optional[ReadFileInfo] = None
        self._ldpc_window: Optional[tk.Toplevel] = None
        self._ldpc_photo: Optional["ImageTk.PhotoImage"] = None

        # Tk variables ------------------------------------------------------
        self.ip_var = tk.StringVar(value=self._defaults.ip)
        self.port_var = tk.StringVar(value=str(self._defaults.port))
        self.watermark_var = tk.StringVar(value=str(self._defaults.watermark))
        self.reads_var = tk.StringVar(value=str(self._defaults.reads))
        self.output_var = tk.StringVar(value=str(self._defaults.out))

        self.batch_var = tk.StringVar(value=str(self._defaults.batch))
        self.skip_wm_var = tk.BooleanVar(value=self._defaults.skip_wm)
        self.post_var = tk.BooleanVar(value=self._defaults.post)

        self.status_var = tk.StringVar(value="等待开始")
        self.upload_percent_var = tk.StringVar(value="0%")
        self.upload_hint_var = tk.StringVar(value="等待上传")
        self.detected_reads_var = tk.StringVar(value="未检测")

        self.send_count_var = tk.IntVar(value=0)

        # Build UI ----------------------------------------------------------
        self._build_ui()
        self._process_log_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Do an initial detection if default read file exists.
        self.after(200, self._auto_detect_default_reads)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        main = ttk.Frame(self, padding=12)
        main.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)
        for idx in range(8):
            main.rowconfigure(idx, weight=0)
        main.rowconfigure(7, weight=1)

        self._build_connection_frame(main)
        self._build_files_frame(main)
        self._build_params_frame(main)
        self._build_progress_frame(main)
        self._build_status_frame(main)
        self._build_log_frame(main)

    def _build_connection_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="服务器连接", padding=12)
        frame.grid(row=0, column=0, sticky="ew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="IP 地址:").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.ip_var).grid(row=0, column=1, sticky="ew")

        ttk.Label(frame, text="端口:").grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Entry(frame, textvariable=self.port_var, width=10).grid(row=0, column=3, sticky="w")

    def _build_files_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="数据文件", padding=12)
        frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        frame.columnconfigure(1, weight=1)

        self._add_file_selector(frame, 0, "水印文件", self.watermark_var, self._choose_watermark)
        self._add_file_selector(frame, 1, "FASTQ 文件", self.reads_var, self._choose_reads)
        self._add_file_selector(frame, 2, "结果输出", self.output_var, self._choose_output)

        ttk.Label(frame, text="检测读段:").grid(row=3, column=0, sticky="w", pady=(6, 0))
        ttk.Label(frame, textvariable=self.detected_reads_var).grid(row=3, column=1, sticky="w", pady=(6, 0))
        ttk.Button(frame, text="重新检测", command=self._manual_detect_reads).grid(row=3, column=2, sticky="ew", pady=(6, 0))

        ttk.Label(frame, text="发送条数:").grid(row=4, column=0, sticky="w", pady=(6, 0))
        self.send_spin = ttk.Spinbox(
            frame,
            from_=1,
            to=MAX_TOTAL_READS,
            textvariable=self.send_count_var,
            width=12,
        )
        self.send_spin.grid(row=4, column=1, sticky="w", pady=(6, 0))

    def _build_params_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="运行参数", padding=12)
        frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="批大小:").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.batch_var, width=10).grid(row=0, column=1, sticky="w")

        ttk.Checkbutton(frame, text="跳过水印传输", variable=self.skip_wm_var).grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Checkbutton(frame, text="发送 POST 触发处理", variable=self.post_var).grid(
            row=1, column=1, sticky="w", pady=(6, 0)
        )

    def _build_progress_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="进度", padding=12)
        frame.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="上传进度:").grid(row=0, column=0, sticky="w")
        self.upload_bar = ttk.Progressbar(frame, maximum=100)
        self.upload_bar.grid(row=0, column=1, sticky="ew")
        ttk.Label(frame, textvariable=self.upload_percent_var, width=7).grid(row=0, column=2, sticky="e", padx=(8, 0))
        ttk.Label(frame, textvariable=self.upload_hint_var).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(4, 0)
        )

    def _build_status_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, padding=(0, 10, 0, 0))
        frame.grid(row=5, column=0, sticky="ew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="状态:").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, textvariable=self.status_var).grid(row=0, column=1, sticky="w")

        self.start_button = ttk.Button(frame, text="开始运行", command=self.start_processing)
        self.start_button.grid(row=0, column=2, padx=(10, 0))

        self.stop_button = ttk.Button(frame, text="停止", command=self.stop_processing, state="disabled")
        self.stop_button.grid(row=0, column=3, padx=(10, 0))

    def _build_log_frame(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="日志", padding=12)
        frame.grid(row=6, column=0, sticky="nsew", pady=(10, 0))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.log_text = ScrolledText(frame, height=16, state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")

    def _add_file_selector(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command: Callable[[], None],
    ) -> None:
        ttk.Label(parent, text=f"{label}:").grid(row=row, column=0, sticky="w")
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", padx=(6, 6))
        ttk.Button(parent, text="选择...", command=command).grid(row=row, column=2, sticky="ew")

    # ----------------------------------------------------------- interactions
    def start_processing(self) -> None:
        if self._worker and self._worker.is_alive():
            messagebox.showinfo("正在运行", "后台任务尚未结束，请先停止。")
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

        if not output_path.parent.exists():
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("路径错误", f"无法创建输出目录: {exc}")
                return

        # Ensure read info available
        if not self._read_info or self._read_info.path != reads_path:
            if not self._detect_reads(reads_path):
                return

        detected_total = self._read_info.total_reads if self._read_info else send_count
        if detected_total < 1:
            messagebox.showerror("检测失败", "无法确定读取总数，请检查文件。")
            return

        config = ClientConfig(
            ip=self.ip_var.get().strip() or self._defaults.ip,
            port=port,
            watermark=watermark_path,
            reads=reads_path,
            out=output_path,
            batch=batch,
            total=detected_total,
            send_limit=send_count,
            skip_wm=self.skip_wm_var.get(),
            post=self.post_var.get(),
            format=self._read_info.format if self._read_info else "auto",
        )

        self._reset_progress()
        self._append_log("================ 开始新的任务 ================")
        self._update_status("启动后台任务 ...")

        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")

        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._run_client_task, args=(config,), daemon=True)
        self._worker.start()

    def stop_processing(self) -> None:
        if self._stop_event is None or self._stop_event.is_set():
            return
        self._append_log("[INFO] 请求停止后台任务 ...")
        self._stop_event.set()

    def _run_client_task(self, config: ClientConfig) -> None:
        def log_fn(message: str) -> None:
            self._log_queue.put(message)

        callbacks = ProgressCallbacks(
            update_status=lambda msg: self.after(0, self._update_status, msg),
            update_upload=lambda sent, total: self.after(0, self._update_upload_progress, sent, total),
            update_stage_label=lambda stage: self.after(0, self._apply_stage_label, stage),
        )

        try:
            stats = run_client(config, log=log_fn, progress=callbacks, stop_event=self._stop_event)
            log_fn(format_metric_report(stats))
            self.after(0, self._update_status, "LDPC 解码中...")
            try:
                ldpc_result = run_ldpc_decoder(
                    Path(config.out),
                    output_dir=Path(config.out).resolve().parent,
                    log=log_fn,
                )
            except Exception as exc:  # noqa: BLE001
                log_fn(f"[LDPC-ERROR] {exc}")
                self.after(0, self._on_run_complete, False, f"LDPC 解码失败: {exc}")
                return
            self.after(0, self._handle_ldpc_result, ldpc_result)
            self.after(0, self._on_run_complete, True, None)
        except OperationCancelled:
            log_fn("[INFO] 任务已取消")
            self.after(0, self._on_run_complete, False, "Operation cancelled")
        except Exception as exc:  # noqa: BLE001
            log_fn(f"[ERROR] {exc}")
            self.after(0, self._on_run_complete, False, str(exc))

    # ------------------------------------------------------------- callbacks
    def _on_run_complete(self, success: bool, error: Optional[str]) -> None:
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

        if success:
            self._append_log("[INFO] 任务完成")
            self._update_status("任务完成")
        else:
            if error == "Operation cancelled":
                self._append_log("[INFO] 任务已取消")
                self._update_status("已取消")
            else:
                self._update_status("发生错误")
                messagebox.showerror("运行失败", error or "未知错误")

        self._worker = None
        self._stop_event = None

    def _process_log_queue(self) -> None:
        try:
            while True:
                message = self._log_queue.get_nowait()
                self._append_log(message)
        except Empty:
            pass
        finally:
            self.after(200, self._process_log_queue)

    # ------------------------------------------------------------- GUI utils
    def _append_log(self, message: str) -> None:
        text = message.rstrip("\n") + "\n"
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _reset_progress(self) -> None:
        self.upload_bar.configure(value=0)
        self.upload_percent_var.set("0%")
        self.upload_hint_var.set("等待上传")

    def _update_status(self, message: str) -> None:
        self.status_var.set(message)

    def _apply_stage_label(self, stage: str) -> None:
        stage_token = (stage or "").upper()
        self.upload_hint_var.set(CLIENT_STAGE_HINTS.get(stage_token, stage_token or ""))

    def _update_upload_progress(self, sent: int, total: int) -> None:
        total = max(total, 1)
        percent = int((sent / total) * 100)
        percent = max(0, min(100, percent))
        self.upload_bar.configure(value=percent)
        self.upload_percent_var.set(f"{percent}%")
        self.upload_hint_var.set(f"已发送 {sent}/{total} 条读段")

    def _handle_ldpc_result(self, result: LDPCResult) -> None:
        self._append_log("[LDPC] 解码流程完成")
        self._append_log(f"[LDPC] dec_input: {result.dec_input_path}")
        self._append_log(f"[LDPC] 解码比特: {result.decoded_bits_path}")
        self._append_log(f"[LDPC] 图像: {result.image_path}")

        if Image is None or ImageTk is None:
            messagebox.showinfo(
                "LDPC 解码完成",
                (
                    "LDPC 解码已完成。\n\n"
                    f"dec_input.txt: {result.dec_input_path}\n"
                    f"decoded_bits.txt: {result.decoded_bits_path}\n"
                    f"image: {result.image_path}\n\n"
                    "已保存输出，请使用外部程序查看图像。"
                ),
            )
            return

        try:
            image = Image.open(result.image_path)
        except Exception as exc:  # noqa: BLE001
            self._append_log(f"[LDPC-ERROR] 无法加载图像: {exc}")
            messagebox.showerror("图像加载失败", f"无法打开解码图像: {exc}")
            return

        if self._ldpc_window is not None and self._ldpc_window.winfo_exists():
            self._ldpc_window.destroy()

        self._ldpc_window = tk.Toplevel(self)
        self._ldpc_window.title("LDPC 解码图像")

        photo = ImageTk.PhotoImage(image)
        self._ldpc_photo = photo  # 保持引用防止被垃圾回收

        image_label = ttk.Label(self._ldpc_window, image=photo)
        image_label.pack(padx=10, pady=10)

        button_frame = ttk.Frame(self._ldpc_window, padding=10)
        button_frame.pack(fill="x")

        ttk.Button(
            button_frame,
            text="打开输出目录",
            command=lambda: self._open_path(result.decoded_bits_path.parent),
        ).pack(side="left")

        ttk.Button(
            button_frame,
            text="关闭",
            command=self._ldpc_window.destroy,
        ).pack(side="right")

    def _open_path(self, path: Path) -> None:
        try:
            if os.name == "nt":
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.run(["open", str(path)], check=False)
            else:
                subprocess.run(["xdg-open", str(path)], check=False)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("打开失败", f"无法打开路径: {exc}")

    # ------------------------------------------------------------- detection
    def _detect_reads(self, path: Path) -> bool:
        try:
            info = analyze_reads_file(path)
        except Exception as exc:
            messagebox.showerror("检测失败", f"统计读段数量失败: {exc}")
            self.detected_reads_var.set("检测失败")
            self._read_info = None
            return False

        reads = max(info.total_reads, 1)
        self._read_info = info
        self.detected_reads_var.set(f"{reads:,} 条 ({info.format.upper()})")
        self.send_spin.configure(to=max(reads, 1))
        self.send_count_var.set(reads)
        return True

    def _manual_detect_reads(self) -> None:
        reads_path = Path(self.reads_var.get()).expanduser()
        if not reads_path.is_file():
            messagebox.showerror("文件错误", "FASTQ 文件不存在。")
            return
        self._detect_reads(reads_path)

    def _auto_detect_default_reads(self) -> None:
        reads_path = Path(self.reads_var.get()).expanduser()
        if reads_path.is_file():
            self._detect_reads(reads_path)

    # ------------------------------------------------------------- file dialogs
    def _choose_watermark(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 watermark.txt",
            filetypes=[("Text", "*.txt"), ("All Files", "*.*")],
        )
        if path:
            self.watermark_var.set(path)

    def _choose_reads(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 read.fastq",
            filetypes=[("FASTQ", "*.fastq"), ("Text", "*.txt"), ("All Files", "*.*")],
        )
        if path:
            self.reads_var.set(path)
            self._detect_reads(Path(path))

    def _choose_output(self) -> None:
        initial = Path(self.output_var.get()).expanduser()
        path = filedialog.asksaveasfilename(
            title="选择结果保存位置",
            defaultextension=".txt",
            initialfile=initial.name,
            initialdir=str(initial.parent) if initial.parent.exists() else None,
            filetypes=[("Text", "*.txt"), ("All Files", "*.*")],
        )
        if path:
            self.output_var.set(path)

    # ------------------------------------------------------------- lifecycle
    def _on_close(self) -> None:
        if self._worker and self._worker.is_alive():
            if not messagebox.askyesno("确认退出", "任务正在运行，确认要退出并尝试停止吗？"):
                return
            if self._stop_event is not None and not self._stop_event.is_set():
                self._stop_event.set()
        self.destroy()


def main() -> None:
    app = DNAAcceleratorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
