"""data(dict) → PDF 와, 화면에 보여 줄 결과(dict). 웹 서버와 브라우저 버전이 함께 씁니다."""

from pathlib import Path

import pymupdf

from . import paths
from .build import build_data, load_input


def build_result(data, todo=None):
    """PDF 를 만들고 (PDF 경로, 결과 dict) 를 돌려줍니다."""
    logs, report = [], {}
    old = load_input(paths.WEEKLY) if paths.WEEKLY.exists() else {}
    data.setdefault("설정", old.get("설정") or {"글꼴": "", "출력폴더": "output"})
    pdf = build_data(data, None, logs.append, report)
    with pymupdf.open(pdf) as doc:
        pages = len(doc)
    return Path(pdf), {
        "ok": True,
        "data": data,
        "todo": todo or [],
        "missing_hymns": report.get("missing_hymns", []),
        "pdf_name": Path(pdf).name,
        "pages": pages,
        "log": "\n".join(logs),
    }
