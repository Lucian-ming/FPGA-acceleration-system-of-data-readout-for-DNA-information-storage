#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""现代化工业级上位机客户端 UI 主题与视觉样式规范 (Tkinter / TTK)。

本模块集中管理:
1. 工业级现代调色板 (Slate + Tech Blue + Emerald Green + Crimson Red);
2. 跨平台字体策略 (Windows / macOS / Linux 字体回落与字号梯度);
3. 高分屏 DPI 缩放感知与窗口居中辅助;
4. TTK 'clam' 主题定制 (输入框、卡片、主操作按钮、危险操作按钮、进度条);
5. 现代柔和圆角组件库:
   - draw_rounded_rect: 高平滑贝塞尔圆角多边形绘制
   - RoundedPill: 柔和圆角胶囊组件 (用于五段式流水线芯片、顶标徽章)
   - RoundedButton: 柔和圆角操作按钮 (支持平滑 hover、点击态与禁用态)
   - RoundedMetricTile: 柔和圆角微卡片 (用于 2x2 性能指标仪表)
   - RoundedStatusBanner: 柔和圆角动态状态横幅 (随流水线状态自动变色)
   - RoundedCard: 柔和圆角容器底板
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Callable, Dict, Optional, Tuple

# =============================================================================
# 1. 调色板 (Modern Industrial Dashboard Palette)
# =============================================================================

# 表面与背景
COLOR_WINDOW_BG = "#f1f5f9"       # Slate-100: 窗口全局底色
COLOR_CARD_BG = "#ffffff"         # 纯白卡片面板底色
COLOR_CARD_ALT = "#f8fafc"        # Slate-50: 辅助区域/输入底色
COLOR_HEADER_BG = "#ffffff"       # 顶部标头栏底色

# 边框与分割线
COLOR_BORDER = "#cbd5e1"          # Slate-300: 标准边框
COLOR_BORDER_LIGHT = "#e2e8f0"    # Slate-200: 浅边框/分割线
COLOR_BORDER_FOCUS = "#3b82f6"    # Blue-500: 聚焦边框

# 文字层级
COLOR_TEXT_PRIMARY = "#0f172a"    # Slate-900: 主要标题与正文
COLOR_TEXT_SECONDARY = "#475569"  # Slate-600: 次要说明与标签
COLOR_TEXT_MUTED = "#94a3b8"      # Slate-400: 弱化/占位文字
COLOR_TEXT_INVERT = "#ffffff"     # 反白文字

# 品牌主色 (Tech Blue)
COLOR_PRIMARY = "#2563eb"         # Blue-600: 主操作按钮、当前激活阶段
COLOR_PRIMARY_HOVER = "#1d4ed8"   # Blue-700
COLOR_PRIMARY_ACTIVE = "#1e40af"  # Blue-800
COLOR_PRIMARY_BG = "#eff6ff"      # Blue-50: 浅蓝指示底色
COLOR_PRIMARY_BORDER = "#93c5fd"  # Blue-300

# 状态语义色 - 成功 (Emerald Green)
COLOR_SUCCESS = "#16a34a"         # Green-600: 校验通过、完成阶段
COLOR_SUCCESS_HOVER = "#15803d"   # Green-700
COLOR_SUCCESS_BG = "#dcfce7"      # Green-100: 成功横幅浅底
COLOR_SUCCESS_BORDER = "#86efac"  # Green-300
COLOR_SUCCESS_TEXT = "#166534"    # Green-800

# 状态语义色 - 失败 (Crimson Red) - 必须极其醒目
COLOR_DANGER = "#dc2626"          # Red-600: 校验未通过、致命错误
COLOR_DANGER_HOVER = "#b91c1c"    # Red-700
COLOR_DANGER_BG = "#fee2e2"       # Red-100: 失败横幅浅底
COLOR_DANGER_BORDER = "#fca5a5"   # Red-300
COLOR_DANGER_TEXT = "#991b1b"     # Red-800

# 状态语义色 - 警告 / 运行中 (Amber)
COLOR_WARNING = "#d97706"         # Amber-600: 警告
COLOR_WARNING_BG = "#fef3c7"      # Amber-100
COLOR_WARNING_BORDER = "#fcd34d"  # Amber-300
COLOR_WARNING_TEXT = "#92400e"    # Amber-800

# 状态语义色 - 信息 (Sky Blue)
COLOR_INFO = "#0284c7"            # Sky-600: 探测信息
COLOR_INFO_BG = "#e0f2fe"         # Sky-100
COLOR_INFO_BORDER = "#7dd3fc"
COLOR_INFO_TEXT = "#075985"

# 胶囊步进器 (Capsule Stepper) 状态配色映射
STEP_PALETTE = {
    "idle": {
        "bg": "#f1f5f9",
        "fg": "#475569",
        "border": "#cbd5e1",
        "prefix": "○",
    },
    "active": {
        "bg": "#2563eb",
        "fg": "#ffffff",
        "border": "#1d4ed8",
        "prefix": "●",
    },
    "done": {
        "bg": "#16a34a",
        "fg": "#ffffff",
        "border": "#15803d",
        "prefix": "✓",
    },
    "failed": {
        "bg": "#dc2626",
        "fg": "#ffffff",
        "border": "#b91c1c",
        "prefix": "✗",
    },
}

# 诊断终端日志配色 (Modern Dark Slate Terminal)
LOG_TERMINAL_BG = "#0f172a"        # Slate-900: 终端纯黑底色
LOG_TERMINAL_FG = "#e2e8f0"        # Slate-200: 终端默认字色
LOG_TERMINAL_SELECT = "#334155"    # Slate-700: 选中文本底色
LOG_TAG_COLORS = {
    "GOLDEN": {"fg": "#60a5fa", "bold": True},   # Blue-400
    "INFO": {"fg": "#4ade80", "bold": False},    # Green-400
    "WARN": {"fg": "#fbbf24", "bold": False},    # Amber-400
    "ERROR": {"fg": "#f87171", "bold": True},    # Red-400
    "FPGA": {"fg": "#38bdf8", "bold": False},    # Sky-400
    "VERIFY": {"fg": "#c084fc", "bold": False},  # Purple-400
}


# =============================================================================
# 2. 跨平台字体策略与字号阶梯
# =============================================================================

def resolve_font_families() -> Tuple[str, str]:
    """返回适合当前操作系统的 (无衬线字体, 等宽字体)。"""
    if sys.platform == "win32":
        sans = "Microsoft YaHei UI"
        mono = "Consolas"
    elif sys.platform == "darwin":
        sans = "PingFang SC"
        mono = "Menlo"
    else:
        # Linux / X11 环境：优先选择中文字体微米黑，回退到 DejaVu
        sans = "WenQuanYi Micro Hei"
        mono = "DejaVu Sans Mono"
    return sans, mono


class FontRegistry:
    """管理全局字体对象与统一阶梯。"""

    def __init__(self, root: tk.Tk) -> None:
        self.sans, self.mono = resolve_font_families()

        # 检查字体是否真实可用，不可用时回落
        try:
            available = set(tkfont.families(root))
            if self.sans not in available:
                for candidate in ("Microsoft YaHei UI", "WenQuanYi Micro Hei", "Noto Sans CJK SC", "DejaVu Sans", "Helvetica"):
                    if candidate in available:
                        self.sans = candidate
                        break
            if self.mono not in available:
                for candidate in ("Consolas", "DejaVu Sans Mono", "Courier New", "Courier"):
                    if candidate in available:
                        self.mono = candidate
                        break
        except Exception:
            pass

        # 字号阶梯 (Title / Header / Body / Caption / Mono)
        self.app_title = (self.sans, 13, "bold")
        self.card_header = (self.sans, 10, "bold")
        self.body = (self.sans, 9)
        self.body_bold = (self.sans, 9, "bold")
        self.caption = (self.sans, 8)
        self.caption_bold = (self.sans, 8, "bold")

        self.mono_body = (self.mono, 9)
        self.mono_bold = (self.mono, 9, "bold")
        self.mono_timer = (self.mono, 15, "bold")
        self.mono_metric = (self.mono, 11, "bold")


# =============================================================================
# 3. DPI 感知与窗口定位
# =============================================================================

def enable_windows_dpi_awareness() -> None:
    """在 Windows 环境下激活 Per-Monitor DPI 感知，避免高分屏字迹发虚。"""
    if sys.platform == "win32":
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def center_window(window: tk.Tk, width: int = 1240, height: int = 860) -> None:
    """设置窗口默认尺寸并在屏幕居中，同时设置合理的最小尺寸约束。"""
    window.update_idletasks()
    screen_w = window.winfo_screenwidth()
    screen_h = window.winfo_screenheight()

    target_w = min(width, max(1000, screen_w - 40))
    target_h = min(height, max(700, screen_h - 60))

    x = max(0, (screen_w - target_w) // 2)
    y = max(0, (screen_h - target_h) // 2)

    window.geometry(f"{target_w}x{target_h}+{x}+{y}")
    window.minsize(1040, 720)


# =============================================================================
# 4. 柔和圆角图形与现代组件库 (Rounded Geometry & Modern Components)
# =============================================================================

def draw_rounded_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: int = 8, **kwargs) -> int:
    """在 Canvas 上利用贝塞尔多边形绘制平滑的抗锯齿圆角矩形。"""
    r = max(2, min(radius, int(abs(x2 - x1) / 2), int(abs(y2 - y1) / 2)))
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def get_parent_bg(parent: tk.Widget, default: str = COLOR_CARD_BG) -> str:
    """安全获取父级容器背景色，兼顾 tk.Widget 与 ttk.Widget。"""
    if hasattr(parent, "cget"):
        for opt in ("bg", "background"):
            try:
                val = parent.cget(opt)
                if val:
                    return val
            except Exception:
                pass
        try:
            # 兼容 ttk 控件样式背景查询
            st = parent.cget("style")
            if not st:
                st = getattr(parent, "default_style", "") or parent.winfo_class()
            val = ttk.Style(parent).lookup(st, "background")
            if val:
                return val
        except Exception:
            pass
    return default


class RoundedPill(tk.Canvas):
    """现代柔和圆角胶囊组件 (支持动态更新文本、字重与语义色)。"""

    def __init__(
        self,
        parent: tk.Widget,
        text: str = "Pill",
        bg_color: str = "#f1f5f9",
        fg_color: str = "#475569",
        border_color: str = "#cbd5e1",
        font: Tuple = ("DejaVu Sans", 9),
        radius: int = 10,
        width: int = 90,
        height: int = 28,
        **kwargs,
    ) -> None:
        parent_bg = get_parent_bg(parent, default=COLOR_CARD_BG)
        super().__init__(parent, width=width, height=height, bg=parent_bg, highlightthickness=0, **kwargs)
        self.text = text
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.border_color = border_color
        self.font = font
        self.radius = radius
        self.bind("<Configure>", self._redraw)

    def set_visuals(
        self,
        text: Optional[str] = None,
        bg_color: Optional[str] = None,
        fg_color: Optional[str] = None,
        border_color: Optional[str] = None,
        font: Optional[Tuple] = None,
    ) -> None:
        if text is not None:
            self.text = text
        if bg_color is not None:
            self.bg_color = bg_color
        if fg_color is not None:
            self.fg_color = fg_color
        if border_color is not None:
            self.border_color = border_color
        if font is not None:
            self.font = font
        self._redraw()

    def _redraw(self, event=None) -> None:
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10:
            return
        draw_rounded_rect(
            self,
            2,
            2,
            w - 2,
            h - 2,
            radius=self.radius,
            fill=self.bg_color,
            outline=self.border_color,
            width=1,
        )
        self.create_text(w / 2, h / 2, text=self.text, fill=self.fg_color, font=self.font)


class RoundedButton(tk.Canvas):
    """现代柔和圆角操作按钮 (支持平滑 Hover、点击交互及禁用态)。"""

    def __init__(
        self,
        parent: tk.Widget,
        text: str = "Button",
        command: Optional[Callable[[], None]] = None,
        bg_color: str = COLOR_PRIMARY,
        hover_color: str = COLOR_PRIMARY_HOVER,
        fg_color: str = "#ffffff",
        border_color: Optional[str] = None,
        radius: int = 8,
        width: int = 140,
        height: int = 36,
        font: Optional[Tuple] = None,
        **kwargs,
    ) -> None:
        parent_bg = get_parent_bg(parent, default=COLOR_CARD_BG)
        kwargs.setdefault("takefocus", 1)
        super().__init__(parent, width=width, height=height, bg=parent_bg, highlightthickness=0, **kwargs)
        self.command = command
        self.text = text
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.fg_color = fg_color
        self.border_color = border_color or hover_color
        self.disabled_bg = "#e2e8f0"
        self.disabled_fg = "#94a3b8"
        self.disabled_border = "#cbd5e1"
        self.radius = radius
        self.font = font or ("DejaVu Sans", 9, "bold")
        self.state = "normal"
        self._is_hovered = False
        self._has_focus = False
        self._space_key_pressed = False
        self._return_key_pressed = False

        self.bind("<Configure>", self._redraw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<KeyPress-space>", self._on_space_press)
        self.bind("<KeyRelease-space>", self._on_space_release)
        self.bind("<KeyPress-Return>", self._on_return_press)
        self.bind("<KeyRelease-Return>", self._on_return_release)
        self.bind("<KeyPress-KP_Enter>", self._on_return_press)
        self.bind("<KeyRelease-KP_Enter>", self._on_return_release)

    def cget(self, key: str):
        if key == "state":
            return self.state
        if key == "text":
            return self.text
        return super().cget(key)

    def __getitem__(self, key: str):
        return self.cget(key)

    def configure(self, cnf=None, **kwargs) -> None:
        if cnf:
            kwargs.update(cnf)
        redraw_needed = False
        if "state" in kwargs:
            self.state = kwargs.pop("state")
            super().configure(takefocus=0 if self.state == "disabled" else 1)
            redraw_needed = True
        if "text" in kwargs:
            self.text = kwargs.pop("text")
            redraw_needed = True
        if "bg_color" in kwargs:
            self.bg_color = kwargs.pop("bg_color")
            redraw_needed = True
        if "hover_color" in kwargs:
            self.hover_color = kwargs.pop("hover_color")
            redraw_needed = True
        if "border_color" in kwargs:
            self.border_color = kwargs.pop("border_color")
            redraw_needed = True
        if "style" in kwargs:
            # 兼容外部 style 传入
            kwargs.pop("style")
        if kwargs:
            super().configure(**kwargs)
        if redraw_needed:
            self._redraw()

    def _on_enter(self, event) -> None:
        if self.state == "normal":
            self._is_hovered = True
            self._redraw()

    def _on_leave(self, event) -> None:
        self._is_hovered = False
        self._redraw()

    def _on_click(self, event) -> None:
        if self.state == "normal" and self.command:
            self.focus_set()
            self._invoke()

    def _on_focus_in(self, event=None) -> None:
        self._has_focus = True
        self._redraw()

    def _on_focus_out(self, event=None) -> None:
        self._has_focus = False
        self._space_key_pressed = False
        self._return_key_pressed = False
        self._redraw()

    def _on_space_press(self, event=None):
        if self.state == "normal":
            self._space_key_pressed = True
            self._redraw()
        return "break"

    def _on_space_release(self, event=None):
        was_pressed = self._space_key_pressed
        self._space_key_pressed = False
        self._redraw()
        if was_pressed:
            self._invoke()
        return "break"

    def _on_return_press(self, event=None):
        if self.state == "normal" and not self._return_key_pressed:
            self._return_key_pressed = True
            self._invoke()
        return "break"

    def _on_return_release(self, event=None):
        self._return_key_pressed = False
        return "break"

    def _invoke(self) -> None:
        if self.state == "normal" and self.command:
            self.command()

    def _redraw(self, event=None) -> None:
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10:
            return

        if self.state == "disabled":
            fill = self.disabled_bg
            fg = self.disabled_fg
            outline = self.disabled_border
            super().configure(cursor="")
        else:
            if self._is_hovered or self._space_key_pressed:
                fill = self.hover_color
                outline = self.hover_color if self.bg_color != COLOR_CARD_ALT else COLOR_PRIMARY_BORDER
                fg = "#ffffff" if self.bg_color != COLOR_CARD_ALT else COLOR_PRIMARY
            else:
                fill = self.bg_color
                outline = self.border_color
                fg = self.fg_color
            super().configure(cursor="hand2")

        draw_rounded_rect(
            self,
            2,
            2,
            w - 2,
            h - 2,
            radius=self.radius,
            fill=fill,
            outline=outline,
            width=1,
        )
        self.create_text(w / 2, h / 2, text=self.text, fill=fg, font=self.font)
        if self._has_focus:
            focus_color = COLOR_PRIMARY if self.bg_color == COLOR_CARD_ALT else "#ffffff"
            draw_rounded_rect(
                self,
                4,
                4,
                w - 4,
                h - 4,
                radius=max(2, self.radius - 2),
                fill="",
                outline=focus_color,
                width=2,
            )


class RoundedMetricTile(tk.Canvas):
    """现代柔和圆角性能度量卡片 (2x2 网格，等宽数字)。"""

    def __init__(
        self,
        parent: tk.Widget,
        title: str,
        textvar: tk.StringVar,
        fonts: FontRegistry,
        radius: int = 8,
        width: int = 180,
        height: int = 54,
        **kwargs,
    ) -> None:
        parent_bg = get_parent_bg(parent, default=COLOR_CARD_BG)
        super().__init__(parent, width=width, height=height, bg=parent_bg, highlightthickness=0, **kwargs)
        self.title = title
        self.textvar = textvar
        self.fonts = fonts
        self.radius = radius
        self.bg_color = COLOR_CARD_ALT
        self.border_color = COLOR_BORDER_LIGHT

        self.bind("<Configure>", self._redraw)
        self.textvar.trace_add("write", lambda *args: self._redraw())

    def _redraw(self, event=None) -> None:
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10:
            return
        draw_rounded_rect(
            self,
            2,
            2,
            w - 2,
            h - 2,
            radius=self.radius,
            fill=self.bg_color,
            outline=self.border_color,
            width=1,
        )
        self.create_text(12, 16, text=self.title, anchor="w", fill=COLOR_TEXT_SECONDARY, font=self.fonts.caption)
        self.create_text(12, 38, text=self.textvar.get(), anchor="w", fill=COLOR_PRIMARY, font=self.fonts.mono_metric)


class RoundedStatusBanner(tk.Canvas):
    """自适应现代柔和圆角状态横幅 (随运行与判据结果动态平滑变色)。"""

    def __init__(
        self,
        parent: tk.Widget,
        status_var: tk.StringVar,
        hint_var: tk.StringVar,
        fonts: FontRegistry,
        radius: int = 8,
        width: int = 300,
        height: int = 38,
        **kwargs,
    ) -> None:
        parent_bg = get_parent_bg(parent, default=COLOR_CARD_BG)
        super().__init__(parent, width=width, height=height, bg=parent_bg, highlightthickness=0, **kwargs)
        self.status_var = status_var
        self.hint_var = hint_var
        self.fonts = fonts
        self.radius = radius

        self.bg_color = COLOR_CARD_ALT
        self.border_color = COLOR_BORDER_LIGHT
        self.fg_color = COLOR_TEXT_PRIMARY
        self.hint_fg = COLOR_TEXT_SECONDARY

        self.bind("<Configure>", self._redraw)
        self.status_var.trace_add("write", lambda *args: self._redraw())
        self.hint_var.trace_add("write", lambda *args: self._redraw())

    def set_theme_mode(self, mode: str) -> None:
        """根据当前状态设置语义色彩模式 (idle / running / success / failed)。"""
        if mode == "failed":
            self.bg_color = COLOR_DANGER_BG
            self.border_color = COLOR_DANGER_BORDER
            self.fg_color = COLOR_DANGER_TEXT
            self.hint_fg = COLOR_DANGER_TEXT
        elif mode == "success":
            self.bg_color = COLOR_SUCCESS_BG
            self.border_color = COLOR_SUCCESS_BORDER
            self.fg_color = COLOR_SUCCESS_TEXT
            self.hint_fg = COLOR_SUCCESS_TEXT
        elif mode == "running":
            self.bg_color = COLOR_PRIMARY_BG
            self.border_color = COLOR_PRIMARY_BORDER
            self.fg_color = COLOR_PRIMARY
            self.hint_fg = COLOR_TEXT_SECONDARY
        else:
            self.bg_color = COLOR_CARD_ALT
            self.border_color = COLOR_BORDER_LIGHT
            self.fg_color = COLOR_TEXT_PRIMARY
            self.hint_fg = COLOR_TEXT_SECONDARY
        self._redraw()

    def _redraw(self, event=None) -> None:
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10:
            return
        draw_rounded_rect(
            self,
            2,
            2,
            w - 2,
            h - 2,
            radius=self.radius,
            fill=self.bg_color,
            outline=self.border_color,
            width=1,
        )
        self.create_text(12, h / 2, text=self.status_var.get(), anchor="w", fill=self.fg_color, font=self.fonts.body_bold)
        self.create_text(w - 12, h / 2, text=self.hint_var.get(), anchor="e", fill=self.hint_fg, font=self.fonts.caption)


class RoundedCard(tk.Canvas):
    """通用柔和圆角卡片底板容器。"""

    def __init__(
        self,
        parent: tk.Widget,
        title: str = "",
        radius: int = 10,
        bg_color: str = COLOR_CARD_BG,
        border_color: str = COLOR_BORDER_LIGHT,
        title_fg: str = COLOR_TEXT_PRIMARY,
        title_font: Optional[Tuple] = None,
        padding: int = 12,
        auto_height: bool = True,
        **kwargs,
    ) -> None:
        parent_bg = get_parent_bg(parent, default=COLOR_WINDOW_BG)
        super().__init__(parent, bg=parent_bg, highlightthickness=0, **kwargs)
        self.title = title
        self.radius = radius
        self.bg_color = bg_color
        self.border_color = border_color
        self.title_fg = title_fg
        self.title_font = title_font
        self.padding = padding
        self.auto_height = auto_height

        self.inner = tk.Frame(self, bg=self.bg_color)
        self.title_offset = (28 + padding // 2) if title else padding
        self.window_id = self.create_window(self.padding, self.title_offset, window=self.inner, anchor="nw")

        if self.auto_height:
            self.inner.bind("<Configure>", self._on_inner_configure)
        self.bind("<Configure>", self._redraw)

    def _on_inner_configure(self, event=None) -> None:
        if self.auto_height:
            req_h = self.inner.winfo_reqheight() + self.title_offset + self.padding
            if abs(self.winfo_height() - req_h) > 1:
                self.configure(height=req_h)
                self._redraw()

    def _redraw(self, event=None) -> None:
        self.delete("bg_rect", "title_text")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10 or h < 10:
            return
        draw_rounded_rect(
            self,
            2,
            2,
            w - 2,
            h - 2,
            radius=self.radius,
            fill=self.bg_color,
            outline=self.border_color,
            width=1,
            tags="bg_rect",
        )
        if self.title:
            font = self.title_font or ("DejaVu Sans", 10, "bold")
            self.create_text(
                self.padding + 2,
                self.title_offset // 2 + 1,
                text=self.title,
                anchor="w",
                font=font,
                fill=self.title_fg,
                tags="title_text",
            )
        inner_w = max(10, w - (self.padding * 2))
        if self.auto_height:
            self.itemconfig(self.window_id, width=inner_w)
        else:
            inner_h = max(10, h - self.title_offset - self.padding)
            self.itemconfig(self.window_id, width=inner_w, height=inner_h)


# =============================================================================
# 5. TTK 样式安装器 (Clam 现代扁平化与柔和主题)
# =============================================================================

def apply_modern_theme(root: tk.Tk) -> FontRegistry:
    """全局应用现代扁平工业风格的主题与控件样式。"""
    enable_windows_dpi_awareness()
    fonts = FontRegistry(root)

    root.configure(background=COLOR_WINDOW_BG)

    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    # 1. 基础布局与卡片面板
    style.configure("TFrame", background=COLOR_CARD_BG)
    style.configure("Window.TFrame", background=COLOR_WINDOW_BG)
    style.configure("Card.TFrame", background=COLOR_CARD_BG)
    style.configure("Header.TFrame", background=COLOR_HEADER_BG)
    style.configure("Pill.TFrame", background=COLOR_CARD_ALT)

    # 2. 卡片 LabelFrame (更轻盈的浅色边框与内边距)
    style.configure(
        "TLabelframe",
        background=COLOR_CARD_BG,
        bordercolor=COLOR_BORDER_LIGHT,
        lightcolor=COLOR_BORDER_LIGHT,
        darkcolor=COLOR_BORDER_LIGHT,
        borderwidth=1,
        relief="solid",
    )
    style.configure(
        "TLabelframe.Label",
        background=COLOR_CARD_BG,
        foreground=COLOR_TEXT_PRIMARY,
        font=fonts.card_header,
    )

    # 3. 基础标签样式
    style.configure(
        "TLabel",
        background=COLOR_CARD_BG,
        foreground=COLOR_TEXT_PRIMARY,
        font=fonts.body,
    )
    style.configure("WindowBg.TLabel", background=COLOR_WINDOW_BG, foreground=COLOR_TEXT_PRIMARY, font=fonts.body)
    style.configure("HeaderTitle.TLabel", background=COLOR_HEADER_BG, foreground=COLOR_TEXT_PRIMARY, font=fonts.app_title)
    style.configure("HeaderSub.TLabel", background=COLOR_HEADER_BG, foreground=COLOR_TEXT_SECONDARY, font=fonts.caption)
    style.configure("Muted.TLabel", background=COLOR_CARD_BG, foreground=COLOR_TEXT_SECONDARY, font=fonts.caption)

    # 语义标签
    style.configure("Success.TLabel", background=COLOR_CARD_BG, foreground=COLOR_SUCCESS_TEXT, font=fonts.body_bold)
    style.configure("Failure.TLabel", background=COLOR_CARD_BG, foreground=COLOR_DANGER_TEXT, font=fonts.body_bold)
    style.configure("Badge.TLabel", background=COLOR_PRIMARY_BG, foreground=COLOR_PRIMARY, font=fonts.body_bold)
    style.configure("Timer.TLabel", background=COLOR_CARD_BG, foreground=COLOR_PRIMARY, font=fonts.mono_timer)
    style.configure("MetricVal.TLabel", background=COLOR_CARD_ALT, foreground=COLOR_TEXT_PRIMARY, font=fonts.mono_metric)
    style.configure("MetricTitle.TLabel", background=COLOR_CARD_ALT, foreground=COLOR_TEXT_SECONDARY, font=fonts.caption)

    # 4. 次要按钮 (更柔和的背景与边框)
    style.configure(
        "TButton",
        background=COLOR_CARD_ALT,
        foreground=COLOR_TEXT_PRIMARY,
        bordercolor=COLOR_BORDER_LIGHT,
        lightcolor=COLOR_BORDER_LIGHT,
        darkcolor=COLOR_BORDER_LIGHT,
        font=fonts.body,
        padding=(8, 4),
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("pressed", COLOR_BORDER_LIGHT), ("active", COLOR_PRIMARY_BG), ("disabled", COLOR_WINDOW_BG)],
        foreground=[("disabled", COLOR_TEXT_MUTED), ("active", COLOR_PRIMARY)],
        bordercolor=[("active", COLOR_PRIMARY_BORDER)],
    )

    # 5. 输入框与选择框
    style.configure(
        "TEntry",
        fieldbackground=COLOR_CARD_BG,
        foreground=COLOR_TEXT_PRIMARY,
        bordercolor=COLOR_BORDER,
        lightcolor=COLOR_BORDER,
        darkcolor=COLOR_BORDER,
        padding=(5, 4),
        insertcolor=COLOR_TEXT_PRIMARY,
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", COLOR_BORDER_FOCUS)],
        lightcolor=[("focus", COLOR_BORDER_FOCUS)],
    )

    style.configure(
        "TCombobox",
        fieldbackground=COLOR_CARD_BG,
        background=COLOR_CARD_ALT,
        foreground=COLOR_TEXT_PRIMARY,
        bordercolor=COLOR_BORDER,
        padding=(4, 4),
    )
    style.map(
        "TCombobox",
        bordercolor=[("focus", COLOR_BORDER_FOCUS)],
        fieldbackground=[("readonly", COLOR_CARD_BG)],
    )

    style.configure(
        "TSpinbox",
        fieldbackground=COLOR_CARD_BG,
        background=COLOR_CARD_ALT,
        foreground=COLOR_TEXT_PRIMARY,
        bordercolor=COLOR_BORDER,
        padding=(4, 4),
    )

    # 6. 复选框
    style.configure(
        "TCheckbutton",
        background=COLOR_CARD_BG,
        foreground=COLOR_TEXT_PRIMARY,
        font=fonts.body,
    )

    # 7. 进度条 (更圆润的厚度与槽色)
    style.configure(
        "Horizontal.TProgressbar",
        background=COLOR_PRIMARY,
        troughcolor=COLOR_BORDER_LIGHT,
        bordercolor=COLOR_BORDER_LIGHT,
        lightcolor=COLOR_PRIMARY,
        darkcolor=COLOR_PRIMARY,
        thickness=10,
    )

    # 8. PanedWindow 分割条
    style.configure(
        "TPanedwindow",
        background=COLOR_WINDOW_BG,
    )

    return fonts
