"""주보(한글 문서) 글자에서 예배 순서를 읽어 weekly.yaml 과 같은 내용을 만듭니다.

주보마다 모양이 달라서 '순서 이름'을 기준으로 찾습니다.
  ※입례찬송   '기뻐하며 경배하세'   반 주 자
  ※교   독    16.시편 28편          다 같 이
  (교독문 본문 줄들 …)
  기   도      유은정 안수집사
  ※성경봉독    김종석 집사
  요엘 2:21∼27절
  21땅이여 … 22들짐승들아 …
점선(……)으로 이어진 주보, 표(순서|내용|담당) 형식 주보 모두 됩니다.
같은 순서 이름이 주보의 다른 곳(예배위원 표, 예배 안내 등)에 또 나오면
예배 순서 목록 안에 있는 것을 고릅니다.
"""

import datetime as dt
import re

from . import bible, memory

# 순서 이름 (띄어쓰기 무시)
LABELS = {
    "입례찬송": ["입례찬송", "예배찬송", "경배찬송", "개회찬송"],
    "영광송": ["영광송"],
    "교독": ["교독문", "성시교독", "교독", "공동기도"],
    "봉헌찬송": ["봉헌찬송", "헌금찬송", "봉헌"],
    "찬송": ["찬송"],
    "대표기도": ["대표기도", "기도"],
    "성경봉독": ["성경봉독", "말씀봉독", "봉독", "성경"],
    "찬양": ["성가대찬양", "특별찬양", "찬양", "성가"],
    "말씀": ["말씀선포", "설교", "말씀"],
}
# 값 모으기를 멈추는 다른 순서 이름들
STOP = ["예배로부름", "예배의부름", "예배에의부름", "송영", "묵도", "기원", "신앙고백", "사도신경", "참회기도",
        "응답송", "응답찬송", "봉헌기도", "주기도문", "주의기도", "주기도", "축도", "광고", "교회소식", "환영",
        "파송", "후주", "전주", "목회기도", "결단찬송", "파송찬송", "헌금", "영혼의찬양", "중보기도"]
# 여러 줄을 이어 받는 항목 (본문이 주보에 실린 경우)
LONG = {"교독": 40, "성경봉독": 40}

ROLES = ["담임목사", "부목사", "원로목사", "목사", "전도사", "강도사", "선교사", "안수집사", "서리집사", "집사",
         "시무장로", "은퇴장로", "장로", "시무권사", "명예권사", "권사", "성도", "청년", "사모", "교사"]
PERSON_RE = re.compile(r"([가-힣]{2,4})\s*(" + "|".join(ROLES) + r")(?![가-힣])")
GROUP_RE = re.compile(r"([가-힣A-Za-z0-9]+\s*(?:성가대|찬양대|중창단|찬양팀|합창단|중창팀|중창|찬양단))")
HYMN_RE = re.compile(r"(?:새\s*찬송가|찬송가|찬송)?\s*(\d{1,3})\s*장")
COMMON = re.compile(r"다\s*같\s*이|회\s*중|인\s*도\s*자|반\s*주\s*자|일\s*어\s*서\s*서|\(\s*통\s*\d+\s*\)|통\s*\d+\s*장?")
DATE_RE = re.compile(r"(20\d\d)\s*[년.\-/]\s*(\d{1,2})\s*[월.\-/]\s*(\d{1,2})")
LEADER = re.compile(r"[.·…‥ㆍ_\-─—=]{3,}")
QUOTE = "\"'“”‘’「」『』<>《》"


def _compact(s):
    return re.sub(r"\s+", "", s)


def _all_labels():
    items = [(lab, key) for key, labs in LABELS.items() for lab in labs]
    items += [(lab, "_stop") for lab in STOP]
    return sorted(items, key=lambda x: len(x[0]), reverse=True)


def _match_label(line):
    """줄이 순서 이름으로 시작하면 (항목, 나머지 글자)."""
    compact = _compact(line)
    for lab, key in _all_labels():
        if not compact.startswith(lab):
            continue
        # 원문에서 순서 이름 글자 수만큼(띄어쓰기 무시) 건너뜀
        i = count = 0
        while i < len(line) and count < len(lab):
            if not line[i].isspace():
                count += 1
            i += 1
        rest = line[i:]
        # '기도하는', '찬송가' 처럼 낱말 일부면 순서 이름이 아님
        if rest[:1] and re.match(r"[가-힣]", rest[:1]):
            continue
        return key, rest.strip(" \t:：")
    return None


def _clean(text):
    text = LEADER.sub("\t", text)
    text = re.sub(r"^[\s※*◎○●▶►·]+", "", text)
    return re.sub(r"[ 　]+", " ", text).strip(" :：")


def _lines(text):
    return [_clean(x) for x in text.replace("\r", "\n").split("\n")]


def candidates(text):
    """(항목, 값 줄 목록, 줄 번호, 주변 순서 수) 목록."""
    lines = _lines(text)
    hits = [_match_label(l) if l else None for l in lines]
    label_rows = [i for i, h in enumerate(hits) if h]
    out = []
    for i, hit in enumerate(hits):
        if not hit or hit[0] == "_stop":
            continue
        key, rest = hit
        values = [rest] if rest else []
        limit = LONG.get(key, 2)
        j = i + 1
        while j < len(lines) and len(values) < limit + (1 if rest else 0):
            if hits[j] or (not lines[j] and key in LONG and values):
                break
            if lines[j]:
                values.append(lines[j])
            j += 1
        near = sum(1 for r in label_rows if r != i and abs(r - i) <= 3)
        out.append((key, values, i, near))
    return out


def _valid(key, value):
    if key in ("입례찬송", "영광송", "찬송", "봉헌찬송"):
        return bool(HYMN_RE.search(value) or _quoted(value))
    if key == "대표기도":
        return bool(PERSON_RE.search(value))
    if key == "교독":
        return bool(re.search(r"\d", value))
    if key == "성경봉독":
        return bool(bible.find_ref(value) or PERSON_RE.search(value))
    if key == "말씀":
        return bool(PERSON_RE.search(value) or _quoted(value))
    if key == "찬양":
        return bool(GROUP_RE.search(value) or _quoted(value))
    return bool(value.strip())


def split_order(text):
    """주보 글자 → {항목: 값 줄 목록}. 예배 순서 목록 안에 있는 것을 우선."""
    best = {}
    for key, values, row, near in candidates(text):
        joined = "\n".join(values)
        score = (_valid(key, joined), near > 0, -row)
        if key not in best or score > best[key][0]:
            best[key] = (score, values)
    return {k: v for k, (_, v) in best.items()}


def _person(text):
    m = PERSON_RE.search(text or "")
    return (m.group(1), m.group(2)) if m else ("", "")


def _quoted(text):
    m = re.search(rf"[{QUOTE}]\s*([^{QUOTE}]+?)\s*[{QUOTE}]", text or "")
    return m.group(1).strip() if m else ""


def _tidy(s):
    s = COMMON.sub(" ", s or "")
    s = re.sub(r"\s+", " ", s.replace("\t", " ")).strip(" -–:,/|()")
    return s.strip(QUOTE).strip()


def _hymn(text):
    """'64장 기뻐하며 경배하세', '43장', '‘기뻐하며 경배하세’' → (장, 제목)."""
    first = (text or "").split("\n")[0]
    m = HYMN_RE.search(first)
    if m:
        rest = COMMON.sub(" ", first[m.end():])
        rest = PERSON_RE.sub(" ", rest.strip().split("\t")[0]) if rest.strip() else ""
        return int(m.group(1)), _tidy(rest)
    title = _quoted(first) or _tidy(PERSON_RE.sub(" ", first.split("\t")[0]))
    return (memory.hymn_number(title), title) if title else None


def _reading_parts(lines):
    """주보에 실린 교독문 줄들 → '인도:/회중:/다같이:' 형식."""
    out, turn = [], 0
    for line in lines:
        line = _tidy(line) if not line.startswith("(") else line.strip()
        m = re.match(r"^\(?\s*(다\s*같\s*이|회\s*중|인\s*도)\s*\)?\s*[:：]?\s*(.+)$", line)
        if m:
            who = _compact(m.group(1))
            who = {"인도": "인도", "회중": "회중"}.get(who, "다같이")
            out.append(f"{who}: {m.group(2).strip()}")
            turn = 0 if who != "인도" else 1
        elif line:
            out.append(f"{'인도' if turn == 0 else '회중'}: {line}")
            turn = 1 - turn
    return "\n".join(out)


def _bulletin_verses(text, ref):
    """주보에 실린 '21땅이여 … 22들짐승들아 …' → 절마다 한 줄."""
    if not ref:
        return ""
    body = text[text.find(ref[5]) + len(ref[5]):] if ref[5] in text else text
    body = re.sub(r"\(\s*다\s*같\s*이\s*\)\s*아\s*멘\.?", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    book, ch, v1, ch2, v2, _ = ref
    if ch2 != ch:
        return ""
    out, pos = [], 0
    starts = []
    for v in range(v1, v2 + 1):
        m = re.compile(rf"(?<!\d){v}(?=\s*[^\d\s:~∼\-])").search(body, pos)
        if not m:
            return ""
        starts.append((v, m.start(), m.end()))
        pos = m.end()
    for i, (v, s, e) in enumerate(starts):
        end = starts[i + 1][1] if i + 1 < len(starts) else len(body)
        verse = body[e:end].strip()
        if not verse:
            return ""
        out.append(f"{v} {verse}")
    return "\n".join(out)


def _date(text):
    for m in DATE_RE.finditer(text):
        try:
            return dt.date(*(int(x) for x in m.groups()))
        except ValueError:
            continue
    return None


def parse(text, log=print):
    """주보 글자 → (weekly 데이터, 확인이 필요한 항목 목록)."""
    order = {k: "\n".join(v) for k, v in split_order(text).items()}
    data, todo = {}, []

    date = _date(text)
    if date:
        data["날짜"] = date.isoformat()
    else:
        todo.append("날짜를 찾지 못해 다가오는 주일로 합니다.")

    for key in ("입례찬송", "영광송", "찬송", "봉헌찬송"):
        hit = _hymn(order.get(key, ""))
        if not hit:
            todo.append(f"{key}: 주보에서 찾지 못했습니다.")
            continue
        num, title = hit
        title = title or (memory.hymn_title(num) if num else "")
        if not num:
            todo.append(f"{key}: '{title}' 의 장 번호를 입력해 주세요 (한 번 입력하면 기억합니다).")
        elif not title:
            todo.append(f"{key}: {num}장 제목을 입력해 주세요 (한 번 입력하면 기억합니다).")
        data[key] = {"장": num or "", "제목": title}
    if "입례찬송" in data:
        data["입례찬송"]["악보"] = False

    # 교독: 첫 줄 '16.시편 28편', 다음 줄부터 본문(있으면)
    lines = order.get("교독", "").split("\n")
    head = lines[0] if lines else ""
    num = None
    m = re.search(r"(\d+)\s*번", head) or re.match(r"\s*(\d+)", head)
    if m:
        num = int(m.group(1))
    saved = memory.reading(num) if num else {}
    psalm = re.search(r"([가-힣]+)\s*(\d+)\s*편", head)
    if num and psalm:
        title = f"{num}. {psalm.group(1)} {psalm.group(2)}편"
    else:
        title = saved.get("제목") or _tidy(head)
    body = _reading_parts(lines[1:]) or saved.get("본문", "")
    data["교독"] = {"제목": title, "본문": body}
    if not head:
        todo.append("교독: 주보에서 교독문을 찾지 못했습니다.")
    elif not body:
        todo.append(f"교독: {title} 본문을 입력해 주세요 (한 번 입력하면 기억합니다).")

    name, role = _person(order.get("대표기도", ""))
    data["대표기도"] = {"이름": name, "직분": role}
    if not name:
        todo.append("대표기도: 기도자 이름을 찾지 못했습니다.")

    raw = order.get("성경봉독", "")
    ref = bible.find_ref(raw)
    name, role = _person(raw.split(ref[5])[0] if ref else raw) if ref else _person(raw)
    if ref and not name:
        name, role = _person(raw)
    reading = {"봉독자": f"{name}  {role}".strip(), "본문": bible.format_ref(ref) if ref else _tidy(raw),
               "말씀": "", "마지막에_아멘": True}
    if ref:
        reading["말씀"] = (_bulletin_verses(raw, ref) or memory.scripture(reading["본문"])
                         or bible.verses(ref))
    data["성경봉독"] = reading
    if not ref:
        todo.append("성경봉독: 본문(예: 누가복음 10:36~37)을 찾지 못했습니다.")
    elif not reading["말씀"]:
        todo.append(f"성경봉독: {reading['본문']} 말씀 내용을 붙여 넣어 주세요 "
                    "(data/bible/ 에 성경 파일을 넣으면 자동으로 채워집니다).")
    if not name:
        todo.append("성경봉독: 봉독자 이름을 찾지 못했습니다.")

    raw = order.get("찬양", "")
    group = GROUP_RE.search(raw)
    composer = re.search(r"([가-힣A-Za-z][가-힣A-Za-z. ]{0,20}?)\s*(작곡|곡|편곡)(?![가-힣A-Za-z])", raw)
    title = _quoted(raw)
    if not title:
        rest = raw
        for hit in (group, composer):
            if hit:
                rest = rest.replace(hit.group(0), " ")
        title = _tidy(re.sub(r"\(\s*\)", " ", rest).split("\n")[0].split("\t")[0])
    saved = memory.anthem(title)
    data["찬양"] = {"성가대": _spaced_group(group.group(1)) if group else "", "곡명": title,
                  "작곡": f"{composer.group(1).strip()} 곡" if composer else saved.get("작곡", ""),
                  "가사": saved.get("가사", "")}
    if not title:
        todo.append("찬양: 곡명을 찾지 못했습니다.")

    raw = order.get("말씀", "")
    ref2 = bible.find_ref(raw)
    name, role = _person(raw)
    title = _quoted(raw)
    if not title:
        title = raw
        for part in (ref2[5] if ref2 else "", f"{name}{role}", name, role):
            if part:
                title = title.replace(part, " ")
        title = _tidy(title.split("\n")[0].split("\t")[0])
    data["말씀"] = {"제목": title.strip(), "본문": bible.format_ref(ref2) if ref2 else reading["본문"],
                  "설교자": name, "직분": role}
    if not title:
        todo.append("말씀: 설교 제목을 찾지 못했습니다.")
    if not name:
        todo.append("말씀: 설교자 이름을 찾지 못했습니다.")
    return data, todo


def _spaced_group(text):
    return re.sub(r"(성가대|찬양대|중창단|찬양팀|합창단|중창팀|찬양단)$", r" \1", text.replace(" ", ""))
