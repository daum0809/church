"""주보 → PDF, weekly.yaml → PDF. 명령줄과 프로그램 창이 함께 씁니다."""

from pathlib import Path

from . import bulletin, memory, paths
from .build import InputError, build_data, load_input
from .hwp import HwpError, extract_text
from .hymns import HymnError

HWP_EXT = {".hwp", ".hwpx"}
ERRORS = (InputError, HymnError, HwpError)

HEADER = """# ===============================================================
#  주보({source})에서 자동으로 읽은 내용입니다.
#  틀린 곳이나 빈 곳이 있으면 고쳐서 저장한 뒤 다시 만들기를 하세요.
# ===============================================================
"""


def from_bulletin(path, output=None, log=print):
    """주보 한글 파일을 읽어 weekly.yaml 을 새로 쓰고 PDF 를 만듭니다.

    돌려주는 값: (PDF 경로, 확인이 필요한 항목 목록)
    """
    paths.setup()
    path = Path(path)
    log(f"주보 읽는 중: {path.name}")
    data, todo = bulletin.parse(extract_text(path))
    old = load_input(paths.WEEKLY) if paths.WEEKLY.exists() else {}
    data["설정"] = old.get("설정") or {"글꼴": "", "출력폴더": "output"}
    with open(paths.WEEKLY, "w", encoding="utf-8") as f:
        f.write(HEADER.format(source=path.name))
        memory.dump_yaml(data, f)
    log(f"읽은 내용을 {paths.WEEKLY.name} 에 저장했습니다.")
    if todo:
        log("\n[확인 필요] 아래 항목은 weekly.yaml 에서 채운 뒤 다시 만들어 주세요.")
        for item in todo:
            log(f"  - {item}")
        log("")
    return build_data(data, output, log), todo


def from_weekly(path=None, output=None, log=print):
    paths.setup()
    return build_data(load_input(path or paths.WEEKLY), output, log), []


def run(path=None, output=None, log=print):
    """확장자를 보고 주보/weekly.yaml 중 알맞게 처리."""
    if path and Path(path).suffix.lower() in HWP_EXT:
        return from_bulletin(path, output, log)
    return from_weekly(path, output, log)


def newest_bulletin():
    paths.BULLETIN_DIR.mkdir(exist_ok=True)
    files = [f for f in paths.BULLETIN_DIR.glob("*")
             if f.suffix.lower() in HWP_EXT and not f.name.startswith("~")]
    if not files:
        raise InputError(f"'{paths.BULLETIN_DIR.name}' 폴더에 주보 한글 파일(.hwp/.hwpx)을 넣어 주세요.")
    return max(files, key=lambda f: f.stat().st_mtime)
