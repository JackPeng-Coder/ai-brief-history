# -*- coding: utf-8 -*-
"""
Build the PDF book 《人工智能简史：机器如何学会学习》.
Requires reportlab. The OFL fonts listed in README.md must be in fonts/.
pypdfium2 is only for previewing the generated PDF.
"""
import os, re, math, random, hashlib
from datetime import datetime

from reportlab.lib.pagesizes import mm
from reportlab.lib.units import mm as MM
from reportlab.lib.colors import Color, HexColor, white, black
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, PageBreak,
    NextPageTemplate, Table, TableStyle, KeepTogether, Flowable, LongTable,
    CondPageBreak,
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.textsplit import CANNOT_START_LINE, CANNOT_END_LINE
import reportlab.platypus.paragraph as rpara
from reportlab.rl_config import _FUZZ

# ----------------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "content")
OUTPUT = os.path.join(ROOT, "output")
os.makedirs(OUTPUT, exist_ok=True)
PDF_PATH = os.path.join(OUTPUT, "人工智能简史.pdf")

# ----------------------------------------------------------------------------
# Fonts
# ----------------------------------------------------------------------------
FONT_DIR = os.path.join(ROOT, "fonts")
REQUIRED_FONTS = [
    "NotoSerifSC-Regular.ttf",
    "NotoSerifSC-Bold.ttf",
    "NotoSansSC-Regular.ttf",
    "NotoSansSC-Bold.ttf",
    "LXGWWenKai-Regular.ttf",
]
missing_fonts = [f for f in REQUIRED_FONTS if not os.path.exists(os.path.join(FONT_DIR, f))]
if missing_fonts:
    raise SystemExit(
        "Missing font files in fonts/: " + ", ".join(missing_fonts) +
        "\nDownload the OFL fonts listed in README.md and place them in fonts/."
    )

def reg(name, file, idx=0):
    pdfmetrics.registerFont(TTFont(name, os.path.join(FONT_DIR, file), subfontIndex=idx))

reg("SS", "NotoSerifSC-Regular.ttf")
reg("SS-Bold", "NotoSerifSC-Bold.ttf")
reg("SS-Italic", "LXGWWenKai-Regular.ttf")
reg("YH", "NotoSansSC-Regular.ttf")
reg("YH-Bold", "NotoSansSC-Bold.ttf")
pdfmetrics.registerFontFamily("SS", normal="SS", bold="SS-Bold", italic="SS-Italic", boldItalic="SS-Bold")
pdfmetrics.registerFontFamily("YH", normal="YH", bold="YH-Bold", italic="YH", boldItalic="YH-Bold")

# ----------------------------------------------------------------------------
# Palette & geometry
# ----------------------------------------------------------------------------
PAGE_W, PAGE_H = 170 * mm, 240 * mm
MARGIN_L = 22 * mm
MARGIN_R = 18 * mm
MARGIN_T = 21 * mm
MARGIN_B = 21 * mm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R
CONTENT_H = PAGE_H - MARGIN_T - MARGIN_B

INK = HexColor("#17324D")
INK_LIGHT = HexColor("#2E4A63")
VERMILION = HexColor("#B23A2E")
GOLD = HexColor("#A9824E")
GOLD_LIGHT = HexColor("#D6BC8A")
PAPER = HexColor("#FFFFFF")
PAPER_DARK = HexColor("#EEF2F6")
TEXT = HexColor("#1C1C1C")
GRAY = HexColor("#666666")
LIGHT_GRAY = HexColor("#A0A0A0")
RULE = HexColor("#D9D9D9")

BOOK_TITLE = "人工智能简史"
BOOK_SUBTITLE = "机器如何学会学习"
BOOK_EN = "A BRIEF HISTORY OF ARTIFICIAL INTELLIGENCE"
AUTHOR = "ai-brief-history 项目 编著"
EDITION = "2026年11月 · 第一版"

# ----------------------------------------------------------------------------
# CJK line breaking with kinsoku (avoid punctuation at line start/end)
# ----------------------------------------------------------------------------
CANNOT_START = set(CANNOT_START_LINE[0] + CANNOT_START_LINE[1] + CANNOT_START_LINE[2])
CANNOT_START |= set("”’」』】》〉〕）］｝，。、；：！？…—～%‰℃")
CANNOT_END = set(CANNOT_END_LINE[0] + CANNOT_END_LINE[1])
CANNOT_END |= set("（《「『【〔〈“‘")

def _tokens(text):
    """Split into CJK single chars and Latin words; keep numbers and units together."""
    out = []
    buf = ""
    for ch in text:
        if ord(ch) >= 0x2E80 or ch in "，。、；：！？…—～%‰℃“”‘’（）《》〈〉【】「」『』〔〕［］｛｝":
            if buf:
                out.append(buf); buf = ""
            out.append(ch)
        elif ch.isalnum() or ch in "'’_-" or (ch in ".%^" and buf and any(c.isdigit() for c in buf)):
            buf += ch
        elif ch == " ":
            if buf:
                out.append(buf); buf = ""
            out.append(" ")
        else:
            if buf:
                out.append(buf); buf = ""
            out.append(ch)
    if buf:
        out.append(buf)
    # Merge "1956" + "年", "90" + "%", "2.2" + "万" so they do not split across lines.
    merged = []
    for tok in out:
        if (merged and re.fullmatch(r"[0-9][0-9.,%^]*", merged[-1])
                and tok in ("年", "月", "日", "万", "亿", "%", "％")):
            merged[-1] += tok
        else:
            merged.append(tok)
    return merged

def _cjk_split(frags, maxWidths, calcBounds, encoding="utf8"):
    """Greedy CJK line breaker with kinsoku and correct overflow handling."""
    U = []
    for f in frags:
        text = f.text
        if isinstance(text, bytes):
            text = text.decode(encoding)
        if text:
            U.extend([rpara.cjkU(t, f, encoding) for t in _tokens(text)])
        else:
            U.append(rpara.cjkU(text, f, encoding))

    if not U:
        return rpara.ParaLines(kind=1, lines=[])

    # Split a single token that is wider than the line (rare, e.g. a long URL).
    first_width = maxWidths[0] if isinstance(maxWidths, (list, tuple)) else maxWidths
    expanded = []
    for tok in U:
        if len(tok) > 1 and tok.width > first_width:
            expanded.extend(rpara.cjkU(ch, tok.frag, encoding) for ch in tok)
        else:
            expanded.append(tok)
    U = expanded
    n = len(U)

    ranges = []
    i = 0
    while i < n:
        while i < n and U[i] == " ":
            i += 1
        if i >= n:
            break
        line_start = i
        max_width = maxWidths[min(len(ranges), len(maxWidths) - 1)] if isinstance(maxWidths, (list, tuple)) else maxWidths
        width = 0
        while i < n:
            tok = U[i]
            w = tok.width
            if hasattr(w, "normalizedValue"):
                w._normalizer = max_width
                w = w.normalizedValue(max_width)
            # The token that would overflow is NOT included in this line.
            if width + w > max_width + _FUZZ and i > line_start:
                break
            width += w
            i += 1
            if hasattr(tok.frag, "lineBreak"):
                break

        j = i
        if j <= line_start:
            j = line_start + 1
        # If the next token is closing punctuation, break earlier so it does
        # not start the next line.
        guard = 0
        while j > line_start + 1 and j < n and U[j] in CANNOT_START and guard < 30:
            j -= 1
            guard += 1
        # If the last token is opening punctuation, move it to the next line.
        guard = 0
        while j > line_start + 1 and U[j - 1] in CANNOT_END and guard < 30:
            j -= 1
            guard += 1
        if j <= line_start:
            j = line_start + 1
        ranges.append((line_start, j))
        i = j

    # Avoid a last line containing only one or two CJK characters.
    def cjk_count(a, b):
        return sum(1 for k in range(a, b) if len(U[k]) == 1 and ord(U[k]) >= 0x2E80)

    if len(ranges) >= 2:
        s, e = ranges[-1]
        ps, pe = ranges[-2]
        if cjk_count(s, e) <= 2 and cjk_count(ps, pe) >= 4:
            new_pe = pe - 1
            guard = 0
            while new_pe > ps + 1 and U[new_pe] in CANNOT_START and guard < 10:
                new_pe -= 1
                guard += 1
            guard = 0
            while new_pe > ps + 1 and U[new_pe - 1] in CANNOT_END and guard < 10:
                new_pe -= 1
                guard += 1
            if new_pe > ps:
                ranges[-2] = (ps, new_pe)
                ranges[-1] = (new_pe, e)

    lines = []
    for idx, (s, e) in enumerate(ranges):
        max_width = maxWidths[min(idx, len(maxWidths) - 1)] if isinstance(maxWidths, (list, tuple)) else maxWidths
        line_width = sum(U[k].width for k in range(s, e))
        lines.append(rpara.makeCJKParaLine(U[s:e], max_width, line_width,
                                           max_width - line_width, False, calcBounds))
    return rpara.ParaLines(kind=1, lines=lines)

def _break_lines_cjk(self, maxWidths):
    """Force every paragraph through the kinsoku-aware breaker, including single-frag ones."""
    if not isinstance(maxWidths, (list, tuple)):
        maxWidths = [maxWidths]
    style = self.style
    self.height = 0
    rpara._handleBulletWidth(self.bulletText, style, maxWidths)
    frags = self.frags
    if hasattr(self, "blPara") and getattr(self, "_splitpara", 0):
        return self.blPara
    if len(frags) <= 0:
        return rpara.ParaLines(kind=0, fontSize=style.fontSize, fontName=style.fontName,
                               textColor=style.textColor, lines=[],
                               ascent=style.fontSize, descent=-0.2 * style.fontSize)
    autoLeading = getattr(self, "autoLeading", getattr(style, "autoLeading", ""))
    calcBounds = autoLeading not in ("", "off")
    return _cjk_split(frags, maxWidths, calcBounds)

rpara.cjkFragSplit = _cjk_split
rpara.Paragraph.breakLinesCJK = _break_lines_cjk
rpara.ALL_CANNOT_START = "".join(CANNOT_START)

# ----------------------------------------------------------------------------
# Styles
# ----------------------------------------------------------------------------
def style(name, **kw):
    base = dict(fontName="SS", fontSize=10.5, leading=18.4, textColor=TEXT,
                wordWrap="CJK", allowWidows=0, allowOrphans=0)
    base.update(kw)
    return ParagraphStyle(name, **base)

S = {
    "body": style("Body", alignment=TA_LEFT, firstLineIndent=21, spaceAfter=3.2),
    "body_noindent": style("BodyNoIndent", alignment=TA_LEFT, firstLineIndent=0, spaceAfter=3.2),
    "body_small": style("BodySmall", fontSize=9.2, leading=16.2, alignment=TA_LEFT, firstLineIndent=18, textColor=HexColor("#33302A")),
    "lead": style("Lead", fontName="SS-Italic", fontSize=10.2, leading=17.5, textColor=INK_LIGHT, alignment=TA_LEFT, firstLineIndent=0, spaceAfter=10),
    "h2": style("H2", fontName="YH-Bold", fontSize=15, leading=23, textColor=INK, spaceBefore=16, spaceAfter=8, firstLineIndent=0, keepWithNext=1),
    "h3": style("H3", fontName="YH-Bold", fontSize=11.2, leading=18, textColor=VERMILION, spaceBefore=10, spaceAfter=3, firstLineIndent=0, keepWithNext=1),
    "quote": style("Quote", fontName="SS-Italic", fontSize=10.0, leading=17.2, textColor=HexColor("#5B4A3A"), alignment=TA_LEFT, firstLineIndent=0, leftIndent=10, rightIndent=6),
    "caption": style("Caption", fontName="YH", fontSize=8.2, leading=12, textColor=GRAY, alignment=TA_CENTER, firstLineIndent=0, spaceBefore=3, spaceAfter=10),
    "note_title": style("NoteTitle", fontName="YH-Bold", fontSize=9.4, leading=14, textColor=INK, firstLineIndent=0, spaceAfter=3),
    "note_body": style("NoteBody", fontSize=9.2, leading=16.0, alignment=TA_LEFT, firstLineIndent=0, textColor=HexColor("#2C2A25")),
    "note_item": style("NoteItem", fontSize=9.2, leading=16.0, alignment=TA_LEFT, firstLineIndent=0, leftIndent=16, bulletIndent=2, bulletFontName="SS", textColor=HexColor("#2C2A25"), spaceAfter=1),
    "table": style("Table", fontSize=8.3, leading=13.2, alignment=TA_LEFT, firstLineIndent=0),
    "table_head": style("TableHead", fontName="YH-Bold", fontSize=8.4, leading=13.2, textColor=INK, alignment=TA_LEFT, firstLineIndent=0),
    "toc_title": style("TOCTitle", fontName="YH-Bold", fontSize=26, leading=34, textColor=INK, alignment=TA_LEFT, firstLineIndent=0),
    "toc_part": style("TOCPart", fontName="YH-Bold", fontSize=11.5, leading=21, textColor=INK, firstLineIndent=0, spaceBefore=9, spaceAfter=2, wordWrap="CJK"),
    "toc_chapter": style("TOCChapter", fontName="SS", fontSize=10.3, leading=18.2, textColor=TEXT, firstLineIndent=0, leftIndent=12, wordWrap="CJK"),
    "toc_section": style("TOCSection", fontName="SS", fontSize=9.2, leading=15.0, textColor=GRAY, firstLineIndent=0, leftIndent=30, wordWrap="CJK"),
    "front_title": style("FrontTitle", fontName="YH-Bold", fontSize=30, leading=42, textColor=INK, alignment=TA_CENTER, firstLineIndent=0),
    "front_sub": style("FrontSub", fontName="SS-Italic", fontSize=13, leading=22, textColor=GRAY, alignment=TA_CENTER, firstLineIndent=0),
    "front_small": style("FrontSmall", fontName="YH", fontSize=8.5, leading=14, textColor=GRAY, alignment=TA_CENTER, firstLineIndent=0),
    "bullet": style("Bullet", alignment=TA_LEFT, firstLineIndent=0, leftIndent=18, bulletIndent=4, bulletFontName="SS", spaceAfter=2),
    "number": style("Number", alignment=TA_LEFT, firstLineIndent=0, leftIndent=22, bulletIndent=4, bulletFontName="SS", spaceAfter=3),
}

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def esc(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

def inline(t):
    t = esc(t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<link href="\2" color="#8B3A2E">\1</link>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"`([^`]+)`", r'<font name="SS" color="#8B3A2E">\1</font>', t)
    return t

def P(text, st="body"):
    return Paragraph(inline(text), S[st])

def clean_text(t):
    return re.sub(r"\s+", " ", t).strip()

def _is_cjk(ch):
    return bool(ch) and (ord(ch) >= 0x2E80 or ch in "，。、；：！？…—～%‰℃“”‘’（）《》〈〉【】「」『』〔〕［］｛｝")

def join_lines(lines):
    """Join hard-wrapped Markdown lines without inserting spaces between CJK chars."""
    if not lines:
        return ""
    out = lines[0].strip()
    for nxt in lines[1:]:
        nxt = nxt.strip()
        if not nxt:
            continue
        a, b = out[-1] if out else "", nxt[0]
        if _is_cjk(a) or _is_cjk(b):
            out += nxt
        else:
            out += " " + nxt
    return out

def draw_wrapped(canv, text, x, y_top, width, font="SS", size=9.5, leading=16,
                 color=TEXT, align="left"):
    """Draw CJK-aware wrapped text on canvas; returns y after last line."""
    canv.setFont(font, size)
    canv.setFillColor(color)
    lines = []
    cur = ""
    for tok in _tokens(text):
        if tok == "\n":
            lines.append(cur.rstrip()); cur = ""; continue
        test = cur + tok
        if stringWidth(test, font, size) > width and cur.strip():
            lines.append(cur.rstrip())
            cur = tok.lstrip()
        else:
            cur = test
    if cur.strip():
        lines.append(cur.rstrip())
    y = y_top
    for line in lines:
        if align == "center":
            canv.drawCentredString(x + width / 2, y, line)
        elif align == "right":
            canv.drawRightString(x + width, y, line)
        else:
            canv.drawString(x, y, line)
        y -= leading
    return y

# ----------------------------------------------------------------------------
# Flowables
# ----------------------------------------------------------------------------
class SceneBreak(Flowable):
    def __init__(self, width=CONTENT_W):
        super().__init__()
        self.width = width
        self.height = 9 * mm
    def wrap(self, aw, ah):
        return self.width, self.height
    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(GOLD)
        c.setFont("SS", 8)
        c.drawCentredString(self.width / 2, 3 * mm, "◆   ◆   ◆")
        c.restoreState()

class QuoteBlock(Flowable):
    def __init__(self, text, width=CONTENT_W):
        super().__init__()
        self.text = text
        self.width = width
        self.p = Paragraph(inline(text), S["quote"])
        self.height = 0
    def wrap(self, aw, ah):
        w, h = self.p.wrap(self.width - 16, ah)
        self.height = h + 6
        return self.width, self.height
    def draw(self):
        c = self.canv
        c.saveState()
        c.setStrokeColor(VERMILION)
        c.setLineWidth(1.6)
        c.line(2, 3, 2, self.height - 3)
        self.p.drawOn(c, 14, 3)
        c.restoreState()

class NoteBox(Flowable):
    def __init__(self, title, items, width=CONTENT_W):
        super().__init__()
        self.title = title
        self.width = width
        self.flows = []
        if title:
            self.flows.append(P(title, "note_title"))
        for kind, bullet, text in items:
            if kind == "p":
                self.flows.append(P(text, "note_body"))
            else:
                self.flows.append(Paragraph(inline(text), S["note_item"], bulletText=bullet))
        self.height = 0
    def wrap(self, aw, ah):
        w = self.width - 24
        h = 0
        for f in self.flows:
            _, fh = f.wrap(w, ah)
            h += fh + 2
        self.height = h + 22
        return self.width, self.height
    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(HexColor("#F7F7F7"))
        c.setStrokeColor(HexColor("#DDDDDD"))
        c.setLineWidth(0.5)
        c.roundRect(0, 0, self.width, self.height, 2 * mm, fill=1, stroke=1)
        c.setFillColor(GOLD)
        c.rect(0, 0, 2.2, self.height, fill=1, stroke=0)
        y = self.height - 10
        for f in self.flows:
            _, fh = f.wrap(self.width - 24, self.height)
            f.drawOn(c, 14, y - fh)
            y -= fh + 2
        c.restoreState()

class Figure(Flowable):
    def __init__(self, fig_id, caption, width=CONTENT_W, height=None):
        super().__init__()
        self.fig_id = fig_id
        self.caption = caption
        self.width = width
        self.height = height or 55 * mm
        self.cap = P(caption, "caption")
        self.cap_h = 0
    def wrap(self, aw, ah):
        _, self.cap_h = self.cap.wrap(self.width, 50)
        return self.width, self.height + self.cap_h + 4
    def draw(self):
        c = self.canv
        c.saveState()
        c.translate(0, self.cap_h + 4)
        draw_figure(c, self.fig_id, self.width, self.height)
        c.restoreState()
        self.cap.drawOn(c, 0, 0)

class ChapterOpener(Flowable):
    def __init__(self, label, title, subtitle, lead, width=CONTENT_W):
        super().__init__()
        self.label = label
        self.title = title
        self.subtitle = subtitle
        self.lead = lead
        self.width = width
        self.height = 74 * mm
        self._toc_level = 1
        self._toc_text = f"{label}　{title}"
        self._toc_kind = "chapter"
        self._bookmark_key = "ch_" + hashlib.md5(self._toc_text.encode("utf8")).hexdigest()[:10]
    def wrap(self, aw, ah):
        return self.width, self.height
    def draw(self):
        c = self.canv
        doc = getattr(c, "_bookmarkDoc", None)
        # background chapter number
        num = {"第一章": "01", "第二章": "02", "第三章": "03", "第四章": "04",
               "第五章": "05", "第六章": "06", "第七章": "07", "第八章": "08",
               "第九章": "09", "第十章": "10", "第十一章": "11", "第十二章": "12",
               "第十三章": "13"}.get(self.label, "")
        c.saveState()
        if num:
            long_title = stringWidth(self.title, "YH-Bold", 26) > 100 * mm
            size = 58 if long_title else 96
            y = self.height - (8 * mm if long_title else 22 * mm)
            c.setFillColor(HexColor("#F0F0F0"))
            c.setFont("YH-Bold", size)
            c.drawRightString(self.width, y, num)
        c.restoreState()
        # label
        c.saveState()
        c.setFillColor(VERMILION)
        c.setFont("YH-Bold", 9.5)
        c.drawString(0, self.height - 10 * mm, self.label, charSpace=2)
        # title
        c.setFillColor(INK)
        c.setFont("YH-Bold", 26)
        # simple two-line split if too wide
        maxw = self.width - 4
        if stringWidth(self.title, "YH-Bold", 26) > maxw:
            # split near middle
            mid = len(self.title) // 2
            l1, l2 = self.title[:mid], self.title[mid:]
            c.drawString(0, self.height - 24 * mm, l1)
            c.drawString(0, self.height - 34 * mm, l2)
            ty = self.height - 41 * mm
        else:
            c.drawString(0, self.height - 24 * mm, self.title)
            ty = self.height - 31 * mm
        # subtitle
        c.setFillColor(GRAY)
        c.setFont("SS-Italic", 11.5)
        c.drawString(0, ty, self.subtitle)
        # rule
        c.setStrokeColor(GOLD)
        c.setLineWidth(0.8)
        c.line(0, ty - 5 * mm, 34 * mm, ty - 5 * mm)
        # lead
        c.setFillColor(HexColor("#444444"))
        draw_wrapped(c, self.lead, 0, ty - 11 * mm, self.width - 10 * mm,
                     font="SS", size=9.3, leading=16, color=HexColor("#444444"))
        c.restoreState()

class PartDivider(Flowable):
    def __init__(self, num, title, years, epigraph, source, intro):
        super().__init__()
        self.num = num
        self.title = title
        self.years = years
        self.epigraph = epigraph
        self.source = source
        self.intro = intro
        self.width = PAGE_W
        self.height = PAGE_H - 0.5
        self.display_num = {"一": "01", "二": "02", "三": "03", "四": "04", "附": "A"}.get(num, "A")
        self.roman = {"一": "I", "二": "II", "三": "III", "四": "IV", "附": ""}.get(num, "")
        self.part_label = "APPENDIX" if num == "附" else f"PART {self.roman}"
        self._toc_level = 0
        self._toc_text = "附录" if num == "附" else (f"第{num}部　{title}")
        self._bookmark_key = "part_" + hashlib.md5(self._toc_text.encode("utf8")).hexdigest()[:10]
    def wrap(self, aw, ah):
        return self.width, self.height
    def draw(self):
        c = self.canv
        c.saveState()
        # white background
        c.setFillColor(PAPER)
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        # huge number
        c.setFillColor(HexColor("#F2F2F2"))
        c.setFont("YH-Bold", 110)
        c.drawRightString(PAGE_W - 14 * mm, PAGE_H - 52 * mm, self.display_num)
        # top label
        c.setFillColor(VERMILION)
        c.setFont("YH-Bold", 10)
        c.drawString(22 * mm, PAGE_H - 38 * mm, self.part_label, charSpace=4)
        c.setStrokeColor(GOLD)
        c.setLineWidth(0.6)
        c.line(22 * mm, PAGE_H - 44 * mm, 58 * mm, PAGE_H - 44 * mm)
        # title
        c.setFillColor(INK)
        c.setFont("YH-Bold", 34)
        c.drawString(22 * mm, PAGE_H - 72 * mm, self.title)
        c.setFillColor(GRAY)
        c.setFont("SS", 12)
        c.drawString(22 * mm, PAGE_H - 84 * mm, self.years)
        # epigraph
        y = draw_wrapped(c, self.epigraph, 22 * mm, PAGE_H - 116 * mm, PAGE_W - 44 * mm,
                         font="SS-Italic", size=12, leading=22, color=INK_LIGHT)
        source_y = max(64 * mm, y - 4 * mm)
        c.setFillColor(GRAY)
        c.setFont("SS", 8.5)
        c.drawString(22 * mm, source_y, self.source)
        # intro
        intro_y = 60 * mm if source_y >= 70 * mm else max(30 * mm, source_y - 10 * mm)
        draw_wrapped(c, self.intro, 22 * mm, intro_y, PAGE_W - 50 * mm,
                     font="SS", size=9.5, leading=17, color=GRAY)
        # footer mark
        c.setFillColor(LIGHT_GRAY)
        c.setFont("YH", 8)
        c.drawString(22 * mm, 20 * mm, "人工智能简史 · " + ("附录" if self.num == "附" else f"第{self.num}部"))
        c.restoreState()

class AppendixHeading(Flowable):
    def __init__(self, text, width=CONTENT_W):
        super().__init__()
        self.text = text
        self.width = width
        self.height = 30 * mm
        self._toc_level = 1
        self._toc_text = text
        self._toc_kind = "appendix"
        self._bookmark_key = "app_" + hashlib.md5(text.encode("utf8")).hexdigest()[:10]
    def wrap(self, aw, ah):
        return self.width, self.height
    def draw(self):
        c = self.canv
        c.saveState()
        c.setFillColor(VERMILION)
        c.setFont("YH-Bold", 8.5)
        c.drawString(0, self.height - 8 * mm, "APPENDIX", charSpace=2)
        c.setFillColor(INK)
        c.setFont("YH-Bold", 22)
        c.drawString(0, self.height - 19 * mm, self.text)
        c.setStrokeColor(GOLD)
        c.setLineWidth(0.8)
        c.line(0, self.height - 24 * mm, 40 * mm, self.height - 24 * mm)
        c.restoreState()

# ----------------------------------------------------------------------------
# Figures (vector)
# ----------------------------------------------------------------------------
def _frame(c, w, h):
    c.setFillColor(PAPER)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.5)
    c.roundRect(0, 0, w, h, 1.5 * mm, fill=1, stroke=1)

def _label(c, x, y, text, size=7.5, color=GRAY, font="YH", align="left"):
    c.setFillColor(color)
    c.setFont(font, size)
    if align == "center":
        c.drawCentredString(x, y, text)
    elif align == "right":
        c.drawRightString(x, y, text)
    else:
        c.drawString(x, y, text)

def fig_timeline(c, w, h):
    _frame(c, w, h)
    pad = 24
    y = h * 0.52
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.2)
    c.line(pad, y, w - pad, y)
    events = [
        ("1950", "图灵之问"), ("1956", "达特茅斯"), ("1974", "第一次寒冬"),
        ("1987", "第二次寒冬"), ("2012", "AlexNet"), ("2017", "Transformer"),
        ("2022", "ChatGPT"), ("2026", "智能体"),
    ]
    n = len(events)
    for i, (yr, lab) in enumerate(events):
        x = pad + (w - 2 * pad) * i / (n - 1)
        up = i % 2 == 0
        c.setFillColor(VERMILION if lab in ("AlexNet", "ChatGPT") else INK)
        c.circle(x, y, 3.2, fill=1, stroke=0)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.6)
        c.line(x, y, x, y + (14 if up else -14))
        _label(c, x, y + (18 if up else -23), yr, size=8, color=INK, font="YH-Bold", align="center")
        _label(c, x, y + (30 if up else -35), lab, size=7.2, color=GRAY, font="YH", align="center")
    _label(c, pad, h - 12, "从符号到规模：AI 的七十年", size=8, color=GRAY)

def fig_turing(c, w, h):
    _frame(c, w, h)
    tape_y = h * 0.52
    cell = (w - 60) / 9
    x0 = 30
    for i in range(9):
        x = x0 + i * cell
        c.setFillColor(PAPER if i % 2 == 0 else HexColor("#F2F2F2"))
        c.setStrokeColor(RULE)
        c.setLineWidth(0.6)
        c.rect(x, tape_y, cell, 20, fill=1, stroke=1)
        if i in (3, 4, 5):
            _label(c, x + cell / 2, tape_y + 6, "01"[i % 2], size=9, color=INK, font="YH-Bold", align="center")
    # head
    hx = x0 + 4 * cell + cell / 2
    c.setFillColor(VERMILION)
    c.setStrokeColor(VERMILION)
    c.setLineWidth(1.0)
    c.rect(hx - 12, tape_y - 24, 24, 18, fill=0, stroke=1)
    c.line(hx, tape_y - 24, hx, tape_y - 2)
    _label(c, hx, tape_y - 38, "读写头", size=7.2, color=VERMILION, align="center")
    # state box
    bx = w - 95
    by = h - 42
    c.setFillColor(INK)
    c.roundRect(bx, by, 78, 30, 2, fill=1, stroke=0)
    _label(c, bx + 8, by + 21, "状态表", size=7.5, color=GOLD_LIGHT)
    _label(c, bx + 8, by + 11, "读入 → 写入", size=6.4, color=PAPER)
    _label(c, bx + 8, by + 3, "移动 / 新状态", size=6.4, color=PAPER)
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.6)
    c.line(hx + 12, tape_y + 10, bx, by + 4)
    _label(c, 8, 10, "无限长的纸带", size=7, color=GRAY)

def fig_perceptron(c, w, h):
    _frame(c, w, h)
    xs = [w * 0.16, w * 0.16, w * 0.16]
    ys = [h * 0.72, h * 0.50, h * 0.28]
    labels = ["x1", "x2", "x3"]
    for x, y, lab in zip(xs, ys, labels):
        c.setFillColor(PAPER)
        c.setStrokeColor(INK)
        c.setLineWidth(0.8)
        c.circle(x, y, 10, fill=1, stroke=1)
        _label(c, x, y - 3, lab, size=8, color=INK, align="center")
    # weights
    tx, ty = w * 0.52, h * 0.50
    for x, y, wt in zip(xs, ys, ["w1", "w2", "w3"]):
        c.setStrokeColor(GOLD)
        c.setLineWidth(1.0)
        c.line(x + 10, y, tx - 18, ty)
        _label(c, (x + tx) / 2 - 4, (y + ty) / 2 + 5, wt, size=7, color=GOLD)
    c.setFillColor(INK)
    c.circle(tx, ty, 18, fill=1, stroke=0)
    _label(c, tx, ty - 3, "Σ", size=12, color=PAPER, align="center")
    # threshold
    c.setStrokeColor(VERMILION)
    c.setLineWidth(1.0)
    c.line(tx + 18, ty, tx + 55, ty)
    c.setFillColor(VERMILION)
    c.rect(tx + 55, ty - 10, 34, 20, fill=1, stroke=0)
    _label(c, tx + 72, ty - 3, "阈值", size=7, color=PAPER, align="center")
    c.setStrokeColor(INK)
    c.line(tx + 89, ty, w - 30, ty)
    c.setFillColor(PAPER)
    c.setStrokeColor(INK)
    c.circle(w - 25, ty, 9, fill=1, stroke=1)
    _label(c, w - 25, ty - 3, "y", size=8, color=INK, align="center")
    _label(c, 10, 10, "输入 × 权重 → 求和 → 超过阈值则输出 1", size=7, color=GRAY)

def fig_winters(c, w, h):
    _frame(c, w, h)
    left, right, bottom, top = 24, w - 16, 24, h - 18
    c.setStrokeColor(RULE)
    c.setLineWidth(0.5)
    c.line(left, bottom, right, bottom)
    c.line(left, bottom, left, top)
    _label(c, left, top + 4, "期望", size=7, color=GRAY)
    _label(c, right - 4, bottom - 12, "时间", size=7, color=GRAY, align="right")
    # wave
    pts = []
    for i in range(241):
        t = i / 240
        x = left + (right - left) * t
        env = 0.55 + 0.45 * math.sin(t * math.pi * 2.1 + 0.6)
        y = bottom + (top - bottom) * (0.42 + 0.34 * math.sin(t * 9.2) * env + 0.1 * math.sin(t * 21))
        pts.append((x, y))
    c.setStrokeColor(INK)
    c.setLineWidth(1.2)
    p = c.beginPath()
    p.moveTo(*pts[0])
    for pt in pts[1:]:
        p.lineTo(*pt)
    c.drawPath(p)
    # labels
    marks = [(0.10, "1956"), (0.30, "1974"), (0.50, "1987"), (0.68, "2012"), (0.86, "2022")]
    for t, lab in marks:
        x = left + (right - left) * t
        c.setStrokeColor(VERMILION)
        c.setLineWidth(0.5)
        c.line(x, bottom, x, bottom + 5)
        _label(c, x, bottom - 12, lab, size=7, color=GRAY, align="center")
    _label(c, left + 8, top - 8, "热潮", size=7, color=VERMILION)
    _label(c, left + 8, bottom + 8, "寒冬", size=7, color=GRAY)

def fig_alexnet(c, w, h):
    _frame(c, w, h)
    left, right, bottom, top = 46, w - 20, 26, h - 20
    data = [("2010", 28.2), ("2011", 25.8), ("2012", 16.4), ("2013", 11.7), ("2014", 6.7), ("2015", 3.6)]
    maxv = 32
    bw = (right - left) / len(data) * 0.55
    for i, (yr, v) in enumerate(data):
        x = left + (right - left) * (i + 0.5) / len(data) - bw / 2
        bh = (top - bottom) * v / maxv
        c.setFillColor(VERMILION if yr == "2012" else INK_LIGHT)
        c.rect(x, bottom, bw, bh, fill=1, stroke=0)
        _label(c, x + bw / 2, bottom + bh + 5, f"{v:.1f}%", size=7.2, color=INK, font="YH-Bold", align="center")
        _label(c, x + bw / 2, bottom - 12, yr, size=7, color=GRAY, align="center")
    # axis
    c.setStrokeColor(RULE)
    c.setLineWidth(0.5)
    c.line(left, bottom, right, bottom)
    c.line(left, bottom, left, top)
    _label(c, 8, top - 2, "top-5 错误率", size=7, color=GRAY)

def fig_rl(c, w, h):
    _frame(c, w, h)
    cx, cy = w * 0.50, h * 0.52
    # agent box
    c.setFillColor(INK)
    c.roundRect(cx - 78, cy + 18, 70, 26, 3, fill=1, stroke=0)
    _label(c, cx - 43, cy + 27, "智能体", size=8, color=PAPER, align="center")
    # env box
    c.setFillColor(VERMILION)
    c.roundRect(cx + 8, cy + 18, 70, 26, 3, fill=1, stroke=0)
    _label(c, cx + 43, cy + 27, "环境", size=8, color=PAPER, align="center")
    # arrows
    c.setStrokeColor(INK)
    c.setLineWidth(1.0)
    c.line(cx - 43, cy + 18, cx - 43, cy - 16)
    c.line(cx - 43, cy - 16, cx + 43, cy - 16)
    c.line(cx + 43, cy - 16, cx + 43, cy + 18)
    c.setFillColor(INK)
    p = c.beginPath()
    p.moveTo(cx + 43, cy + 18); p.lineTo(cx + 39, cy + 10); p.lineTo(cx + 47, cy + 10)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    _label(c, cx, cy - 10, "动作", size=7.5, color=INK, align="center")
    # feedback loop: environment -> agent
    c.setStrokeColor(VERMILION)
    c.setLineWidth(1.0)
    c.line(cx + 43, cy + 44, cx + 43, cy + 56)
    c.line(cx + 43, cy + 56, cx - 43, cy + 56)
    c.line(cx - 43, cy + 56, cx - 43, cy + 44)
    c.setFillColor(VERMILION)
    p = c.beginPath()
    p.moveTo(cx - 43, cy + 44); p.lineTo(cx - 47, cy + 50); p.lineTo(cx - 39, cy + 50)
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    _label(c, cx, cy + 60, "状态 / 奖励", size=7.5, color=VERMILION, align="center")
    _label(c, 10, 10, "智能体根据奖励调整策略，环境根据动作给出新状态", size=7, color=GRAY)

def fig_transformer(c, w, h):
    _frame(c, w, h)
    tokens = ["这", "只", "猫", "很", "可", "爱"]
    n = len(tokens)
    x0 = 22
    gap = (w - 2 * x0) / (n - 1)
    y = h * 0.38
    for i, t in enumerate(tokens):
        x = x0 + i * gap
        c.setFillColor(PAPER)
        c.setStrokeColor(INK)
        c.setLineWidth(0.8)
        c.circle(x, y, 11, fill=1, stroke=1)
        _label(c, x, y - 3, t, size=8, color=INK, align="center")
    # attention lines from 猫 (index 2) to all
    src = x0 + 2 * gap
    for i in range(n):
        x = x0 + i * gap
        alpha = min(0.95, 0.18 + 0.12 * (n - abs(i - 2)))
        c.setStrokeColor(Color(VERMILION.red, VERMILION.green, VERMILION.blue, alpha=alpha))
        c.setLineWidth(0.8 + 0.5 * (n - abs(i - 2)))
        c.line(src, y + 11, x, y + 38)
        c.circle(x, y + 38, 2, fill=1, stroke=0)
    _label(c, src, y + 50, "查询：猫", size=7.2, color=VERMILION, align="center")
    _label(c, 10, 10, "每个词都与其他词计算相关性，权重由数据学习得到", size=7, color=GRAY)

def fig_rlhf(c, w, h):
    _frame(c, w, h)
    steps = [("预训练", "海量文本"), ("监督微调", "人类示范"), ("奖励模型", "人类排序"), ("强化学习", "偏好优化")]
    bw, gap = 58, 12
    total = len(steps) * bw + (len(steps) - 1) * gap
    x0 = (w - total) / 2
    y = h * 0.42
    for i, (t1, t2) in enumerate(steps):
        x = x0 + i * (bw + gap)
        c.setFillColor(INK if i < 2 else VERMILION)
        c.roundRect(x, y, bw, 34, 3, fill=1, stroke=0)
        _label(c, x + bw / 2, y + 20, t1, size=7.6, color=PAPER, align="center")
        _label(c, x + bw / 2, y + 9, t2, size=6.8, color=GOLD_LIGHT, align="center")
        if i < len(steps) - 1:
            c.setStrokeColor(GOLD)
            c.setLineWidth(1.0)
            c.line(x + bw + 2, y + 17, x + bw + gap - 2, y + 17)
            c.setFillColor(GOLD)
            p = c.beginPath()
            p.moveTo(x + bw + gap - 2, y + 17); p.lineTo(x + bw + gap - 6, y + 14); p.lineTo(x + bw + gap - 6, y + 20)
            p.close(); c.drawPath(p, fill=1, stroke=0)
    _label(c, 10, 10, "从“会说话”到“说人话”：RLHF 用人类偏好校准模型", size=7, color=GRAY)

def fig_scaling(c, w, h):
    _frame(c, w, h)
    left, right, bottom, top = 40, w - 18, 28, h - 18
    c.setStrokeColor(RULE)
    c.setLineWidth(0.5)
    c.line(left, bottom, right, bottom)
    c.line(left, bottom, left, top)
    _label(c, 8, top - 2, "能力", size=7, color=GRAY)
    _label(c, right - 4, bottom - 12, "计算量 / 思考时间", size=7, color=GRAY, align="right")
    # curve 1: training scaling (log-like)
    p1 = c.beginPath()
    for i in range(101):
        t = i / 100
        x = left + (right - left) * t
        y = bottom + (top - bottom) * (0.08 + 0.72 * (1 - math.exp(-3.2 * t)))
        if i == 0: p1.moveTo(x, y)
        else: p1.lineTo(x, y)
    c.setStrokeColor(INK)
    c.setLineWidth(1.4)
    c.drawPath(p1)
    # curve 2: test-time scaling (steeper, later)
    p2 = c.beginPath()
    for i in range(101):
        t = i / 100
        x = left + (right - left) * t
        y = bottom + (top - bottom) * (0.05 + 0.80 * (1 - math.exp(-5.0 * max(0, t - 0.18))))
        if i == 0: p2.moveTo(x, y)
        else: p2.lineTo(x, y)
    c.setStrokeColor(VERMILION)
    c.setLineWidth(1.4)
    c.setDash(4, 3)
    c.drawPath(p2)
    c.setDash()
    # legend above the plot, away from the curves
    c.setStrokeColor(INK)
    c.setLineWidth(1.4)
    c.line(left + 6, top - 4, left + 26, top - 4)
    _label(c, left + 30, top - 6, "训练时计算", size=7.2, color=INK)
    c.setStrokeColor(VERMILION)
    c.setLineWidth(1.4)
    c.setDash(4, 3)
    c.line(left + 6, top - 18, left + 26, top - 18)
    c.setDash()
    _label(c, left + 30, top - 20, "测试时计算", size=7.2, color=VERMILION)

FIGURES = {
    "timeline": (fig_timeline, 62 * mm),
    "turing": (fig_turing, 58 * mm),
    "perceptron": (fig_perceptron, 55 * mm),
    "winters": (fig_winters, 58 * mm),
    "alexnet": (fig_alexnet, 55 * mm),
    "rl": (fig_rl, 48 * mm),
    "transformer": (fig_transformer, 60 * mm),
    "rlhf": (fig_rlhf, 48 * mm),
    "scaling": (fig_scaling, 58 * mm),
}

def draw_figure(c, fig_id, w, h):
    fn, _ = FIGURES.get(fig_id, (None, None))
    if fn:
        fn(c, w, h)
    else:
        _frame(c, w, h)
        _label(c, w / 2, h / 2, f"[figure: {fig_id}]", align="center")

# ----------------------------------------------------------------------------
# Document
# ----------------------------------------------------------------------------
class BookDoc(BaseDocTemplate):
    def __init__(self, filename, **kw):
        super().__init__(filename, pagesize=(PAGE_W, PAGE_H), **kw)
        self.current_chapter = BOOK_TITLE
        self.chapter_start_page = 0
        self.page_offset = 0
        self._outline_rooted = False
    def handle_documentBegin(self):
        super().handle_documentBegin()
        self._outline_rooted = False
    def afterFlowable(self, flowable):
        if getattr(flowable, "_toc_kind", None) in ("chapter", "appendix"):
            self.current_chapter = flowable._toc_text
            self.chapter_start_page = self.page
        if hasattr(flowable, "_toc_level"):
            key = flowable._bookmark_key
            text = flowable._toc_text
            level = flowable._toc_level
            if level == 1 and not self._outline_rooted:
                self.canv.bookmarkPage("root")
                self.canv.addOutlineEntry(BOOK_TITLE, "root", 0, closed=False)
                self._outline_rooted = True
            elif level == 0:
                self._outline_rooted = True
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level, closed=False)
            self.notify("TOCEntry", (level, text, self.page, key))

def draw_paper(c, doc):
    c.saveState()
    c.setFillColor(PAPER)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    # subtle top rule
    c.setStrokeColor(HexColor("#E5E5E5"))
    c.setLineWidth(0.4)
    c.line(0, PAGE_H - 8 * mm, PAGE_W, PAGE_H - 8 * mm)
    c.restoreState()

def draw_front_footer(c, doc):
    page = c.getPageNumber()
    if page <= 5:
        return
    c.saveState()
    c.setFont("SS", 9)
    c.setFillColor(HexColor("#777777"))
    c.drawCentredString(PAGE_W / 2, 11 * mm, str(page))
    c.restoreState()

def draw_body_footer(c, doc):
    page = c.getPageNumber()
    c.saveState()
    if page != doc.chapter_start_page:
        c.setFont("YH", 8)
        c.setFillColor(HexColor("#555555"))
        if page % 2 == 0:
            header = BOOK_TITLE
            c.drawString(MARGIN_L, PAGE_H - 13.5 * mm, header)
        else:
            header = doc.current_chapter
            c.drawRightString(PAGE_W - MARGIN_R, PAGE_H - 13.5 * mm, header)
        c.setStrokeColor(HexColor("#DDDDDD"))
        c.setLineWidth(0.4)
        c.line(MARGIN_L, PAGE_H - 16 * mm, PAGE_W - MARGIN_R, PAGE_H - 16 * mm)
    c.setFont("SS", 9)
    c.setFillColor(HexColor("#777777"))
    c.drawCentredString(PAGE_W / 2, 11 * mm, str(page))
    c.restoreState()

def draw_cover(c, doc):
    c.saveState()
    # pure white background
    c.setFillColor(PAPER)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    # ring constellation, moved clear of the title for print legibility
    cx, cy, r = PAGE_W * 0.76, PAGE_H * 0.86, 22 * mm
    c.setStrokeColor(HexColor("#C9B18A"))
    c.setLineWidth(0.7)
    c.circle(cx, cy, r, fill=0, stroke=1)
    c.setStrokeColor(HexColor("#E5DED2"))
    c.setLineWidth(0.5)
    c.circle(cx, cy, r * 0.78, fill=0, stroke=1)
    c.circle(cx, cy, r * 0.52, fill=0, stroke=1)
    # radial ticks
    for k in range(48):
        a = k * math.pi * 2 / 48
        r1 = r * (0.80 if k % 4 else 0.72)
        r2 = r * (0.95 if k % 4 else 1.0)
        c.setStrokeColor(HexColor("#C9B18A"))
        c.setLineWidth(0.5 if k % 4 else 0.8)
        c.line(cx + r1 * math.cos(a), cy + r1 * math.sin(a), cx + r2 * math.cos(a), cy + r2 * math.sin(a))
    # constellation inside
    random.seed(23)
    pts = []
    for _ in range(20):
        a = random.random() * math.pi * 2
        rr = random.random() * r * 0.65
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            if math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]) < 18 * mm:
                c.setStrokeColor(HexColor("#DDD6C9"))
                c.setLineWidth(0.35)
                c.line(pts[i][0], pts[i][1], pts[j][0], pts[j][1])
    for x, y in pts:
        c.setFillColor(HexColor("#A9824E"))
        c.circle(x, y, 0.9, fill=1, stroke=0)
    # horizon line
    c.setStrokeColor(VERMILION)
    c.setLineWidth(0.9)
    c.line(0, PAGE_H * 0.305, PAGE_W, PAGE_H * 0.305)
    # left vertical rule
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.6)
    c.line(18 * mm, 24 * mm, 18 * mm, PAGE_H - 24 * mm)
    # title
    c.setFillColor(INK)
    c.setFont("YH-Bold", 37)
    c.drawString(24 * mm, PAGE_H - 72 * mm, "人工智能简史")
    c.setFillColor(VERMILION)
    c.setFont("SS-Italic", 16)
    c.drawString(24 * mm, PAGE_H - 88 * mm, "机器如何学会学习")
    c.setFillColor(GRAY)
    c.setFont("YH", 7.2)
    c.drawString(24 * mm, PAGE_H - 100 * mm, "A BRIEF HISTORY OF ARTIFICIAL INTELLIGENCE", charSpace=1.4)
    # small vertical line + text
    c.setFillColor(GRAY)
    c.setFont("SS", 8.5)
    c.drawString(24 * mm, PAGE_H - 122 * mm, "从达特茅斯的夏天，到智能体的黎明")
    # bottom
    c.setFillColor(GRAY)
    c.setFont("YH", 9)
    c.drawString(24 * mm, 26 * mm, AUTHOR)
    c.setFillColor(LIGHT_GRAY)
    c.setFont("YH", 7)
    c.drawString(24 * mm, 20 * mm, "OPEN SOURCE EDITION · 2026")
    c.restoreState()

def draw_back(c, doc):
    c.saveState()
    # pure white background
    c.setFillColor(PAPER)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    # small ring echo, clear of the text block
    cx, cy, r = PAGE_W * 0.82, PAGE_H * 0.86, 18 * mm
    c.setStrokeColor(HexColor("#E5DED2"))
    c.setLineWidth(0.5)
    c.circle(cx, cy, r, fill=0, stroke=1)
    c.setStrokeColor(HexColor("#C9B18A"))
    c.setLineWidth(0.5)
    c.circle(cx, cy, r * 0.70, fill=0, stroke=1)
    c.setFillColor(VERMILION)
    c.setFont("YH-Bold", 9)
    c.drawString(22 * mm, PAGE_H - 40 * mm, "人工智能简史", charSpace=2.5)
    c.setFillColor(INK)
    c.setFont("YH-Bold", 19)
    c.drawString(22 * mm, PAGE_H - 58 * mm, "机器如何学会学习")
    c.setFillColor(GRAY)
    c.setFont("SS-Italic", 12)
    c.drawString(22 * mm, PAGE_H - 72 * mm, "A BRIEF HISTORY OF ARTIFICIAL INTELLIGENCE")
    # blurb
    blurb = ("从图灵之问到 ChatGPT，从符号主义到深度学习，从专家系统到智能体——"
             "这是一部关于机器如何学会学习的历史，也是一部关于野心、失败、资本与选择的故事。"
             "它不预测终点，只提供更好的问题。")
    draw_wrapped(c, blurb, 22 * mm, PAGE_H - 98 * mm, PAGE_W - 44 * mm,
                 font="SS", size=10.2, leading=19, color=TEXT)
    # quote
    c.setStrokeColor(VERMILION)
    c.setLineWidth(1.2)
    c.line(22 * mm, PAGE_H - 150 * mm, 38 * mm, PAGE_H - 150 * mm)
    draw_wrapped(c, "“我们只能看到前方很短的距离，\n但我们可以看到，那里有很多事情需要去做。”",
                 22 * mm, PAGE_H - 160 * mm, PAGE_W - 44 * mm,
                 font="SS-Italic", size=10.5, leading=20, color=INK_LIGHT)
    c.setFillColor(GRAY)
    c.setFont("SS", 8.5)
    c.drawString(22 * mm, PAGE_H - 200 * mm, "——艾伦·图灵，1950")
    # repo
    c.setFillColor(GRAY)
    c.setFont("YH", 8)
    c.drawString(22 * mm, 28 * mm, "github.com/JackPeng-Coder/ai-brief-history")
    c.drawString(22 * mm, 22 * mm, "CC BY-NC-SA 4.0 · 非卖品 · 2026")
    c.restoreState()

# ----------------------------------------------------------------------------
# Markdown parsing
# ----------------------------------------------------------------------------
def is_special(line):
    s = line.strip()
    return (not s or s.startswith("#") or s.startswith("> ") or s.startswith(":::") or
            s.startswith("![fig:") or s.startswith("|") or s.startswith("- ") or s == "---" or
            re.match(r"^\d+\.\s", s) is not None)

def parse_blocks(path, skip_first_heading=True):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    blocks = []
    i = 0
    first_heading = True
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith("# "):
            if skip_first_heading and first_heading:
                first_heading = False
                i += 1
                continue
            first_heading = False
            blocks.append(("appendix", line[2:].strip()))
            i += 1
            continue
        if line.startswith("## "):
            blocks.append(("h2", line[3:].strip()))
            i += 1
            continue
        if line.startswith("### "):
            blocks.append(("h3", line[4:].strip()))
            i += 1
            continue
        if line.startswith("> "):
            buf = []
            while i < len(lines) and lines[i].startswith("> "):
                buf.append(lines[i][2:].strip())
                i += 1
            blocks.append(("quote", join_lines(buf)))
            continue
        if line.startswith("::: note"):
            title = line[len("::: note"):].strip()
            buf = []
            i += 1
            while i < len(lines) and lines[i].strip() != ":::":
                if lines[i].strip():
                    buf.append(lines[i].strip())
                i += 1
            i += 1
            blocks.append(("note", (title, buf)))
            continue
        if line.startswith("![fig:"):
            m = re.match(r"!\[fig:([^\]]+)\]\((.*)\)", line)
            if m:
                blocks.append(("figure", (m.group(1), m.group(2))))
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            blocks.append(("table", rows))
            continue
        if line.startswith("- "):
            items = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:])
                i += 1
            blocks.append(("bullets", items))
            continue
        if re.match(r"^\d+\.\s", line.strip()):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s", lines[i].strip()):
                m = re.match(r"^(\d+)\.\s+(.*)$", lines[i].strip())
                items.append((m.group(1), m.group(2)))
                i += 1
            blocks.append(("numbered", items))
            continue
        if line.strip() == "---":
            blocks.append(("scene", None))
            i += 1
            continue
        # paragraph
        buf = [line.strip()]
        i += 1
        while i < len(lines) and not is_special(lines[i]):
            buf.append(lines[i].strip())
            i += 1
        blocks.append(("p", join_lines(buf)))
    return blocks

def make_table(rows, col_widths=None):
    # remove separator row
    data = []
    header = None
    for r in rows:
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
            continue
        data.append(cells)
    if not data:
        return Spacer(1, 1)
    ncols = max(len(r) for r in data)
    data = [r + [""] * (ncols - len(r)) for r in data]
    header = data[0]
    body = data[1:]
    if col_widths is None:
        if ncols == 2:
            first = 45 * mm if header and header[0] == "人物" else 32 * mm
            col_widths = [first, CONTENT_W - first]
        elif ncols == 4 and header and header[0] == "模型":
            col_widths = [32 * mm, 22 * mm, 28 * mm, CONTENT_W - 82 * mm]
        else:
            col_widths = [CONTENT_W / ncols] * ncols
    compact = len(body) >= 20
    fs = 7.9 if compact else 8.3
    lead = 12.0 if compact else 13.2
    pad = 2.5 if compact else 4
    head_style = ParagraphStyle("TableHeadLocal", parent=S["table_head"], fontSize=fs + 0.1, leading=lead)
    body_style = ParagraphStyle("TableBodyLocal", parent=S["table"], fontSize=fs, leading=lead)
    table_data = [[Paragraph(inline(c), head_style) for c in header]]
    for r in body:
        table_data.append([Paragraph(inline(c), body_style) for c in r])
    t = LongTable(table_data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PAPER_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), INK),
        ("FONTNAME", (0, 0), (-1, 0), "YH-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "SS"),
        ("FONTSIZE", (0, 0), (-1, -1), fs),
        ("LEADING", (0, 0), (-1, -1), lead),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PAPER, HexColor("#F7F7F7")]),
        ("GRID", (0, 0), (-1, -1), 0.35, RULE),
    ]))
    if header and header[0] == "模型":
        cap = Paragraph("表 10-1 代表性大语言模型", S["caption"])
        return KeepTogether([cap, t])
    return t

def blocks_to_flowables(blocks, prefix="", toc_sections=False):
    out = []
    for kind, val in blocks:
        if kind == "p":
            out.append(P(val, "body"))
        elif kind == "h2":
            p = P(val, "h2")
            if toc_sections:
                p._toc_level = 2
                p._toc_text = val
                p._bookmark_key = "sec_" + hashlib.md5((prefix + "|" + val).encode("utf8")).hexdigest()[:10]
            out.append(p)
        elif kind == "h3":
            out.append(P(val, "h3"))
        elif kind == "quote":
            out.append(Spacer(1, 2))
            out.append(QuoteBlock(val))
            out.append(Spacer(1, 4))
        elif kind == "note":
            title, lines = val
            items = []
            buf = []
            for line in lines:
                m = re.match(r"^(\d+)\.\s+(.*)$", line)
                if m:
                    if buf:
                        items.append(("p", None, join_lines(buf))); buf = []
                    items.append(("num", m.group(1) + ".", m.group(2)))
                elif line.startswith("- "):
                    if buf:
                        items.append(("p", None, join_lines(buf))); buf = []
                    items.append(("bul", "·", line[2:]))
                else:
                    buf.append(line)
            if buf:
                items.append(("p", None, join_lines(buf)))
            out.append(Spacer(1, 5))
            out.append(NoteBox(title, items))
            out.append(Spacer(1, 7))
        elif kind == "figure":
            fig_id, caption = val
            _, fh = FIGURES.get(fig_id, (None, 55 * mm))
            out.append(Spacer(1, 4))
            out.append(Figure(fig_id, caption, height=fh))
            out.append(Spacer(1, 3))
        elif kind == "table":
            out.append(Spacer(1, 3))
            out.append(make_table(val))
            out.append(Spacer(1, 6))
        elif kind == "bullets":
            for item in val:
                out.append(Paragraph(inline(item), S["bullet"], bulletText="·"))
            out.append(Spacer(1, 3))
        elif kind == "numbered":
            for num, item in val:
                out.append(Paragraph(inline(item), S["number"], bulletText=f"{num}."))
            out.append(Spacer(1, 3))
        elif kind == "scene":
            out.append(SceneBreak())
        elif kind == "appendix":
            out.append(PageBreak())
            out.append(AppendixHeading(val))
    return out

# ----------------------------------------------------------------------------
# Metadata
# ----------------------------------------------------------------------------
PARTS = [
    dict(num="一", title="符号的雄心", years="远古—1974",
         epigraph="我们基于这样一个猜想：学习的每一个方面，或智能的任何其他特征，原则上都可以被如此精确地描述，以至于可以制造一台机器来模拟它。",
         source="——达特茅斯会议提案，1955",
         intro="第一次押注：符号。从神话到逻辑，从图灵机到达特茅斯，人类试图把智能写成规则。"),
    dict(num="二", title="知识的工程", years="1974—1993",
         epigraph="知识就是力量。",
         source="——弗朗西斯·培根",
         intro="这不是新的押注，而是符号押注的工程化极限：专家系统让 AI 第一次赚钱，也让人们看到规则的极限。"),
    dict(num="三", title="学习的胜利", years="1993—2017",
         epigraph="经验是最好的老师。",
         source="——谚语",
         intro="第二次押注：学习。数据、算力、算法汇合，机器从经验中学会感知和决策。"),
    dict(num="四", title="规模的信仰", years="2017—2026",
         epigraph="More is different.",
         source="——菲利普·安德森，1972",
         intro="第三次押注：规模；第四次押注——具身——正在发生。当规模本身成为方法，AI 从语言走向行动，也从实验室走向社会。"),
]

CHAPTERS = [
    dict(file="00-序章.md", part=None, label="序章", title="机器能思考吗？", subtitle="一个问题的四次押注",
         lead="从图灵的模仿游戏出发，看人工智能如何用四次押注回答同一个问题。"),
    dict(file="01-从神话到机器.md", part=0, label="第一章", title="从神话到机器", subtitle="智能的古老梦想",
         lead="在计算机出现之前，人类已经在用神话、机械和逻辑，预演人造智能。"),
    dict(file="02-计算的边界.md", part=0, label="第二章", title="计算的边界", subtitle="图灵、哥德尔与“会思考的机器”",
         lead="图灵机定义了可计算的世界，也给了人工智能一个起点。"),
    dict(file="03-达特茅斯的夏天.md", part=0, label="第三章", title="达特茅斯的夏天", subtitle="人工智能的诞生",
         lead="1956年的那个夏天，一群人给一个问题起了名字，也给它许下了过大的愿。"),
    dict(file="04-感知机的狂欢与第一次寒冬.md", part=0, label="第四章", title="感知机的狂欢与第一次寒冬", subtitle="一次过早的承诺",
         lead="机器第一次从数据中学习，却在期望的重压下摔得粉碎。"),
    dict(file="05-专家系统.md", part=1, label="第五章", title="专家系统", subtitle="把知识装进机器",
         lead="AI 第一次真正赚钱，也第一次发现知识的天花板。"),
    dict(file="06-寒冬再临与连接主义的暗流.md", part=1, label="第六章", title="寒冬再临与连接主义的暗流", subtitle="当规则遇到常识",
         lead="专家系统的黄金时代结束，神经网络在边缘处悄悄长大。"),
    dict(file="07-数据上场.md", part=2, label="第七章", title="数据上场", subtitle="从深蓝到互联网",
         lead="搜索、云计算、GPU 和 ImageNet，把 AI 从实验室推向数据海洋。"),
    dict(file="08-ImageNet时刻.md", part=2, label="第八章", title="ImageNet 时刻", subtitle="深度学习的三件套",
         lead="2012年，数据、算力、算法同时到位，感知的门被撞开。"),
    dict(file="09-从棋盘到现实.md", part=2, label="第九章", title="从棋盘到现实", subtitle="强化学习与决策智能",
         lead="AlphaGo 让世界看到，机器可以在封闭世界里超越人类；真实世界却复杂得多。"),
    dict(file="10-注意力革命.md", part=3, label="第十章", title="注意力革命", subtitle="Transformer 与大模型",
         lead="一篇论文改变了 AI 的进步方式：从为任务设计模型，到为规模训练系统。"),
    dict(file="11-ChatGPT时刻.md", part=3, label="第十一章", title="ChatGPT 时刻", subtitle="生成式 AI 走向大众",
         lead="一个输入框，把 AI 从实验室带进了亿万人的生活。"),
    dict(file="12-从回答到行动.md", part=3, label="第十二章", title="从回答到行动", subtitle="推理、智能体与具身智能",
         lead="当模型学会思考、调用工具、控制身体，AI 的边界从屏幕延伸到现实。"),
    dict(file="13-未完成的智能.md", part=3, label="第十三章", title="未完成的智能", subtitle="安全、伦理与人的位置",
         lead="能力越强，控制越难；智能的问题，最终是人的问题。"),
    dict(file="14-尾声.md", part=None, label="尾声", title="下一个达特茅斯", subtitle="历史不提供答案，只提供更好的问题",
         lead="站在2026年，回望七十年的热潮与寒冬，下一站会在哪里？"),
]

# ----------------------------------------------------------------------------
# Front matter
# ----------------------------------------------------------------------------
def front_matter():
    out = []
    # half title
    out.append(Spacer(1, 55 * mm))
    out.append(Paragraph("人工智能简史", S["front_title"]))
    out.append(Spacer(1, 10 * mm))
    out.append(Paragraph("机器如何学会学习", S["front_sub"]))
    out.append(Spacer(1, 8 * mm))
    out.append(Paragraph("A BRIEF HISTORY OF ARTIFICIAL INTELLIGENCE", S["front_small"]))
    out.append(PageBreak())
    # title page
    out.append(Spacer(1, 42 * mm))
    out.append(Paragraph("人工智能简史", S["front_title"]))
    out.append(Spacer(1, 7 * mm))
    out.append(Paragraph("机器如何学会学习", S["front_sub"]))
    out.append(Spacer(1, 6 * mm))
    out.append(Paragraph("A BRIEF HISTORY OF ARTIFICIAL INTELLIGENCE", S["front_small"]))
    out.append(Spacer(1, 35 * mm))
    out.append(Paragraph(AUTHOR, ParagraphStyle("a", fontName="YH", fontSize=10.5, leading=18, alignment=TA_CENTER, textColor=TEXT)))
    out.append(Spacer(1, 4 * mm))
    out.append(Paragraph(EDITION, S["front_small"]))
    out.append(Spacer(1, 3 * mm))
    out.append(Paragraph("OPEN SOURCE EDITION", S["front_small"]))
    out.append(PageBreak())
    # copyright
    out.append(Spacer(1, 40 * mm))
    out.append(Paragraph("人工智能简史：机器如何学会学习", ParagraphStyle("cp", fontName="YH-Bold", fontSize=13, leading=20, textColor=INK)))
    out.append(Spacer(1, 6 * mm))
    out.append(Paragraph(AUTHOR, S["body_noindent"]))
    out.append(Paragraph("2026年11月 · 第一版", S["body_noindent"]))
    out.append(Paragraph("开源科普项目 · 非卖品", S["body_noindent"]))
    out.append(Spacer(1, 8 * mm))
    out.append(Paragraph("本书文本采用 CC BY-NC-SA 4.0 许可协议发布：你可以自由复制、分发、改编，但需注明出处、不得用于商业目的，并以相同许可分享。书中的代码与排版脚本采用 MIT 许可。", S["body_small"]))
    out.append(Spacer(1, 3 * mm))
    out.append(Paragraph("本书由 AI 辅助完成研究与写作，经人工审校、编辑和排版。资料截至2026年11月。书中的观点、判断与错误由编者负责。", S["body_small"]))
    out.append(Spacer(1, 3 * mm))
    out.append(Paragraph("项目地址：https://github.com/JackPeng-Coder/ai-brief-history", S["body_small"]))
    out.append(PageBreak())
    # epigraph
    out.append(Spacer(1, 72 * mm))
    out.append(Paragraph("“我们只能看到前方很短的距离，但我们可以看到，那里有很多事情需要去做。”", ParagraphStyle("ep", fontName="SS-Italic", fontSize=14, leading=26, textColor=INK_LIGHT, alignment=TA_CENTER)))
    out.append(Spacer(1, 6 * mm))
    out.append(Paragraph("——艾伦·图灵，《计算机器与智能》，1950", S["front_small"]))
    out.append(PageBreak())
    return out

def toc_page():
    out = []
    out.append(Spacer(1, 6 * mm))
    out.append(Paragraph("目录", S["toc_title"]))
    out.append(Spacer(1, 2 * mm))
    out.append(Paragraph("CONTENTS", ParagraphStyle("ct", fontName="YH", fontSize=8, leading=12, textColor=GRAY)))
    out.append(Spacer(1, 8 * mm))
    toc = TableOfContents()
    toc.levelStyles = [S["toc_part"], S["toc_chapter"], S["toc_section"]]
    toc.dotsMinLevel = 0
    out.append(toc)
    return out

# ----------------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------------
def build():
    doc = BookDoc(PDF_PATH,
                  leftMargin=MARGIN_L, rightMargin=MARGIN_R,
                  topMargin=MARGIN_T, bottomMargin=MARGIN_B,
                  title="人工智能简史：机器如何学会学习",
                  author=AUTHOR,
                  subject="人工智能历史科普",
                  creator="ai-brief-history",
                  keywords="人工智能, AI, 历史, 科普, 大模型, 深度学习")
    cover_frame = Frame(0, 0, PAGE_W, PAGE_H, id="cover", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    front_frame = Frame(MARGIN_L, MARGIN_B, CONTENT_W, CONTENT_H, id="front", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    body_frame = Frame(MARGIN_L, MARGIN_B, CONTENT_W, CONTENT_H, id="body", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    part_frame = Frame(0, 0, PAGE_W, PAGE_H - 0.5, id="part", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    back_frame = Frame(0, 0, PAGE_W, PAGE_H, id="back", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], onPage=draw_cover),
        PageTemplate(id="front", frames=[front_frame], onPage=draw_paper, onPageEnd=draw_front_footer),
        PageTemplate(id="body", frames=[body_frame], onPage=draw_paper, onPageEnd=draw_body_footer),
        PageTemplate(id="part", frames=[part_frame]),
        PageTemplate(id="back", frames=[back_frame], onPage=draw_back),
    ])

    story = []
    # cover (first page uses the first template)
    story.append(Spacer(1, 1))
    story.append(NextPageTemplate("front"))
    story.append(PageBreak())
    story.extend(front_matter())
    story.append(NextPageTemplate("front"))
    story.extend(toc_page())
    story.append(NextPageTemplate("body"))

    current_part = None
    for ch in CHAPTERS:
        # part divider
        if ch["part"] is not None and ch["part"] != current_part:
            current_part = ch["part"]
            part = PARTS[current_part]
            story.append(NextPageTemplate("part"))
            story.append(PageBreak())
            story.append(PartDivider(part["num"], part["title"], part["years"],
                                     part["epigraph"], part["source"], part["intro"]))
            story.append(NextPageTemplate("body"))
            story.append(PageBreak())
        else:
            # normal chapter: start on a new page (no double break after a part divider)
            story.append(PageBreak())
        # chapter
        story.append(ChapterOpener(ch["label"], ch["title"], ch["subtitle"], ch["lead"]))
        blocks = parse_blocks(os.path.join(CONTENT, ch["file"]), skip_first_heading=True)
        story.extend(blocks_to_flowables(blocks, prefix=ch["label"]))

    # appendices
    story.append(NextPageTemplate("part"))
    story.append(PageBreak())
    story.append(PartDivider("附", "附录与延伸", "年表 · 人物 · 术语 · 阅读",
                             "历史不会重复，但它会押韵。",
                             "——编者", "给想继续探索的读者：一份年表、一份人物谱、一份术语表，以及一条更长的阅读路径。"))
    story.append(NextPageTemplate("body"))
    story.append(PageBreak())
    story.append(AppendixHeading("附录 A 人工智能大事年表"))
    blocks = parse_blocks(os.path.join(CONTENT, "15-附录.md"), skip_first_heading=True)
    # skip the first appendix heading in the file (we already added it)
    if blocks and blocks[0][0] == "appendix" and "大事年表" in blocks[0][1]:
        blocks = blocks[1:]
    story.extend(blocks_to_flowables(blocks, prefix="附录", toc_sections=True))

    # back cover
    story.append(NextPageTemplate("back"))
    story.append(PageBreak())
    story.append(Spacer(1, 1))

    doc.multiBuild(story)
    print("Wrote", PDF_PATH)

if __name__ == "__main__":
    build()
