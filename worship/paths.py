"""파일 위치.

- RES : 프로그램에 들어 있는 읽기 전용 파일 (원본 디자인 PDF, 글꼴, 처음 악보/기억 데이터)
- HOME: 사용자가 쓰고 고치는 파일 (weekly.yaml, hymns/, data/, output/, 주보/)

파이썬으로 실행하면 둘 다 이 저장소 폴더이고,
exe 로 실행하면 RES 는 exe 안, HOME 은 exe 가 있는 폴더입니다.
"""

import shutil
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    RES = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    HOME = Path(sys.executable).resolve().parent
else:
    RES = HOME = Path(__file__).resolve().parent.parent

BASE_PDF = RES / "templates" / "base.pdf"
FONTS = RES / "fonts"
HYMN_DIR = HOME / "hymns"
INBOX = HYMN_DIR / "inbox"
DATA = HOME / "data"
OUTPUT = HOME / "output"
WEEKLY = HOME / "weekly.yaml"
BULLETIN_DIR = HOME / "주보"


def setup():
    """exe 처음 실행 때 기본 파일들을 exe 옆 폴더에 풀어 놓습니다."""
    if RES == HOME:
        return
    for name in ("hymns", "data"):
        src, dst = RES / name, HOME / name
        if src.exists():
            for f in src.rglob("*"):
                target = dst / f.relative_to(src)
                if f.is_file() and not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target)
    if not WEEKLY.exists() and (RES / "weekly.yaml").exists():
        shutil.copy2(RES / "weekly.yaml", WEEKLY)
    for d in (INBOX, OUTPUT, BULLETIN_DIR, DATA / "bible"):
        d.mkdir(parents=True, exist_ok=True)
