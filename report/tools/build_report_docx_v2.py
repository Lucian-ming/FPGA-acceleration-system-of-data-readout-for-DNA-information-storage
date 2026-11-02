#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""以官方 DOCX 模板为底稿，将定稿 Markdown 组装为竞赛报告。"""
from __future__ import annotations

import argparse
import copy
import re
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor, Twips
from lxml import etree
from PIL import Image

TEXT_WIDTH_CM = 14.649
TEXT_WIDTH_TWIPS = 8306
BODY_PT = 10.5
BODY_LINE = 1.15
PARA_AFTER_PT = 3.0
TABLE_PT = 8.5
REF_PT = 9.0
FIG_WIDTH_CM = 14.0
FIG_MAX_H_CM = 7.5
SNAP_GRID = False
FIG_OVERRIDES: Dict[str, float] = {}
SUBTITLE = "全国大学生嵌入式芯片与系统设计竞赛 · 2026 · AMD 赛道 · 自主选题"
CAPTION_PT = 9.0
BODY_EAST_ASIA = "宋体"
HEADING_EAST_ASIA = "黑体"
BODY_WESTERN = "Times New Roman"
MONO_FONT = "Consolas"
MONO_EAST_ASIA = BODY_EAST_ASIA

IMAGE_RE = re.compile(r"^\s*!\[([^]]*)\]\(([^)]+)\)\s*$")
IMAGE_CAPTION_RE = re.compile(r"^图\s+([A-Z]?\d+)　.+$")
TABLE_CAPTION_RE = re.compile(r"^表\s+([A-Z]?\d+)　.+$")
HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
LIST_RE = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
CODE_FENCE_RE = re.compile(r"^\s*```")
TABLE_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")
INLINE_RE = re.compile(
    r"(\*\*.+?\*\*|`[^`]+`|\$[^$]+\$|\[[^\]]+\]\([^)]+\)|(?<!\*)\*[^*]+\*(?!\*))"
)
INLINE_MATH_RE = re.compile(r"\$([^$]+)\$")
DISPLAY_MATH_RE = re.compile(r"^\s*\$\$(.+?)\$\$\s*$")


@dataclass
class FormulaToken:
    tex: str
    display: bool


@dataclass
class FormulaPlan:
    tokens: List[FormulaToken]
    omml: Optional[List[etree._Element]]
    index: int = 0

    def take(self, tex: str, display: bool) -> Optional[etree._Element]:
        if self.index >= len(self.tokens):
            raise ValueError(f"公式扫描与正文解析不一致：多出 {tex!r}")
        token = self.tokens[self.index]
        if token.tex.strip() != tex.strip() or token.display != display:
            raise ValueError(
                f"公式顺序不一致：预期 {token.tex!r}（display={token.display}），"
                f"实际 {tex!r}（display={display}）"
            )
        index = self.index
        self.index += 1
        return copy.deepcopy(self.omml[index]) if self.omml is not None else None


def collect_formulas(lines: Sequence[str]) -> List[FormulaToken]:
    formulas: List[FormulaToken] = []
    in_code = False
    for line in lines:
        if CODE_FENCE_RE.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        display = DISPLAY_MATH_RE.match(line)
        if display:
            formulas.append(FormulaToken(display.group(1).strip(), True))
        else:
            formulas.extend(FormulaToken(match.group(1), False) for match in INLINE_MATH_RE.finditer(line))
    return formulas


def prepare_omml(formulas: Sequence[FormulaToken], work_dir: Path) -> Tuple[Optional[List[etree._Element]], Optional[str]]:
    if not formulas:
        return [], None
    try:
        with tempfile.TemporaryDirectory(prefix="formula-", dir=work_dir) as temp_name:
            temp_dir = Path(temp_name)
            markdown_path = temp_dir / "formulas.md"
            docx_path = temp_dir / "formulas.docx"
            formula_lines: List[str] = []
            for token in formulas:
                if token.display:
                    formula_lines.extend(("$$", token.tex, "$$", ""))
                else:
                    formula_lines.extend((f"${token.tex}$", ""))
            markdown_path.write_text("\n".join(formula_lines), encoding="utf-8")
            subprocess.run(
                ["pandoc", "--from=markdown+tex_math_dollars", "--to=docx", "--output", str(docx_path), str(markdown_path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            with zipfile.ZipFile(docx_path) as archive:
                root = etree.fromstring(archive.read("word/document.xml"))
            omml = root.xpath("//*[local-name()='oMath']")
            if len(omml) != len(formulas):
                raise ValueError(f"pandoc 产出 {len(omml)} 个 m:oMath，输入有 {len(formulas)} 个公式")
            return omml, None
    except Exception as error:
        return None, str(error)


LATEX_SYMBOLS = {
    r"\sum": "∑", r"\prod": "∏", r"\oplus": "⊕", r"\arg\max": "arg max",
    r"\argmax": "arg max", r"\min": "min", r"\max": "max", r"\mathrm": "",
    r"\operatorname": "", r"\mathop": "", r"\left": "", r"\right": "",
    r"\cdot": "·", r"\times": "×", r"\in": "∈", r"\setminus": "\\", r"\geq": "≥",
    r"\leq": "≤", r"\neq": "≠", r"\to": "→", r"\infty": "∞", r"\hat": "",
}


def latex_plain(tex: str) -> str:
    value = tex.replace(r"\begin{cases}", "").replace(r"\end{cases}", "")
    value = value.replace(r"\\", " ; ").replace("&", " ")
    for command, replacement in LATEX_SYMBOLS.items():
        value = value.replace(command, replacement)
    value = re.sub(r"\\text\{([^{}]*)\}", r"\1", value)
    value = value.replace(r"\{", "{").replace(r"\}", "}").replace("{", "").replace("}", "")
    value = value.replace(r"\,", " ").replace(r"\;", " ").replace(r"\!", "")
    value = re.sub(r"\\([A-Za-z]+)", r"\1", value)
    return value.strip()


def add_fallback_formula(paragraph, tex: str) -> None:
    """在 Pandoc 不可用时，把常见 TeX 符号转换为文本并保留上下标 run。"""
    pos = 0
    for match in re.finditer(r"([_^])(?:\{([^{}]*)\}|([A-Za-z0-9+-]))", tex):
        if match.start() > pos:
            run = paragraph.add_run(latex_plain(tex[pos:match.start()]))
            set_run_font(run, size=BODY_PT, east_asia=BODY_EAST_ASIA)
        content = latex_plain(match.group(2) if match.group(2) is not None else match.group(3))
        run = paragraph.add_run(content)
        set_run_font(run, size=9, east_asia=BODY_EAST_ASIA)
        run.font.subscript = match.group(1) == "_"
        run.font.superscript = match.group(1) == "^"
        pos = match.end()
    if pos < len(tex):
        run = paragraph.add_run(latex_plain(tex[pos:]))
        set_run_font(run, size=BODY_PT, east_asia=BODY_EAST_ASIA)


def append_math(paragraph, tex: str, plan: FormulaPlan, *, display: bool = False):
    element = plan.take(tex, display)
    if element is None:
        add_fallback_formula(paragraph, tex)
    else:
        paragraph._p.append(element)


def set_rfonts(rpr, west: str, east_asia: str) -> None:
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    fonts.set(qn("w:ascii"), west)
    fonts.set(qn("w:hAnsi"), west)
    fonts.set(qn("w:eastAsia"), east_asia)
    fonts.set(qn("w:cs"), west)


def set_run_font(
    run,
    *,
    size: float = 12,
    east_asia: str = BODY_EAST_ASIA,
    west: str = BODY_WESTERN,
    bold: Optional[bool] = None,
    italic: Optional[bool] = None,
    color: Optional[RGBColor] = None,
) -> None:
    run.font.name = west
    run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color is not None:
        run.font.color.rgb = color
    set_rfonts(run._element.get_or_add_rPr(), west, east_asia)


def set_style_font(style, *, size: float, east_asia: str, west: str, bold: bool = False) -> None:
    style.font.name = west
    style.font.size = Pt(size)
    style.font.bold = bold
    set_rfonts(style._element.get_or_add_rPr(), west, east_asia)


def ensure_paragraph_style(document, name: str):
    try:
        return document.styles[name]
    except KeyError:
        return document.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)


def set_outline_level(style, level: int) -> None:
    p_pr = style._element.get_or_add_pPr()
    outline = p_pr.find(qn("w:outlineLvl"))
    if outline is None:
        outline = OxmlElement("w:outlineLvl")
        p_pr.append(outline)
    outline.set(qn("w:val"), str(level))


def set_cell_margins(cell, top: int = 65, start: int = 55, bottom: int = 65, end: int = 55) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.find(qn("w:tcMar"))
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for edge, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_cell_borders(cell, **borders: Dict[str, str]) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = tc_pr.find(qn("w:tcBorders"))
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV", "start", "end"):
        if edge not in borders:
            continue
        tag = qn(f"w:{edge}")
        element = tc_borders.find(tag)
        if element is None:
            element = OxmlElement(f"w:{edge}")
            tc_borders.append(element)
        for key, value in borders[edge].items():
            element.set(qn(f"w:{key}"), str(value))


def set_table_borders(table) -> None:
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for child in list(borders):
        borders.remove(child)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        item = OxmlElement(f"w:{edge}")
        item.set(qn("w:val"), "single")
        item.set(qn("w:sz"), "4")
        item.set(qn("w:space"), "0")
        item.set(qn("w:color"), "B7C9DD")
        borders.append(item)


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = tc_pr.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        tc_pr.append(shading)
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), fill)


def add_page_field(paragraph) -> None:
    def field_run(element_name: str, value: Optional[str] = None, **attrs: str):
        run = paragraph.add_run()
        set_run_font(run, size=9, east_asia=BODY_EAST_ASIA, west=BODY_WESTERN, color=RGBColor(90, 90, 90))
        element = OxmlElement(element_name)
        for name, attr_value in attrs.items():
            element.set(qn(f"w:{name}"), attr_value)
        if value is not None:
            element.text = value
        run._r.append(element)
        return run

    lead = paragraph.add_run("第 ")
    set_run_font(lead, size=9, east_asia=BODY_EAST_ASIA, west=BODY_WESTERN, color=RGBColor(90, 90, 90))
    field_run("w:fldChar", fldCharType="begin")
    instruction_run = field_run("w:instrText", " PAGE ")
    instruction_run._r[-1].set(qn("xml:space"), "preserve")
    field_run("w:fldChar", fldCharType="separate")
    result = paragraph.add_run("1")
    set_run_font(result, size=9, east_asia=BODY_EAST_ASIA, west=BODY_WESTERN, color=RGBColor(90, 90, 90))
    field_run("w:fldChar", fldCharType="end")
    tail = paragraph.add_run(" 页")
    set_run_font(tail, size=9, east_asia=BODY_EAST_ASIA, west=BODY_WESTERN, color=RGBColor(90, 90, 90))


def add_inline(
    paragraph,
    text: str,
    *,
    size: float = 12,
    east_asia: str = BODY_EAST_ASIA,
    color=None,
    formula_plan: Optional[FormulaPlan] = None,
) -> None:
    pos = 0
    for match in INLINE_RE.finditer(text):
        if match.start() > pos:
            run = paragraph.add_run(text[pos:match.start()])
            set_run_font(run, size=size, east_asia=east_asia, color=color)
        token = match.group(0)
        if token.startswith("$"):
            if formula_plan is None:
                raise ValueError("行内公式缺少公式转换上下文。")
            append_math(paragraph, token[1:-1], formula_plan)
        elif token.startswith("**"):
            run = paragraph.add_run(token[2:-2])
            set_run_font(run, size=size, east_asia=east_asia, bold=True, color=color)
        elif token.startswith("`"):
            run = paragraph.add_run(token[1:-1])
            set_run_font(run, size=max(size - 1, 8), east_asia=MONO_FONT, west=MONO_FONT, color=color)
        elif token.startswith("["):
            label = re.match(r"\[([^\]]+)\]\([^)]+\)", token).group(1)
            run = paragraph.add_run(label)
            set_run_font(run, size=size, east_asia=east_asia, color=color)
        else:
            run = paragraph.add_run(token[1:-1])
            set_run_font(run, size=size, east_asia=east_asia, italic=True, color=color)
        pos = match.end()
    if pos < len(text):
        run = paragraph.add_run(text[pos:])
        set_run_font(run, size=size, east_asia=east_asia, color=color)


def apply_body_paragraph(paragraph, *, first_line: bool = True) -> None:
    fmt = paragraph.paragraph_format
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    fmt.line_spacing = BODY_LINE
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(PARA_AFTER_PT)
    fmt.first_line_indent = Pt(BODY_PT * 2) if first_line else Pt(0)
    fmt.widow_control = True


def apply_caption(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.space_before = Pt(2)
    paragraph.paragraph_format.space_after = Pt(6)
    paragraph.paragraph_format.keep_together = True


def add_caption(document, text: str, *, keep_with_next: bool = False):
    paragraph = document.add_paragraph(style="Caption")
    apply_caption(paragraph)
    paragraph.paragraph_format.keep_with_next = keep_with_next
    add_inline(paragraph, text.strip(), size=CAPTION_PT)
    return paragraph


def add_display_equation(document, tex: str, formula_plan: FormulaPlan, number: int) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.left_indent = Pt(0)
    paragraph.paragraph_format.right_indent = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(6)
    paragraph.paragraph_format.tab_stops.add_tab_stop(Twips(TEXT_WIDTH_TWIPS // 2), WD_TAB_ALIGNMENT.CENTER)
    paragraph.paragraph_format.tab_stops.add_tab_stop(Twips(TEXT_WIDTH_TWIPS), WD_TAB_ALIGNMENT.RIGHT)
    lead = paragraph.add_run("\t")
    set_run_font(lead, size=BODY_PT)
    append_math(paragraph, tex, formula_plan, display=True)
    tail = paragraph.add_run("\t")
    set_run_font(tail, size=BODY_PT)
    number_run = paragraph.add_run(f"({number})")
    set_run_font(number_run, size=BODY_PT)


def add_reference_paragraph(document, text: str, formula_plan: FormulaPlan) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.left_indent = Pt(18)
    paragraph.paragraph_format.first_line_indent = Pt(-18)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.paragraph_format.widow_control = True
    add_inline(paragraph, text, size=REF_PT, formula_plan=formula_plan)


def parse_table_row(line: str) -> List[str]:
    value = line.strip()
    if value.startswith("|"):
        value = value[1:]
    if value.endswith("|"):
        value = value[:-1]
    return [cell.strip() for cell in value.split("|")]


def parse_table_alignments(line: str) -> List[str]:
    alignments = []
    for cell in parse_table_row(line):
        value = cell.replace(" ", "")
        if value.startswith(":") and value.endswith(":"):
            alignments.append("center")
        elif value.endswith(":"):
            alignments.append("right")
        else:
            alignments.append("left")
    return alignments


def is_table_separator(line: str) -> bool:
    cells = parse_table_row(line)
    return bool(cells) and all(TABLE_SEPARATOR_CELL_RE.match(cell.replace(" ", "")) for cell in cells)


def estimate_text_cm(text: str, size_pt: float = 10.5) -> float:
    """粗估一段单行文本的排版宽度（cm）。

    只用于给列宽兜底，不追求精确：拉丁大写取 0.75 em、小写 0.5 em、数字 0.5 em、
    中日韩全角 1 em。按 em 换算成 cm（1 pt = 2.54/72 cm）。
    """
    em_cm = size_pt * 2.54 / 72.0
    width = 0.0
    for char in text:
        if ord(char) > 0x2E7F:
            width += 1.0 * em_cm
        elif char.isupper():
            width += 0.75 * em_cm
        elif char.isdigit():
            width += 0.5 * em_cm
        elif char == " ":
            width += 0.28 * em_cm
        else:
            width += 0.5 * em_cm
    return width


def compute_column_widths(
    rows: Sequence[Sequence[str]],
    total_cm: float,
    header_rows: int = 1,
    font_pt: float = TABLE_PT,
) -> List[float]:
    """按各列最长内容分配列宽，而不是等分。

    等分会让「模块名」这类长标识符列被挤到 2.9 cm 以下，Word 只能在词中间断开
    （`dna_accelerator_c` / `ore`），表就废了。按内容长度加权可以把宽度让给长列；
    权重上下限（6 ~ 32 字符）防止某一列的超长内容吃掉整张表。

    另外补两条下限，都是实测踩出来的：
    * 每列不小于 1.15 cm，否则连表头都放不下；
    * 表头里最长的不可断词（`RAMB36`）必须能单行放下——按内容加权后它只有 1.69 cm，
      Word 仍会把它断成 `RAMB3` / `6`。上限按 10.5 pt 字宽估算再加单元格边距。
    """
    column_count = max(len(row) for row in rows)
    weights = []
    floors = []
    for column_index in range(column_count):
        longest = max((len(row[column_index]) for row in rows if column_index < len(row)), default=6)
        weights.append(min(32.0, max(6.0, float(longest))))
        floor_cm = min(1.15, total_cm / column_count)
        for row in rows[:header_rows]:
            if column_index >= len(row):
                continue
            for word in row[column_index].split():
                # 单元格左右边距 55+55 twips ≈ 0.19 cm，再留 0.12 cm 余量
                need = estimate_text_cm(word, font_pt) * 1.08 + 0.31
                floor_cm = max(floor_cm, need)
        floors.append(floor_cm)

    raw = [total_cm * weight / sum(weights) for weight in weights]

    def raise_to_floors(values: List[float]) -> List[float]:
        # 从余量最富的列里按比例抽，抽不动时（所有列都已在下限）就停手
        for _ in range(column_count * 2):
            deficit = 0.0
            for index, floor_cm in enumerate(floors):
                if values[index] < floor_cm - 1e-9:
                    deficit += floor_cm - values[index]
                    values[index] = floor_cm
            if deficit <= 1e-9:
                return values
            donors = [i for i, value in enumerate(values) if value > floors[i] + 1e-9]
            if not donors:
                return values
            spare = sum(values[i] - floors[i] for i in donors)
            take = min(deficit, spare)
            for index in donors:
                values[index] -= take * (values[index] - floors[index]) / spare
        return values

    raw = raise_to_floors(raw)
    scale = total_cm / sum(raw)
    return [width * scale for width in raw]


def add_markdown_table(
    document,
    rows: Sequence[Sequence[str]],
    alignments: Sequence[str],
    formula_plan: FormulaPlan,
) -> None:
    if not rows:
        return
    column_count = max(len(row) for row in rows)
    normalized = [list(row) + [""] * (column_count - len(row)) for row in rows]
    table = document.add_table(rows=len(normalized), cols=column_count)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_table_borders(table)
    # 只设 column.width / cell.width 还不够：Word 在 autofit 下会忽略它们重排。
    # 必须把表布局钉成 fixed 并给出整表宽度，列宽才会被遵守。
    tbl_pr = table._tbl.tblPr
    layout = tbl_pr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tbl_pr.append(layout)
    layout.set(qn("w:type"), "fixed")
    tbl_width = tbl_pr.find(qn("w:tblW"))
    if tbl_width is not None:
        tbl_width.set(qn("w:w"), str(TEXT_WIDTH_TWIPS))
        tbl_width.set(qn("w:type"), "dxa")
    col_widths = compute_column_widths(normalized, TEXT_WIDTH_CM, font_pt=TABLE_PT)
    for column_index, width in enumerate(col_widths):
        table.columns[column_index].width = Cm(width)
    for row_index, values in enumerate(normalized):
        row = table.rows[row_index]
        tr_pr = row._tr.get_or_add_trPr()
        cant_split = OxmlElement("w:cantSplit")
        tr_pr.append(cant_split)
        if row_index == 0:
            tbl_header = OxmlElement("w:tblHeader")
            tbl_header.set(qn("w:val"), "true")
            tr_pr.append(tbl_header)
        for column_index, value in enumerate(values):
            cell = row.cells[column_index]
            cell.width = Cm(col_widths[column_index])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_margins(cell)
            border = {"val": "single", "sz": "4", "color": "B7C9DD"}
            set_cell_borders(cell, top=border, left=border, bottom=border, right=border)
            if row_index == 0:
                set_cell_shading(cell, "EAF1F8")
            paragraph = cell.paragraphs[0]
            if row_index == 0:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                paragraph.alignment = {
                    "left": WD_ALIGN_PARAGRAPH.LEFT,
                    "center": WD_ALIGN_PARAGRAPH.CENTER,
                    "right": WD_ALIGN_PARAGRAPH.RIGHT,
                }.get(alignments[column_index] if column_index < len(alignments) else "left", WD_ALIGN_PARAGRAPH.LEFT)
            paragraph.paragraph_format.first_line_indent = Pt(0)
            paragraph.paragraph_format.left_indent = Pt(0)
            paragraph.paragraph_format.right_indent = Pt(0)
            paragraph.paragraph_format.space_before = Pt(0)
            paragraph.paragraph_format.space_after = Pt(0)
            paragraph.paragraph_format.line_spacing = 1.0
            paragraph.paragraph_format.keep_together = True
            add_inline(paragraph, value, size=TABLE_PT, formula_plan=formula_plan)
            if row_index == 0:
                for run in paragraph.runs:
                    run.bold = True
                    set_rfonts(run._element.get_or_add_rPr(), BODY_WESTERN, BODY_EAST_ASIA)
    spacer = document.add_paragraph()
    spacer.paragraph_format.space_after = Pt(2)
    spacer.paragraph_format.line_spacing = 1.0


def add_key_value_block(document, rows: Sequence[Sequence[str]]) -> None:
    """将模板中无题注的小型 Markdown 表格作为正文键值段落保留。"""
    if len(rows) < 2:
        return
    headers = list(rows[0])
    for row in rows[1:]:
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.left_indent = Pt(24)
        paragraph.paragraph_format.first_line_indent = Pt(-24)
        paragraph.paragraph_format.line_spacing = BODY_LINE
        paragraph.paragraph_format.space_after = Pt(3)
        paragraph.paragraph_format.widow_control = True
        if headers[:2] == ["关键变量", "含义"] and len(row) >= 2:
            add_inline(paragraph, row[0], size=BODY_PT)
            separator = paragraph.add_run("：")
            set_run_font(separator, size=BODY_PT)
            add_inline(paragraph, row[1], size=BODY_PT)
        elif headers[:2] == ["指标", "结果"] and len(row) >= 2:
            label = paragraph.add_run("指标：")
            set_run_font(label, size=BODY_PT, bold=True)
            add_inline(paragraph, row[0], size=BODY_PT)
            separator = paragraph.add_run("　结果：")
            set_run_font(separator, size=BODY_PT, bold=True)
            add_inline(paragraph, row[1], size=BODY_PT)
        else:
            for index, value in enumerate(row):
                if index:
                    separator = paragraph.add_run("；")
                    set_run_font(separator, size=BODY_PT)
                if index < len(headers):
                    label = paragraph.add_run(headers[index] + "：")
                    set_run_font(label, size=BODY_PT, bold=True)
                add_inline(paragraph, value, size=BODY_PT)


def add_code_block(document, lines: Sequence[str]) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.left_indent = Pt(7)
    paragraph.paragraph_format.right_indent = Pt(7)
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(3)
    paragraph.paragraph_format.space_after = Pt(7)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.keep_together = True
    p_pr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), "F1F1F1")
    p_pr.append(shd)
    run = paragraph.add_run("\n".join(lines))
    set_run_font(run, size=8.5, east_asia=MONO_EAST_ASIA, west=MONO_FONT)


def image_width_cm(path: Path, pixel_width: int, pixel_height: int) -> float:
    requested = min(FIG_OVERRIDES.get(path.name, FIG_WIDTH_CM), TEXT_WIDTH_CM)
    if requested <= 0:
        raise ValueError(f"图片宽度必须为正数：{path.name}={requested}")
    if requested * pixel_height / pixel_width > FIG_MAX_H_CM:
        requested = FIG_MAX_H_CM * pixel_width / pixel_height
    return requested


def add_image(document, image_path: Path, alt: str) -> None:
    if not image_path.is_file() or image_path.stat().st_size <= 0:
        raise FileNotFoundError(f"图片不存在或为空：{image_path}")
    with Image.open(image_path) as source_image:
        width, height = source_image.size
        source_image.verify()
    if width <= 0 or height <= 0:
        raise ValueError(f"图片尺寸无效：{image_path}（{width}×{height}）")
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.space_before = Pt(2)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.keep_with_next = True
    width_cm = image_width_cm(image_path, width, height)
    shape = paragraph.add_run().add_picture(str(image_path), width=Cm(width_cm))
    shape._inline.docPr.set("descr", alt)


def add_heading(document, level: int, text: str, formula_plan: FormulaPlan) -> None:
    paragraph = document.add_paragraph(style=f"Heading {level}")
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.space_before = Pt({1: 12, 2: 9, 3: 6}[level])
    paragraph.paragraph_format.space_after = Pt({1: 6, 2: 4, 3: 3}[level])
    paragraph.paragraph_format.keep_with_next = True
    add_inline(paragraph, text.strip(), size={1: 16, 2: 13, 3: 11.5}[level], east_asia=HEADING_EAST_ASIA, formula_plan=formula_plan)
    for run in paragraph.runs:
        run.bold = True
        set_rfonts(run._element.get_or_add_rPr(), BODY_WESTERN, HEADING_EAST_ASIA)


def clear_template_body(document) -> None:
    body = document._element.body
    section_properties = body.findall(qn("w:sectPr"))
    if not section_properties:
        raise ValueError("模板正文缺少末尾 w:sectPr，无法保留页面与页眉页脚设置。")
    keep = section_properties[-1]
    for child in list(body):
        if child is not keep:
            body.remove(child)


def strip_page_break_markers(document) -> None:
    roots = [document._element, document.styles.element]
    for section in document.sections:
        roots.extend((section.header._element, section.footer._element))
    for root in roots:
        for node in list(root.xpath(".//w:br[@w:type='page']")) + list(root.xpath(".//w:pageBreakBefore")):
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)


def disable_grid_snap(document) -> None:
    """模板节属性带 15.6 pt 行网格；段落对齐网格时，多倍行距按网格放大，小字号表格与题注也被撑到整格。
    在段落默认格式里关闭对齐网格，行距改按字体行高计算；页面设置本身不动。"""
    styles = document.styles.element
    defaults = styles.find(qn("w:docDefaults"))
    if defaults is None:
        defaults = OxmlElement("w:docDefaults")
        styles.insert(0, defaults)
    ppr_default = defaults.find(qn("w:pPrDefault"))
    if ppr_default is None:
        ppr_default = OxmlElement("w:pPrDefault")
        defaults.append(ppr_default)
    ppr = ppr_default.find(qn("w:pPr"))
    if ppr is None:
        ppr = OxmlElement("w:pPr")
        ppr_default.append(ppr)
    snap = ppr.find(qn("w:snapToGrid"))
    if snap is None:
        snap = OxmlElement("w:snapToGrid")
        ppr.insert(0, snap)
    snap.set(qn("w:val"), "0")


def setup_document(document) -> None:
    normal = document.styles["Normal"]
    set_style_font(normal, size=BODY_PT, east_asia=BODY_EAST_ASIA, west=BODY_WESTERN)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    normal.paragraph_format.line_spacing = BODY_LINE
    normal.paragraph_format.space_after = Pt(PARA_AFTER_PT)
    normal.paragraph_format.widow_control = True

    heading_sizes = {1: 16, 2: 13, 3: 11.5}
    heading_before = {1: 12, 2: 9, 3: 6}
    heading_after = {1: 6, 2: 4, 3: 3}
    for level in (1, 2, 3):
        style = ensure_paragraph_style(document, f"Heading {level}")
        set_style_font(style, size=heading_sizes[level], east_asia=HEADING_EAST_ASIA, west=BODY_WESTERN, bold=True)
        style.paragraph_format.line_spacing = 1.0
        style.paragraph_format.space_before = Pt(heading_before[level])
        style.paragraph_format.space_after = Pt(heading_after[level])
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.keep_together = True
        set_outline_level(style, level - 1)

    caption = ensure_paragraph_style(document, "Caption")
    set_style_font(caption, size=CAPTION_PT, east_asia=BODY_EAST_ASIA, west=BODY_WESTERN)
    caption.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    caption.paragraph_format.line_spacing = 1.0
    caption.paragraph_format.space_before = Pt(2)
    caption.paragraph_format.space_after = Pt(6)
    caption.paragraph_format.first_line_indent = Pt(0)

    if not SNAP_GRID:
        disable_grid_snap(document)

    for node in list(document.settings._element.xpath(".//w:updateFields")):
        node.getparent().remove(node)
    has_page_field = any(
        any("PAGE" in (node.text or "").upper() for node in section.footer._element.xpath(".//w:instrText"))
        for section in document.sections
    )
    if not has_page_field:
        footer = document.sections[-1].footer
        paragraph = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_page_field(paragraph)
    strip_page_break_markers(document)


def add_cover(document, title: str, subtitle_text: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.first_line_indent = Pt(0)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(2)
    paragraph.paragraph_format.line_spacing = 1.0
    run = paragraph.add_run(title)
    set_run_font(run, size=22, east_asia=HEADING_EAST_ASIA, west=BODY_WESTERN, bold=True, color=RGBColor(0, 0, 0))

    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.first_line_indent = Pt(0)
    subtitle.paragraph_format.space_after = Pt(0)
    subtitle.paragraph_format.line_spacing = 1.0
    run = subtitle.add_run(subtitle_text)
    set_run_font(run, size=10, east_asia=BODY_EAST_ASIA, west=BODY_WESTERN, color=RGBColor(0, 0, 0))


def next_nonblank(lines: Sequence[str], index: int) -> int:
    while index < len(lines) and not lines[index].strip():
        index += 1
    return index


def readback_math_count(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    return len(root.xpath("//*[local-name()='oMath']"))


def build(
    source: Path,
    figures_root: Path,
    output: Path,
    *,
    template_path: Path,
    subtitle: str = SUBTITLE,
    body_pt: float = 10.5,
    line: float = 1.15,
    para_after: float = 3.0,
    table_pt: float = 8.5,
    ref_pt: float = 9.0,
    fig_width: float = 14.0,
    fig_max_h: float = 7.5,
    figures: Optional[Dict[str, float]] = None,
    snap_grid: bool = False,
) -> Dict[str, object]:
    global TEXT_WIDTH_CM, TEXT_WIDTH_TWIPS
    global BODY_PT, BODY_LINE, PARA_AFTER_PT, TABLE_PT, REF_PT
    global FIG_WIDTH_CM, FIG_MAX_H_CM, FIG_OVERRIDES, SNAP_GRID

    if min(body_pt, line, table_pt, ref_pt, fig_width, fig_max_h) <= 0 or para_after < 0:
        raise ValueError("字号、行距和图片尺寸必须为正数，段后间距不能为负数。")
    if not template_path.is_file():
        raise FileNotFoundError(f"模板不存在：{template_path}")
    BODY_PT, BODY_LINE, PARA_AFTER_PT, TABLE_PT, REF_PT = body_pt, line, para_after, table_pt, ref_pt
    FIG_WIDTH_CM, FIG_MAX_H_CM = fig_width, fig_max_h
    FIG_OVERRIDES = dict(figures or {})
    SNAP_GRID = snap_grid

    lines = source.read_text(encoding="utf-8-sig").splitlines()
    first_heading = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first_heading is None or lines[first_heading].strip() != "# 作品名称":
        raise ValueError("输入开头必须是 '# 作品名称'，封面标题无法识别。")
    title_index = next_nonblank(lines, first_heading + 1)
    if title_index >= len(lines):
        raise ValueError("输入缺少封面作品名。")
    title_match = re.fullmatch(r"\*\*(.+?)\*\*", lines[title_index].strip())
    if title_match is None:
        raise ValueError("'# 作品名称' 下一行必须是粗体作品名（**作品名**）。")
    cover_title = title_match.group(1)

    formula_tokens = collect_formulas(lines)
    omml, pandoc_error = prepare_omml(formula_tokens, output.parent)
    if pandoc_error:
        print(f"警告：pandoc 公式转换失败，退回 Unicode 文本和上下标 run：{pandoc_error}", file=sys.stderr)
    formula_plan = FormulaPlan(formula_tokens, omml)

    document = Document(str(template_path))
    clear_template_body(document)
    section = document.sections[0]
    TEXT_WIDTH_TWIPS = section.page_width.twips - section.left_margin.twips - section.right_margin.twips
    TEXT_WIDTH_CM = TEXT_WIDTH_TWIPS / 567.0
    setup_document(document)
    document.core_properties.title = cover_title
    document.core_properties.subject = "竞赛技术报告"
    add_cover(document, cover_title, subtitle)

    images: List[str] = []
    image_captions: List[str] = []
    table_captions: List[str] = []
    table_count = 0
    code_block_count = 0
    equation_count = 0
    pending_table_caption = False
    in_references = False
    figures_root = figures_root.resolve()

    i = title_index + 1
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        if not stripped or stripped == "---":
            i += 1
            continue
        if pending_table_caption and not stripped.startswith("|"):
            raise ValueError(f"表题后未出现表格：{table_captions[-1]}")

        display_match = DISPLAY_MATH_RE.match(stripped)
        if display_match:
            equation_count += 1
            add_display_equation(document, display_match.group(1).strip(), formula_plan, equation_count)
            i += 1
            continue

        if CODE_FENCE_RE.match(line):
            i += 1
            code_lines: List[str] = []
            while i < len(lines) and not CODE_FENCE_RE.match(lines[i]):
                code_lines.append(lines[i].rstrip("\r"))
                i += 1
            if i == len(lines):
                raise ValueError("代码块缺少结束 ```。")
            add_code_block(document, code_lines)
            code_block_count += 1
            i += 1
            continue

        image_match = IMAGE_RE.match(line)
        if image_match:
            alt, relative_path = image_match.groups()
            rel = Path(relative_path)
            if rel.is_absolute() or rel.parts[:2] != ("figures", "v2"):
                raise ValueError(f"图片路径必须形如 figures/v2/xxx.png：{relative_path}")
            image_path = (figures_root / rel).resolve()
            try:
                image_path.relative_to(figures_root)
            except ValueError:
                raise ValueError(f"图片路径越出 --figures-root：{relative_path}")
            add_image(document, image_path, alt)
            images.append(relative_path)
            i += 1
            caption_index = next_nonblank(lines, i)
            if caption_index >= len(lines) or not IMAGE_CAPTION_RE.match(lines[caption_index].strip()):
                raise ValueError(f"图片后缺少图题：{relative_path}")
            caption_text = lines[caption_index].strip()
            add_caption(document, caption_text)
            image_captions.append(caption_text)
            i = caption_index + 1
            continue

        if stripped.startswith("|"):
            raw_rows: List[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                raw_rows.append(lines[i].strip())
                i += 1
            separators = [row for row in raw_rows if is_table_separator(row)]
            if len(separators) != 1:
                raise ValueError(f"标准表格必须且只能有一行分隔符：{raw_rows[0]}")
            if not pending_table_caption:
                raise ValueError("发现没有表题的 Markdown 表格。")
            rows = [parse_table_row(row) for row in raw_rows if not is_table_separator(row)]
            if len(rows) < 2:
                raise ValueError("Markdown 表格至少要有表头和一行数据。")
            add_markdown_table(document, rows, parse_table_alignments(separators[0]), formula_plan)
            table_count += 1
            pending_table_caption = False
            continue

        heading_match = HEADING_RE.match(stripped)
        if heading_match:
            hashes, heading_text = heading_match.groups()
            level = len(hashes)
            if level == 1:
                in_references = heading_text.strip() == "第五部分　参考文献"
            add_heading(document, level, heading_text, formula_plan)
            i += 1
            continue

        if TABLE_CAPTION_RE.match(stripped):
            if pending_table_caption:
                raise ValueError(f"连续出现表题但前一张表缺失：{table_captions[-1]}")
            table_captions.append(stripped)
            add_caption(document, stripped, keep_with_next=True)
            pending_table_caption = True
            i += 1
            continue

        if IMAGE_CAPTION_RE.match(stripped):
            raise ValueError(f"孤立图题，没有对应图片行：{stripped}")

        if stripped.startswith(">"):
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_text = lines[i].strip()[1:].lstrip()
                paragraph = document.add_paragraph()
                paragraph.paragraph_format.left_indent = Pt(24)
                paragraph.paragraph_format.right_indent = Pt(24)
                paragraph.paragraph_format.first_line_indent = Pt(0)
                paragraph.paragraph_format.line_spacing = BODY_LINE
                paragraph.paragraph_format.space_before = Pt(3)
                paragraph.paragraph_format.space_after = Pt(3)
                add_inline(paragraph, quote_text, size=BODY_PT, color=RGBColor(96, 96, 96), formula_plan=formula_plan)
                i += 1
            continue

        list_match = LIST_RE.match(line)
        if list_match:
            _indent, number, content = list_match.groups()
            paragraph = document.add_paragraph()
            # 列表项常含不可断行的长路径，两端对齐会把整行字距拉散，改用左对齐
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            paragraph.paragraph_format.left_indent = Pt(24)
            paragraph.paragraph_format.first_line_indent = Pt(-24)
            paragraph.paragraph_format.line_spacing = BODY_LINE
            paragraph.paragraph_format.space_after = Pt(4)
            paragraph.paragraph_format.widow_control = True
            prefix = paragraph.add_run(f"{number}. ")
            set_run_font(prefix, size=BODY_PT)
            add_inline(paragraph, content, size=BODY_PT, formula_plan=formula_plan)
            i += 1
            continue

        if in_references and re.match(r"^\[\d+\]\s", stripped):
            add_reference_paragraph(document, stripped, formula_plan)
            i += 1
            continue

        paragraph = document.add_paragraph()
        apply_body_paragraph(paragraph)
        add_inline(paragraph, stripped, size=BODY_PT, formula_plan=formula_plan)
        i += 1

    if pending_table_caption:
        raise ValueError(f"表题后无表格：{table_captions[-1]}")
    if formula_plan.index != len(formula_tokens):
        raise ValueError(f"有 {len(formula_tokens) - formula_plan.index} 个公式没有注入正文。")

    expected_image_labels = [str(number) for number in range(1, 16)] + ["A1"]
    expected_table_labels = [str(number) for number in range(1, 13)] + ["A1", "A2", "B1", "C1"]
    actual_image_labels = [IMAGE_CAPTION_RE.match(caption).group(1) for caption in image_captions]
    actual_table_labels = [TABLE_CAPTION_RE.match(caption).group(1) for caption in table_captions]
    if actual_image_labels != expected_image_labels:
        raise ValueError(f"图题编号不连续或顺序错误：{actual_image_labels}")
    if actual_table_labels != expected_table_labels:
        raise ValueError(f"表题编号不连续或顺序错误：{actual_table_labels}")
    if len(images) != len(expected_image_labels):
        raise ValueError(f"图片数应为 {len(expected_image_labels)}，实际 {len(images)}")
    if table_count != len(expected_table_labels):
        raise ValueError(f"表格数应为 {len(expected_table_labels)}，实际 {table_count}")

    output.parent.mkdir(parents=True, exist_ok=True)
    strip_page_break_markers(document)
    document.save(output)
    math_count = readback_math_count(output)
    return {
        "images": images,
        "image_captions": image_captions,
        "table_captions": table_captions,
        "table_count": table_count,
        "code_block_count": code_block_count,
        "formula_count": len(formula_tokens),
        "math_count": math_count,
        "formula_fallback": pandoc_error is not None,
    }


def parse_figure_overrides(values: Sequence[str]) -> Dict[str, float]:
    parsed: Dict[str, float] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--fig 应为 name=宽度cm：{value}")
        name, raw_width = value.split("=", 1)
        if not name or Path(name).name != name:
            raise ValueError(f"--fig 只接受图片文件名，不接受路径：{name}")
        try:
            width = float(raw_width)
        except ValueError as error:
            raise ValueError(f"--fig 宽度不是有效数字：{value}") from error
        if width <= 0:
            raise ValueError(f"--fig 图片宽度必须为正数：{value}")
        parsed[name] = width
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a styled DOCX from the report Markdown subset.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--source", type=Path, required=True, help="合稿 Markdown 文件")
    parser.add_argument("--figures-root", type=Path, required=True, help="图片根目录，内部应包含 figures/v2/")
    parser.add_argument("--output", type=Path, required=True, help="输出 DOCX 路径")
    parser.add_argument("--template", type=Path, default=Path("/mnt/d/submitwork/report/参考-模板.docx"), help="官方 DOCX 模板")
    parser.add_argument("--subtitle", default=SUBTITLE, help="标题下方副标题")
    parser.add_argument("--body-pt", type=float, default=10.5, help="正文与列表字号（pt）")
    parser.add_argument("--line", type=float, default=1.15, help="正文行距倍数")
    parser.add_argument("--para-after", type=float, default=3.0, help="正文段后间距（pt）")
    parser.add_argument("--table-pt", type=float, default=8.5, help="表格单元格字号（pt）")
    parser.add_argument("--ref-pt", type=float, default=9.0, help="参考文献字号（pt）")
    parser.add_argument("--fig-width", type=float, default=14.0, help="图片默认最大宽度（cm）")
    parser.add_argument("--fig-max-h", type=float, default=7.5, help="图片最大高度（cm）")
    parser.add_argument("--snap-grid", action="store_true", help="保留模板的段落对齐文档网格（默认关闭，行距按字体行高计算）")
    parser.add_argument("--fig", action="append", default=[], metavar="NAME=CM", help="单张图宽度覆盖，可重复")
    args = parser.parse_args()
    source = args.source.resolve()
    figures_root = args.figures_root.resolve()
    output = args.output.resolve()
    try:
        figure_overrides = parse_figure_overrides(args.fig)
        result = build(
            source,
            figures_root,
            output,
            template_path=args.template.resolve(),
            subtitle=args.subtitle,
            body_pt=args.body_pt,
            line=args.line,
            para_after=args.para_after,
            table_pt=args.table_pt,
            ref_pt=args.ref_pt,
            fig_width=args.fig_width,
            fig_max_h=args.fig_max_h,
            figures=figure_overrides,
            snap_grid=args.snap_grid,
        )
    except Exception as error:
        print(f"生成失败：{error}", file=sys.stderr)
        return 1

    print(f"DOCX: {output} ({output.stat().st_size} bytes)")
    print(f"图片：{len(result['images'])} 张；表格：{result['table_count']} 张；代码块段落：{result['code_block_count']}")
    print(f"公式：{result['formula_count']} 条；m:oMath：{result['math_count']}")
    print("图题清单：")
    for caption in result["image_captions"]:
        print(f"  {caption}")
    print("表题清单：")
    for caption in result["table_captions"]:
        print(f"  {caption}")
    if result["math_count"] != result["formula_count"]:
        print("注意：公式回读数与输入数不一致，检查 Pandoc 回退和 Word XML。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
