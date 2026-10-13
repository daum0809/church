"""성경 본문 찾기.

성경 본문(개역개정)은 저작권 때문에 함께 넣지 않았습니다.
data/bible/ 폴더에 성경 텍스트 파일(.txt, UTF-8)을 넣어 두면 자동으로 찾아 씁니다.
한 줄에 한 절, 다음 형식 중 아무거나 됩니다:
    누가복음 10:36 네 생각에는 ...
    눅10:36 네 생각에는 ...
    [눅 10:36] 네 생각에는 ...
"""

import re
from pathlib import Path

from .paths import DATA

BIBLE_DIR = DATA / "bible"

BOOKS = [
    ("창세기", "창"), ("출애굽기", "출"), ("레위기", "레"), ("민수기", "민"), ("신명기", "신"),
    ("여호수아", "수"), ("사사기", "삿"), ("룻기", "룻"), ("사무엘상", "삼상"), ("사무엘하", "삼하"),
    ("열왕기상", "왕상"), ("열왕기하", "왕하"), ("역대상", "대상"), ("역대하", "대하"), ("에스라", "스"),
    ("느헤미야", "느"), ("에스더", "에"), ("욥기", "욥"), ("시편", "시"), ("잠언", "잠"),
    ("전도서", "전"), ("아가", "아"), ("이사야", "사"), ("예레미야", "렘"), ("예레미야애가", "애"),
    ("에스겔", "겔"), ("다니엘", "단"), ("호세아", "호"), ("요엘", "욜"), ("아모스", "암"),
    ("오바댜", "옵"), ("요나", "욘"), ("미가", "미"), ("나훔", "나"), ("하박국", "합"),
    ("스바냐", "습"), ("학개", "학"), ("스가랴", "슥"), ("말라기", "말"),
    ("마태복음", "마"), ("마가복음", "막"), ("누가복음", "눅"), ("요한복음", "요"), ("사도행전", "행"),
    ("로마서", "롬"), ("고린도전서", "고전"), ("고린도후서", "고후"), ("갈라디아서", "갈"),
    ("에베소서", "엡"), ("빌립보서", "빌"), ("골로새서", "골"), ("데살로니가전서", "살전"),
    ("데살로니가후서", "살후"), ("디모데전서", "딤전"), ("디모데후서", "딤후"), ("디도서", "딛"),
    ("빌레몬서", "몬"), ("히브리서", "히"), ("야고보서", "약"), ("베드로전서", "벧전"),
    ("베드로후서", "벧후"), ("요한일서", "요일"), ("요한이서", "요이"), ("요한삼서", "요삼"),
    ("유다서", "유"), ("요한계시록", "계"),
]
_ALIASES = {"룻": "룻기", "요한1서": "요한일서", "요한2서": "요한이서", "요한3서": "요한삼서", "요한계시록": "요한계시록", "계시록": "요한계시록", "시": "시편", "아가서": "아가",
            "예레미야 애가": "예레미야애가"}
NAMES = {}
for full, short in BOOKS:
    NAMES[full] = full
    NAMES[short] = full
NAMES.update(_ALIASES)
# 긴 이름부터 맞춰야 '요한일서'가 '요'로 잘리지 않습니다.
_BOOK_RE = "|".join(sorted(map(re.escape, NAMES), key=len, reverse=True))

REF_RE = re.compile(
    rf"({_BOOK_RE})\s*(\d+)\s*(?:[:：]|장\s*)\s*(\d+)(?:\s*절)?(?:\s*[-~∼〜–]\s*(?:(\d+)\s*[:：]\s*)?(\d+))?\s*절?")


def find_ref(text):
    """'누가복음 10:36~37', '눅 10장 36-37절' 등을 찾아 (책, 장, 시작절, 끝장, 끝절, 원문) 으로."""
    m = REF_RE.search(text or "")
    if not m:
        return None
    book, ch, v1, ch2, v2 = m.groups()
    ch, v1 = int(ch), int(v1)
    ch2 = int(ch2) if ch2 else ch
    v2 = int(v2) if v2 else (v1 if ch2 == ch else v1)
    return NAMES[book], ch, v1, ch2, v2, m.group(0)


def format_ref(ref):
    book, ch, v1, ch2, v2, _ = ref
    if ch2 != ch:
        return f"{book} {ch}:{v1}~{ch2}:{v2}절"
    return f"{book} {ch}:{v1}절" if v1 == v2 else f"{book} {ch}:{v1}~{v2}절"


_LINE_RE = re.compile(rf"^\s*\[?\s*({_BOOK_RE})\s*(\d+)\s*[:：]\s*(\d+)\s*\]?\s*(.+?)\s*$")
_cache = None


def _load():
    global _cache
    if _cache is None:
        _cache = {}
        if BIBLE_DIR.exists():
            for f in sorted(BIBLE_DIR.glob("*.txt")):
                for enc in ("utf-8-sig", "cp949"):
                    try:
                        text = f.read_text(encoding=enc)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    continue
                for line in text.splitlines():
                    m = _LINE_RE.match(line)
                    if m:
                        b, c, v, t = m.groups()
                        _cache.setdefault((NAMES[b], int(c), int(v)), t)
    return _cache


def verses(ref):
    """'36 네 생각에는...' 형식의 줄들. 성경 파일이 없거나 못 찾으면 빈 문자열."""
    book, ch, v1, ch2, v2, _ = ref
    data = _load()
    out = []
    c, v = ch, v1
    while (c, v) <= (ch2, v2):
        text = data.get((book, c, v))
        if text is None:
            if (book, c + 1, 1) in data and c < ch2:
                c, v = c + 1, 1
                continue
            return ""
        out.append(f"{v} {text}")
        v += 1
    return "\n".join(out)
