"""weekly.yaml 내용을 받아 예배 PDF 를 만듭니다."""

import datetime as dt
import re
from pathlib import Path

import pymupdf
import yaml

from . import hymns, layout, memory
from .text import BOLD_FONT, Writer, erase, find_font, find_span, rgb

ROOT = Path(__file__).resolve().parent.parent
BASE_PDF = ROOT / "templates" / "base.pdf"

WHITE = (1, 1, 1)
YELLOW = (1, 1, 0)
LABEL = rgb(0xF3F1EE)      # 찬송가 번호 상자 글자색
SUBTLE = rgb(0x9C958E)     # 직분 글자색
DARK = rgb(0x333333)


class InputError(Exception):
    pass


# ------------------------------------------------------------------ 입력

def load_input(path):
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def _get(data, *keys, default=None):
    cur = data
    for k in keys:
        if not isinstance(cur, dict) or cur.get(k) in (None, ""):
            return default
        cur = cur[k]
    return cur


def _sunday(value):
    if isinstance(value, dt.date):
        return value
    if value:
        m = re.match(r"\s*(\d{2,4})\D+(\d{1,2})\D+(\d{1,2})", str(value))
        if not m:
            raise InputError(f"날짜 형식을 알 수 없습니다: {value} (예: 2026-10-18)")
        y, mo, d = (int(x) for x in m.groups())
        return dt.date(y + 2000 if y < 100 else y, mo, d)
    today = dt.date.today()
    return today + dt.timedelta(days=(6 - today.weekday()) % 7)


def _hymn(data, key):
    """장 번호가 비어 있으면 None (번호 칸을 비우고 악보는 건너뜀)."""
    item = data.get(key) or {}
    if not isinstance(item, dict):
        item = {}
    title = str(item.get("제목") or "").strip()
    if not item.get("장") and not title:
        raise InputError(f"'{key}' 의 장 번호나 제목을 입력해 주세요.")
    return (int(item["장"]) if item.get("장") else None), title, item


def parse_reading(text):
    """교독문: '인도:', '회중:', '다같이:' 로 시작하는 줄. 표시가 없으면 인도/회중 번갈아."""
    parts, turn = [], 0
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(인도|사회|회중|다같이|다 같이)\s*[:：)]\s*(.*)$", line)
        if m:
            who = {"사회": "인도", "다 같이": "다같이"}.get(m.group(1), m.group(1))
            parts.append((who, m.group(2).strip()))
        else:
            parts.append(("인도" if turn % 2 == 0 else "회중", line))
        turn = 0 if parts[-1][0] in ("회중", "다같이") else 1
    slides, i = [], 0
    while i < len(parts):
        who, line = parts[i]
        if who == "인도" and i + 1 < len(parts) and parts[i + 1][0] == "회중":
            slides.append([parts[i], parts[i + 1]])
            i += 2
        else:
            slides.append([parts[i]])
            i += 1
    return slides


def parse_verses(text):
    """성경 본문: 줄 앞의 숫자를 절 번호로 봅니다. 번호 없는 줄은 앞 절에 이어 붙입니다."""
    verses = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(\d+)\s*(.*)$", line)
        if m or not verses:
            verses.append([m.group(1) if m else "", (m.group(2) if m else line)])
        else:
            verses[-1][1] += " " + line
    return verses


# ------------------------------------------------------------------ 페이지 만들기

class Builder:
    def __init__(self, font_path, log=print):
        self.base = pymupdf.open(BASE_PDF)
        self.out = pymupdf.open()
        self.w = Writer(font_path)
        self.bold = Writer(BOLD_FONT)
        self.log = log
        self.missing = []
        hymns.seed_from_template(self.base)

    def copy(self, index):
        self.out.insert_pdf(self.base, from_page=index, to_page=index)
        return self.out[-1]

    def copy_fixed(self, indexes):
        for i in indexes:
            self.copy(i)

    def sheets(self, num):
        if num is None:
            self.missing.append("장 번호가 없는 찬송은 악보를 넣지 못했습니다. weekly.yaml 에 장 번호를 입력해 주세요.")
            return
        try:
            doc = hymns.get_hymn(num, self.log)
        except hymns.HymnError as e:
            self.missing.append(str(e))
            self.log(f"  [건너뜀] 찬송가 {num}장 악보 없음")
            return
        with doc:
            self.out.insert_pdf(doc)

    # 표지 ---------------------------------------------------------
    def cover(self, date):
        page = self.copy(layout.COVER)
        # 날짜는 글자가 아니라 도형으로 그려져 있어 영역째 지웁니다.
        erase(page, [(90, 60, 215, 98)], vector_text=True)
        text = f"{date.year % 100:02d}. {date.month:02d}. {date.day:02d}"
        self.w.write(page, text, 102, 90, 29, DARK)

    # 찬송 제목 (입례/영광송/찬송/봉헌) --------------------------------
    def hymn_title(self, index, num, title):
        page = self.copy(index)
        label = find_span(page, "장")
        name = max((s for s in _spans_white(page)), key=lambda s: s["size"])
        erase(page, [label["bbox"], name["bbox"]])
        lb, nb = pymupdf.Rect(label["bbox"]), pymupdf.Rect(name["bbox"])
        self.w.write(page, f"찬송가 {num}장" if num else "찬송가", (lb.x0 + lb.x1) / 2, label["origin"][1],
                     label["size"], LABEL, align="center", max_width=390)
        self.w.write(page, title, 720, name["origin"][1], name["size"], WHITE,
                     align="center", max_width=1300)

    # 교독 -----------------------------------------------------------
    def reading(self, title, body):
        page = self.copy(layout.READING_TITLE)
        s = find_span(page, "편")
        erase(page, [s["bbox"]])
        self.w.write(page, title, 720, s["origin"][1], s["size"], WHITE, align="center", max_width=1300)

        for slide in parse_reading(body):
            page = self.copy(layout.READING_SLIDE)
            erase(page, [(40, 200, 1400, 770)])
            if len(slide) == 1:
                who, line = slide[0]
                color, size = (WHITE, 60) if who == "인도" else (YELLOW, 72)
                self._block(page, line, size, color, center_y=470, max_lines=6)
            else:
                self._block(page, slide[0][1], 60, WHITE, center_y=318, max_lines=3)
                self._block(page, slide[1][1], 72, YELLOW, center_y=578, max_lines=3)

    def _block(self, page, text, size, color, center_y, max_lines, width=1230):
        lines = self.w.wrap(text, size, width)
        while len(lines) > max_lines and size > 30:
            size -= 2
            lines = self.w.wrap(text, size, width)
        step = size * 1.23
        first = center_y - (len(lines) - 1) * step / 2 + size * 0.36
        for i, line in enumerate(lines):
            self.w.write(page, line, 722, first + i * step, size, color, align="center")

    # 대표기도 ---------------------------------------------------------
    def prayer(self, name, role):
        page = self.copy(layout.PRAYER)
        n, r = find_span(page, "김도연"), find_span(page, "안수집사")
        erase(page, [n["bbox"], r["bbox"]])
        self._name_group(page, name, role, n, r, center=(n["bbox"][0] + r["bbox"][2]) / 2,
                         name_color=DARK, role_color=SUBTLE)

    def _name_group(self, page, name, role, n, r, name_color, role_color, center=None, right=None):
        gap = r["bbox"][0] - n["bbox"][2]
        wn, wr = self.w.width(name, n["size"]), self.w.width(role, r["size"]) if role else 0
        total = wn + (gap + wr if role else 0)
        x = right - total if right is not None else center - total / 2
        self.w.write(page, name, x, n["origin"][1], n["size"], name_color)
        if role:
            self.w.write(page, role, x + wn + gap, r["origin"][1], r["size"], role_color)

    # 성경봉독 ---------------------------------------------------------
    def scripture(self, reader, ref, body, amen):
        page = self.copy(layout.SCRIPTURE_TITLE)
        rd, rf = find_span(page, "권사"), find_span(page, "절")
        erase(page, [rd["bbox"], rf["bbox"]])
        rb = pymupdf.Rect(rd["bbox"])
        self.w.write(page, reader, (rb.x0 + rb.x1) / 2, rd["origin"][1], rd["size"], LABEL,
                     align="center", max_width=520)
        self.w.write(page, ref, 720, rf["origin"][1], rf["size"], WHITE, align="center", max_width=1300)

        verses = parse_verses(body)
        if amen and verses and "아멘" not in verses[-1][1][-12:]:
            verses[-1][1] = verses[-1][1].rstrip() + " (다같이) 아멘."
        for num, text in verses:
            lines = self.w.wrap(num + text, 60, 1290)
            for chunk in [lines[i:i + 5] for i in range(0, len(lines), 5)] or [[]]:
                page = self.copy(layout.SCRIPTURE_SLIDE)
                head = find_span(page, "절")
                erase(page, [head["bbox"], (40, 205, 1400, 770)])
                self.w.write(page, ref, head["bbox"][2], head["origin"][1], head["size"],
                             rgb(head["color"]), align="right", max_width=520)
                for i, line in enumerate(chunk):
                    self.w.write(page, line, 77, 296.5 + i * 109.6, 60, WHITE)

    # 찬양 (성가대) -----------------------------------------------------
    def anthem(self, choir, title, composer, lyrics):
        page = self.copy(layout.ANTHEM)
        c = find_span(page, "성가대")
        t = find_span(page, "은혜")
        # 작곡자 글자는 '글자 모양 마스크를 씌운 작은 색 이미지'라서 마스크를 비웁니다.
        for img in page.get_images(full=True):
            xref, width = img[0], img[2]
            if width <= 4 and any(r.y0 > 600 for r in page.get_image_rects(xref)):
                _clear_smask(self.out, xref)
        erase(page, [c["bbox"], t["bbox"], (600, 625, 840, 682)])
        erase(page, [(480, 686, 960, 745)], vector_text=True)
        cb = pymupdf.Rect(c["bbox"])
        self.w.write(page, choir, (cb.x0 + cb.x1) / 2, c["origin"][1], c["size"], LABEL,
                     align="center", max_width=390)
        self.w.write(page, title, 720, t["origin"][1], t["size"], WHITE, align="center", max_width=1300)
        self.w.write(page, composer, 720, 667, 34, LABEL, align="center", max_width=900)
        lines = [l.strip() for l in str(lyrics or "").splitlines() if l.strip()][:2]
        for i, line in enumerate(lines):
            self.w.write(page, line, 720, 706 + i * 30.5, 21.5, LABEL, align="center",
                         max_width=1200, opacity=0.69)

    # 말씀선포 ---------------------------------------------------------
    def sermon(self, title, ref, preacher, role):
        page = self.copy(layout.SERMON)
        t, rf = find_span(page, "기후위기"), find_span(page, "절")
        n, r = find_span(page, "이택규"), find_span(page, "목사")
        erase(page, [t["bbox"], rf["bbox"], n["bbox"], r["bbox"]])
        if title and not title.startswith(("\"", "“")):
            title = f"\"{title}\""
        size, color, base = t["size"], rgb(t["color"]), t["origin"][1]
        if self.w.fit_size(title, size, 1300) >= size * 0.75:
            self.w.write(page, title, 720, base, size, color, align="center", max_width=1300)
        else:  # 너무 길면 두 줄로
            size *= 0.8
            lines = self.w.wrap(title, size, 1300)
            lines = lines[:1] + [" ".join(lines[1:])]
            for i, line in enumerate(lines):
                self.w.write(page, line, 720, base - size * 0.9 + i * size * 1.2, size, color,
                             align="center", max_width=1300)
        self.w.write(page, ref, 720, rf["origin"][1], rf["size"], SUBTLE, align="center")
        self._name_group(page, preacher, role, n, r, right=r["bbox"][2],
                         name_color=DARK, role_color=SUBTLE)

    # 교회소식 ---------------------------------------------------------
    def news(self, text):
        """한 줄 = 한 항목 ('  - ' 로 시작하면 하위 항목). 넘치면 여러 화면으로.

        글자를 조금 줄여서 화면 수가 줄어들면 줄인 크기를 씁니다.
        """
        items = [l.rstrip() for l in str(text or "").splitlines() if l.strip()]
        if not items:
            self.copy(layout.NEWS)
            return
        best = None
        for scale in (1.0, 0.94, 0.88):
            pages = self._news_pages(items, scale)
            if best is None or len(pages) < len(best):
                best = pages
        right = 1340
        for n, blocks_on_page in enumerate(best, 1):
            page = self.copy(layout.NEWS)
            for img in page.get_images(full=True):
                if img[2] <= 4:
                    _clear_smask(self.out, img[0])
            erase(page, [(36, 205, 1405, 775)])
            y = 262
            for block in blocks_on_page:
                for x, line, size, color in block:
                    self.bold.write(page, line, x, y, size, color, max_width=right - x)
                    y += size * 1.55
                y += 10
            if len(best) > 1:
                self.w.write(page, f"{n} / {len(best)}", 1385, 765, 22, (0.65, 0.64, 0.62), align="right")

    def _news_pages(self, items, scale):
        left, right, room = 120, 1340, 748 - 262
        groups = []  # 항목(+하위 항목)마다 [블록], 블록 = [(x, 글자, 크기, 색)]
        for item in items:
            sub = item.startswith((" ", "\t", "-"))
            body = item.strip().lstrip("-").strip() if sub else item.strip()
            size = (31 if sub else 34) * scale
            color = (0.86, 0.85, 0.83) if sub else WHITE
            if sub:
                prefix, x0 = "- ", left + 40
            else:
                m = re.match(r"^(\d{1,2}\.\s*)", body)
                prefix, x0 = (m.group(1), left) if m else ("", left)
                body = body[len(prefix):]
            indent = self.bold.width(prefix, size)
            lines = self.bold.wrap(body, size, right - x0 - indent) or [""]
            block = [(x0, prefix + lines[0], size, color)]
            block += [(x0 + indent, l, size, color) for l in lines[1:]]
            if sub and groups:
                groups[-1].append(block)  # 하위 항목은 위 항목과 같은 화면에
            else:
                groups.append([block])

        height = lambda block: sum(b[2] * 1.55 for b in block) + 10
        pages, cur, used = [], [], 0
        for group in groups:
            h = sum(height(b) for b in group)
            units = [group] if h <= room else [[b] for b in group]
            for unit in units:
                h = sum(height(b) for b in unit)
                if cur and used + h > room:
                    pages.append(cur)
                    cur, used = [], 0
                cur.extend(unit)
                used += h
        if cur:
            pages.append(cur)
        return pages

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.out.subset_fonts()
        self.out.save(path, garbage=3, deflate=True)
        return path


def _clear_smask(doc, xref):
    kind, value = doc.xref_get_key(xref, "SMask")
    if kind != "xref":
        return
    mask = int(value.split()[0])
    w = int(doc.xref_get_key(mask, "Width")[1])
    h = int(doc.xref_get_key(mask, "Height")[1])
    doc.xref_set_key(mask, "Filter", "null")
    doc.xref_set_key(mask, "DecodeParms", "null")
    doc.xref_set_key(mask, "BitsPerComponent", "8")
    doc.update_stream(mask, bytes(w * h), compress=False)


def _spans_white(page):
    from .text import spans
    return [s for s in spans(page) if s["color"] == 0xFFFFFF]


# ------------------------------------------------------------------ 전체 순서

def build(input_path, output=None, log=print):
    return build_data(load_input(input_path), output, log)


def build_data(data, output=None, log=print):
    settings = data.get("설정") or {}
    font = find_font(settings.get("글꼴"))
    log(f"글꼴: {Path(font).name}")
    date = _sunday(data.get("날짜"))

    b = Builder(font, log)
    log("표지 / 입례 찬송")
    b.cover(date)
    num, title, item = _hymn(data, "입례찬송")
    b.hymn_title(layout.ENTRANCE_TITLE, num, title)
    if item.get("악보"):
        b.sheets(num)
    b.copy_fixed(layout.CREED)

    log("영광송")
    num, title, _ = _hymn(data, "영광송")
    b.hymn_title(layout.GLORIA_TITLE, num, title)
    b.sheets(num)

    log("교독 (공동기도)")
    b.reading(str(_get(data, "교독", "제목", default="")), _get(data, "교독", "본문", default=""))

    log("찬송")
    num, title, _ = _hymn(data, "찬송")
    b.hymn_title(layout.HYMN_TITLE, num, title)
    b.sheets(num)

    log("대표기도")
    b.prayer(str(_get(data, "대표기도", "이름", default="")), str(_get(data, "대표기도", "직분", default="")))

    log("성경봉독")
    ref = str(_get(data, "성경봉독", "본문", default=""))
    b.scripture(str(_get(data, "성경봉독", "봉독자", default="")), ref,
                _get(data, "성경봉독", "말씀", default=""),
                bool(_get(data, "성경봉독", "마지막에_아멘", default=True)))
    b.copy_fixed([layout.RESPONSE])

    log("찬양 / 말씀선포")
    b.anthem(str(_get(data, "찬양", "성가대", default="")), str(_get(data, "찬양", "곡명", default="")),
             str(_get(data, "찬양", "작곡", default="")), _get(data, "찬양", "가사", default=""))
    b.sermon(str(_get(data, "말씀", "제목", default="")), str(_get(data, "말씀", "본문", default=ref)),
             str(_get(data, "말씀", "설교자", default="")), str(_get(data, "말씀", "직분", default="")))
    b.copy_fixed([layout.BLANK])

    log("봉헌 / 마침")
    num, title, _ = _hymn(data, "봉헌찬송")
    b.hymn_title(layout.OFFERTORY_TITLE, num, title)
    b.sheets(num)
    b.copy_fixed([layout.OFFERTORY_PRAYER])
    log("교회소식")
    b.news(data.get("교회소식"))
    b.copy_fixed(layout.CLOSING)

    if output is None:
        folder = Path(settings.get("출력폴더") or "output")
        if not folder.is_absolute():
            folder = ROOT / folder
        output = folder / f"주일예배_{date:%Y-%m-%d}.pdf"
    path = b.save(output)
    memory.learn(data)
    if b.missing:
        log("\n[주의] 악보가 빠진 찬송이 있습니다. 악보 파일을 넣고 다시 만들어 주세요.")
        for msg in b.missing:
            log("  " + msg.replace("\n", "\n  "))
    log(f"완성: {path}  ({len(b.out)}쪽)")
    return path
