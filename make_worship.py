"""주일예배 PDF 만들기.

사용법:
    python make_worship.py                 # weekly.yaml 로 만들기
    python make_worship.py 다른입력.yaml
    python make_worship.py -o 결과.pdf
"""

import argparse
import sys
from pathlib import Path

from worship.build import InputError, build
from worship.hymns import HymnError


def main():
    parser = argparse.ArgumentParser(description="주일예배 PDF 만들기")
    parser.add_argument("input", nargs="?", default=str(Path(__file__).parent / "weekly.yaml"))
    parser.add_argument("-o", "--output", help="저장할 PDF 경로")
    args = parser.parse_args()
    try:
        build(args.input, args.output)
    except (InputError, HymnError) as e:
        print(f"\n[오류] {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
