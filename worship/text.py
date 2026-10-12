"""글꼴 찾기와 원본 글자를 지우고 새 글자를 같은 자리에 쓰는 도구."""

import os
import re
import sys
from pathlib import Path

import pymupdf

from .paths import FONTS, HOME

FALLBACK_FONT = FONTS / "Pretendard-Regular.ttf"
BOLD_FONT = FONTS / "Pretendard-SemiBold.ttf"


def _font_dirs():
    if sys.platform.startswith("win"):
        yield Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        local = os.environ.get("LOCALAPPDATA")
        if local:
            yield Path(local) / "Microsoft" / "Windows" / "Fonts"
    elif sys.platform == "darwin":
        yield Path.home() / "Library" / "Fonts"
        yield Path("/Library/Fonts")
    else:
        yield Path.home() / ".fonts"
        yield Path.home() / ".local" / "share" / "fonts"
        yield Path("/usr/share/fonts")


def find_font(preferred=None):
    """원본 디자인 글꼴(TT옴니고딕)이 설치돼 있으면 그것을, 없으면 Pretendard 를 씁니다."""
    if preferred:
        path = Path(preferred)
        if not path.is_absolute():
            path = HOME / path
        if path.exists():
            return path
        print(f"[경고] 지정한 글꼴을 찾을 수 없습니다: {preferred}")
    for folder in _font_dirs():
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if path.suffix.lower() in (".ttf", ".otf") and "omni" in path.name.lower():
                try:
                    if "OmniGothic" in pymupdf.Font(fontfile=str(path)).name.replace(" ", ""):
                        return path
                except Exception:
                    continue
    return FALLBACK_FONT


class Writer:
    """한 글꼴로 페이지에 글자를 쓰고 폭을 계산합니다."""

    def __init__(self, font_path):
        self.font_path = str(font_path)
        self.font = pymupdf.Font(fontfile=self.font_path)
        self.fontname = "w" + re.sub(r"[^A-Za-z0-9]", "", Path(font_path).stem)[:20]
        # 템플릿의 글자 크기는 TT옴니고딕 기준입니다. 다른 글꼴이면 한글 높이와
        # 아랫선이 같아지도록 크기를 키우고 기준선을 내립니다.
        if "OmniGothic" in self.font.name.replace(" ", ""):
            self.scale, self.drop = 1.0, 0.0
        else:
            self.scale, self.drop = 1.056, 0.069

    def width(self, text, size):
        return self.font.text_length(text, fontsize=size * self.scale)

    def fit_size(self, text, size, max_width):
        w = self.width(text, size)
        return size if w <= max_width or w == 0 else size * max_width / w

    def write(self, page, text, x, baseline, size, color, align="left", max_width=None, opacity=1.0):
        """align: left 이면 x 가 왼쪽 끝, center 면 가운데, right 면 오른쪽 끝."""
        if not text:
            return
        if max_width:
            size = self.fit_size(text, size, max_width)
        w = self.width(text, size)
        if align == "center":
            x -= w / 2
        elif align == "right":
            x -= w
        page.insert_font(fontname=self.fontname, fontfile=self.font_path)
        page.insert_text((x, baseline + size * self.drop), text, fontname=self.fontname,
                         fontsize=size * self.scale,
                         color=color, fill_opacity=opacity)

    def wrap(self, text, size, max_width):
        """띄어쓰기 단위로 줄바꿈 (한 단어가 너무 길면 글자 단위)."""
        lines, cur = [], ""
        for word in text.split():
            cand = f"{cur} {word}" if cur else word
            if self.width(cand, size) <= max_width:
                cur = cand
                continue
            if cur:
                lines.append(cur)
            cur = ""
            for ch in word:
                if self.width(cur + ch, size) > max_width and cur:
                    lines.append(cur)
                    cur = ""
                cur += ch
        if cur:
            lines.append(cur)
        return lines


def spans(page):
    """페이지의 글자 묶음(span) 목록."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for s in line["spans"]:
                if s["text"].strip():
                    out.append(s)
    return out


def find_span(page, contains):
    key = contains.replace(" ", "")
    for s in spans(page):
        if key in s["text"].replace(" ", ""):
            return s
    raise LookupError(f"템플릿 {page.number + 1}쪽에서 '{contains}' 글자를 찾지 못했습니다.")


def rgb(color_int):
    return ((color_int >> 16) & 255) / 255, ((color_int >> 8) & 255) / 255, (color_int & 255) / 255


def erase(page, rects, vector_text=False):
    """rects 안의 글자만 지웁니다 (배경 사진·선은 그대로).

    vector_text=True 이면 글자가 도형(벡터)으로 그려진 경우도, 영역 안에 완전히
    들어있는 도형에 한해 함께 지웁니다.
    """
    for r in rects:
        r = pymupdf.Rect(r)
        # 이웃한 글자를 건드리지 않도록 살짝 안쪽으로
        page.add_redact_annot(r + (1, 2, -1, -2), fill=False)
    graphics = (pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED if vector_text
                else pymupdf.PDF_REDACT_LINE_ART_NONE)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=graphics,
                          text=pymupdf.PDF_REDACT_TEXT_REMOVE)
