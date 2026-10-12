"""핸드폰 브라우저(Pyodide) 안에서 부르는 함수들. 서버 없이 폰 안에서 PDF 를 만듭니다."""

import json
import re
import time
from pathlib import Path

from . import bulletin, hymns, memory, paths
from .hwp import extract_text
from .run import ERRORS
from .service import build_result

_started = 0.0


def init():
    """폴더를 만들고 악보 자동 다운로드를 끕니다."""
    global _started
    hymns.ALLOW_DOWNLOAD = False
    for d in (paths.INBOX, paths.OUTPUT, paths.BULLETIN_DIR, paths.DATA / "bible"):
        d.mkdir(parents=True, exist_ok=True)
    _started = time.time()
    return "ok"


def _safe(fn):
    """알려진 오류(주보 못 읽음, 악보 없음 등)는 화면에 보여 줄 메시지로 돌려줍니다."""
    def wrapper(*args):
        try:
            return fn(*args)
        except ERRORS + (ValueError,) as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    wrapper.__name__ = fn.__name__
    return wrapper


def _reply(data, todo=None):
    pdf, result = build_result(data, todo)
    result["pdf_path"] = str(pdf)
    return json.dumps(result, ensure_ascii=False, default=str)


@_safe
def from_hwp(path):
    """올린 주보 파일(path)을 읽어 PDF 를 만듭니다."""
    data, todo = bulletin.parse(extract_text(Path(path)))
    return _reply(data, todo)


@_safe
def from_data(text):
    """화면에서 고친 내용(JSON)으로 PDF 를 다시 만듭니다."""
    return _reply(json.loads(text))


def add_hymn(num, filename):
    """/app/hymns/inbox 에 올려 둔 악보 파일을 찬송가 num 장 악보로 등록."""
    if not re.fullmatch(r"\d{1,3}", str(num)):
        raise ValueError("찬송가 장 번호가 올바르지 않습니다.")
    cache = hymns.cache_path(int(num))
    if cache.exists():
        cache.unlink()
    hymns._FAILED.pop(int(num), None)
    return "ok"


def restore(rel):
    """/restore/<rel> 에 되살려 둔 파일(예전에 기억시킨 내용)을 /app/<rel> 에 합칩니다.

    찬송가 제목·성경 말씀·찬양 목록처럼 '이름 → 내용' 표는 새 버전의 기본값과 합치고,
    그 밖의 파일(교독문, 악보)은 그대로 덮어씁니다.
    """
    src = Path("/restore") / rel
    dst = paths.HOME / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.suffix == ".yaml" and dst.parent == paths.DATA:
        merged = memory._load(dst)
        merged.update(memory._load(src))
        memory._dump(dst, merged)
    else:
        dst.write_bytes(src.read_bytes())
    return "ok"


def changed_files():
    """init() 이후 새로 만들어졌거나 바뀐 기억 파일들 (data/, hymns/)."""
    out = []
    for base in (paths.DATA, paths.HYMN_DIR):
        for f in base.rglob("*"):
            if f.is_file() and "inbox" not in f.parts and f.stat().st_mtime >= _started:
                out.append(str(f.relative_to(paths.HOME)))
    return json.dumps(out, ensure_ascii=False)
