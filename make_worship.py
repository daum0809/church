"""주일예배 PDF 만들기.

사용법:
    python make_worship.py                 # weekly.yaml 로 만들기
    python make_worship.py 주보.hwp         # 주보(한글 .hwp/.hwpx)를 읽어서 바로 만들기
    python make_worship.py --bulletin      # 주보 폴더에서 가장 최근 한글 파일로 만들기
    python make_worship.py 다른입력.yaml -o 결과.pdf
"""

import argparse
import sys
from pathlib import Path

from worship.build import InputError, build, build_data, load_input
from worship.hwp import HwpError
from worship.hymns import HymnError

ROOT = Path(__file__).resolve().parent
WEEKLY = ROOT / "weekly.yaml"
BULLETIN_DIR = ROOT / "주보"
HWP_EXT = {".hwp", ".hwpx"}

HEADER = """# ===============================================================
#  주보({source})에서 자동으로 읽은 내용입니다.
#  틀린 곳이나 빈 곳이 있으면 고쳐서 저장한 뒤 '만들기.bat' 을 실행하세요.
# ===============================================================
"""


def from_bulletin(path, output):
    from worship import bulletin, memory
    from worship.hwp import extract_text

    print(f"주보 읽는 중: {path.name}")
    data, todo = bulletin.parse(extract_text(path))
    old = load_input(WEEKLY) if WEEKLY.exists() else {}
    data["설정"] = old.get("설정") or {"글꼴": "", "출력폴더": "output"}
    with open(WEEKLY, "w", encoding="utf-8") as f:
        f.write(HEADER.format(source=path.name))
        memory.dump_yaml(data, f)
    print(f"읽은 내용을 {WEEKLY.name} 에 저장했습니다.")
    if todo:
        print("\n[확인 필요] 아래 항목은 weekly.yaml 에서 채운 뒤 '만들기.bat' 으로 다시 만들어 주세요.")
        for item in todo:
            print(f"  - {item}")
        print()
    return build_data(data, output)


def newest_bulletin():
    files = [f for f in BULLETIN_DIR.glob("*") if f.suffix.lower() in HWP_EXT and not f.name.startswith("~")]
    if not files:
        raise InputError(f"'{BULLETIN_DIR.name}' 폴더에 주보 한글 파일(.hwp/.hwpx)을 넣어 주세요.")
    return max(files, key=lambda f: f.stat().st_mtime)


def main():
    parser = argparse.ArgumentParser(description="주일예배 PDF 만들기")
    parser.add_argument("input", nargs="?", help="weekly.yaml 또는 주보 .hwp/.hwpx")
    parser.add_argument("--bulletin", action="store_true", help="주보 폴더의 최신 한글 파일 사용")
    parser.add_argument("-o", "--output", help="저장할 PDF 경로")
    args = parser.parse_args()
    try:
        if args.bulletin and not args.input:
            from_bulletin(newest_bulletin(), args.output)
        elif args.input and Path(args.input).suffix.lower() in HWP_EXT:
            from_bulletin(Path(args.input), args.output)
        else:
            build(args.input or WEEKLY, args.output)
    except (InputError, HymnError, HwpError) as e:
        print(f"\n[오류] {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
