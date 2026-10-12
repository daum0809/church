"""한 번 입력한 내용을 기억해 두었다가 다음에 자동으로 채웁니다.

- data/hymn_titles.yaml : 찬송가 장 번호 → 제목
- data/readings/NNN.yaml : 교독문 번호 → 제목과 본문
- data/scripture.yaml : 성경 본문 위치 → 말씀 내용
- data/anthems.yaml : 찬양 곡명 → 작곡, 가사
"""

import re
from pathlib import Path

import yaml

from .paths import DATA

TITLES = DATA / "hymn_titles.yaml"
READINGS = DATA / "readings"
SCRIPTURE = DATA / "scripture.yaml"
ANTHEMS = DATA / "anthems.yaml"
HYMN_KEYS = ("입례찬송", "영광송", "찬송", "봉헌찬송")


def _load(path):
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class _Dumper(yaml.SafeDumper):
    pass


def _str(dumper, value):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _str)


def dump_yaml(data, f, sort_keys=False):
    yaml.dump(data, f, Dumper=_Dumper, allow_unicode=True, sort_keys=sort_keys, width=1000)


def _dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        dump_yaml(data, f, sort_keys=True)


def hymn_title(num):
    return _load(TITLES).get(int(num), "")


def hymn_number(title):
    """제목으로 장 번호 찾기 (띄어쓰기 무시). 모르면 None."""
    key = _key(title)
    for num, saved in _load(TITLES).items():
        if _key(saved) == key:
            return int(num)
    return None


def reading_number(title):
    m = re.match(r"\s*(\d+)", str(title or ""))
    return int(m.group(1)) if m else None


def reading(num):
    return _load(READINGS / f"{int(num):03d}.yaml")


def scripture(ref):
    return _load(SCRIPTURE).get(_key(ref), "")


def anthem(title):
    return _load(ANTHEMS).get(_key(title), {})


def _key(text):
    return re.sub(r"\s+", "", str(text or ""))


def _remember(path, key, value):
    store = _load(path)
    if key and value and store.get(key) != value:
        store[key] = value
        _dump(path, store)


def learn(data):
    """PDF 를 만들 때 쓴 찬송가 제목과 교독문을 저장."""
    titles = _load(TITLES)
    changed = False
    for key in HYMN_KEYS:
        item = data.get(key) or {}
        if isinstance(item, dict) and item.get("장") and item.get("제목"):
            num, title = int(item["장"]), str(item["제목"]).strip()
            if titles.get(num) != title:
                titles[num] = title
                changed = True
    if changed:
        _dump(TITLES, titles)

    item = data.get("교독") or {}
    num = reading_number(item.get("제목"))
    if num and str(item.get("본문") or "").strip():
        new = {"제목": str(item["제목"]).strip(), "본문": str(item["본문"]).strip() + "\n"}
        if reading(num) != new:
            _dump(READINGS / f"{num:03d}.yaml", new)

    item = data.get("성경봉독") or {}
    text = str(item.get("말씀") or "").strip()
    _remember(SCRIPTURE, _key(item.get("본문")), text + "\n" if text else "")

    item = data.get("찬양") or {}
    value = {k: str(item.get(k) or "").strip() for k in ("작곡", "가사")}
    if any(value.values()):
        if value["가사"]:
            value["가사"] += "\n"
        _remember(ANTHEMS, _key(item.get("곡명")), value)
