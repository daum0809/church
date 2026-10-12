"""주보(한글 문서) 글자에서 예배 순서를 읽어 weekly.yaml 과 같은 내용을 만듭니다.

주보마다 모양이 달라서 '순서 이름'을 기준으로 찾습니다.
  입례찬송 ...... 64장 ...... 다같이
  대표기도 ...... 김도연 안수집사
  성경봉독 ...... 누가복음 10:36~37 ...... 김경자 권사
표 형태(순서 | 내용 | 담당)로 칸이 나뉘어 있어도 됩니다.
"""

import datetime as dt
import re

from . import bible, memory

# 순서 이름 (띄어쓰기 무시). 앞쪽 항목이 우선.
LABELS = {
    "입례찬송": ["입례찬송", "예배찬송", "경배찬송", "개회찬송"],
    "영광송": ["영광송", "송영"],
    "교독": ["교독문", "성시교독", "교독", "공동기도"],
    "봉헌찬송": ["봉헌찬송", "헌금찬송", "봉헌"],
    "찬송": ["찬송"],
    "대표기도": ["대표기도", "기도"],
    "성경봉독": ["성경봉독", "말씀봉독", "봉독", "성경"],
    "찬양": ["성가대찬양", "특별찬양", "찬양", "성가"],
    "말씀": ["말씀선포", "설교", "말씀"],
}
# 값 모으기를 멈추는 다른 순서 이름들
STOP = ["예배로부름", "예배의부름", "묵도", "기원", "신앙고백", "사도신경", "참회기도", "응답송", "응답찬송",
        "봉헌기도", "주기도문", "주의기도", "주기도", "축도", "광고", "교회소식", "환영", "파송", "후주", "전주",
        "목회기도", "결단찬송", "파송찬송", "헌금"]

ROLES = ["담임목사", "부목사", "원로목사", "목사", "전도사", "강도사", "선교사", "안수집사", "서리집사", "집사",
         "시무장로", "은퇴장로", "장로", "시무권사", "명예권사", "권사", "성도", "청년", "사모", "교사"]
PERSON_RE = re.compile(r"([가-힣]{2,4})\s*(" + "|".join(ROLES) + r")(?![가-힣])")
GROUP_RE = re.compile(r"([가-힣A-Za-z0-9]+\s*(?:성가대|찬양대|중창단|찬양팀|합창단|중창팀|중창|찬양단))")
HYMN_RE = re.compile(r"(?:새\s*찬송가|찬송가|찬송)?\s*(\d{1,3})\s*장")
COMMON = re.compile(r"다\s*같\s*이|회\s*중|인\s*도\s*자|일\s*어\s*서\s*서|일어서서|\(\s*통\s*\d+\s*\)|통\s*\d+\s*장?")
DATE_RE = re.compile(r"(20\d\d)\s*[년.\-/]\s*(\d{1,2})\s*[월.\-/]\s*(\d{1,2})")
LEADER = re.compile(r"[.·…‥ㆍ_\-─—=]{3,}")


def _compact(s):
    return re.sub(r"\s+", "", s)


def _all_labels():
    items = [(lab, key) for key, labs in LABELS.items() for lab in labs]
    items += [(lab, None) for lab in STOP]
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
        nxt = rest[:1]
        # '기도하는', '찬송가' 처럼 낱말 일부면 순서 이름이 아님
        if nxt and re.match(r"[가-힣]", nxt):
            continue
        return key or "_stop", rest
    return None


def _clean(text):
    text = LEADER.sub("\t", text)
    return re.sub(r"[ 　]+", " ", text).strip(" \t:：")


def split_order(text):
    """주보 글자 → {항목: 값 문자열} (같은 항목은 처음 나온 것)."""
    lines = [l for l in (_clean(x) for x in text.replace("\r", "\n").split("\n")) if l]
    found, cur = {}, None
    gathered = 0
    for line in lines:
        hit = _match_label(line)
        if hit:
            key, rest = hit
            cur = None
            if key != "_stop" and key not in found:
                found[key] = rest.strip()
                cur, gathered = key, 0
            continue
        # 표 칸 때문에 다음 줄로 넘어간 값 (최대 3칸)
        if cur and gathered < 3:
            found[cur] = (found[cur] + "\t" + line).strip()
            gathered += 1
    return found


def _person(text):
    m = PERSON_RE.search(text or "")
    return (m.group(1), m.group(2)) if m else ("", "")


def _hymn(text):
    m = HYMN_RE.search(text or "")
    if not m:
        return None
    num = int(m.group(1))
    rest = COMMON.sub(" ", text[m.end():])
    rest = re.split(r"\t", rest.strip())[0] if rest.strip() else ""
    title = re.sub(r"^[\s\-–:()]+|[\s\-–:()]+$", "", PERSON_RE.sub("", rest)).strip()
    title = title.strip("\"'“”‘’「」『』<>《》")
    return num, title


def _tidy(s):
    s = COMMON.sub(" ", s or "")
    s = re.sub(r"\s+", " ", s.replace("\t", " ")).strip(" -–:,/|()")
    return s


def parse(text, log=print):
    """주보 글자 → (weekly 데이터, 확인이 필요한 항목 목록)."""
    order = split_order(text)
    data, todo = {}, []

    m = DATE_RE.search(text)
    if m:
        data["날짜"] = dt.date(*(int(x) for x in m.groups())).isoformat()
    else:
        todo.append("날짜를 찾지 못해 다가오는 주일로 합니다.")

    for key in ("입례찬송", "영광송", "찬송", "봉헌찬송"):
        hit = _hymn(order.get(key, ""))
        if not hit:
            todo.append(f"{key}: 장 번호를 찾지 못했습니다.")
            continue
        num, title = hit
        title = title or memory.hymn_title(num)
        if not title:
            todo.append(f"{key}: {num}장 제목을 입력해 주세요 (한 번 입력하면 기억합니다).")
        data[key] = {"장": num, "제목": title}
    if "입례찬송" in data:
        data["입례찬송"]["악보"] = False

    # 교독: '20번', '교독문 20', '시편 33편'
    raw = order.get("교독", "")
    num = None
    m = re.search(r"(\d+)\s*번", raw) or re.match(r"\s*(\d+)", raw)
    if m:
        num = int(m.group(1))
    saved = memory.reading(num) if num else {}
    psalm = re.search(r"([가-힣]+)\s*(\d+)\s*편", raw)
    if saved.get("제목"):
        title = saved["제목"]
    elif num and psalm:
        title = f"{num}. {psalm.group(1)} {psalm.group(2)}편"
    else:
        title = _tidy(raw)
    data["교독"] = {"제목": title, "본문": saved.get("본문", "")}
    if not raw:
        todo.append("교독: 주보에서 교독문을 찾지 못했습니다.")
    elif not saved.get("본문"):
        todo.append(f"교독: {title} 본문을 입력해 주세요 (한 번 입력하면 기억합니다).")

    name, role = _person(order.get("대표기도", ""))
    data["대표기도"] = {"이름": name, "직분": role}
    if not name:
        todo.append("대표기도: 기도자 이름을 찾지 못했습니다.")

    raw = order.get("성경봉독", "")
    ref = bible.find_ref(raw)
    name, role = _person(raw.replace(ref[5], " ") if ref else raw)
    reading = {"봉독자": f"{name}  {role}".strip(), "본문": bible.format_ref(ref) if ref else _tidy(raw),
               "말씀": "", "마지막에_아멘": True}
    if ref:
        reading["말씀"] = memory.scripture(reading["본문"]) or bible.verses(ref)
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
    composer = re.search(r"([가-힣A-Za-z]{2,10})\s*(작곡|곡|편곡)(?![가-힣])", raw)
    rest = raw
    for hit in (group, composer):
        if hit:
            rest = rest.replace(hit.group(0), " ")
    title = _tidy(re.sub(r"\(\s*\)", " ", rest)).strip("\"'“”‘’「」『』")
    data["찬양"] = {"성가대": _spaced_group(group.group(1)) if group else "",
                  "곡명": title, "작곡": f"{composer.group(1)} 곡" if composer else "", "가사": ""}
    saved = memory.anthem(title)
    if saved and not data["찬양"]["작곡"]:
        data["찬양"]["작곡"] = saved.get("작곡", "")
    data["찬양"]["가사"] = saved.get("가사", "")
    if not title:
        todo.append("찬양: 곡명을 찾지 못했습니다.")

    raw = order.get("말씀", "")
    ref2 = bible.find_ref(raw)
    quoted = re.search(r"[\"“『「<《']\s*(.+?)\s*[\"”』」>》']", raw)
    name, role = _person(raw)
    if quoted:
        title = quoted.group(1)
    else:
        title = raw
        for part in (ref2[5] if ref2 else "", f"{name}{role}", name, role):
            if part:
                title = title.replace(part, " ")
        title = _tidy(title).split("\t")[0]
    data["말씀"] = {"제목": title.strip(), "본문": bible.format_ref(ref2) if ref2 else reading["본문"],
                  "설교자": name, "직분": role}
    if not title:
        todo.append("말씀: 설교 제목을 찾지 못했습니다.")
    if not name:
        todo.append("말씀: 설교자 이름을 찾지 못했습니다.")
    return data, todo


def _spaced_group(text):
    return re.sub(r"(성가대|찬양대|중창단|찬양팀|합창단|중창팀|찬양단)$", r" \1", text.replace(" ", ""))
