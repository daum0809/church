"""주일예배 PDF 만들기 (명령줄).

사용법:
    python make_worship.py                 # weekly.yaml 로 만들기
    python make_worship.py 주보.hwp         # 주보(한글 .hwp/.hwpx)를 읽어서 바로 만들기
    python make_worship.py --bulletin      # 주보 폴더에서 가장 최근 한글 파일로 만들기
    python make_worship.py 다른입력.yaml -o 결과.pdf
    python make_worship.py --prefetch 전체  # 찬송가 악보를 미리 받아 두기 (1-100, 305,455 도 가능)

창으로 쓰려면: python app.py
"""

import argparse
import sys

from worship.run import ERRORS, newest_bulletin, run


def _utf8_console():
    """윈도우 기본 콘솔(cp949/cp1252)에서도 한글 출력이 멈추지 않게."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main():
    _utf8_console()
    parser = argparse.ArgumentParser(description="주일예배 PDF 만들기")
    parser.add_argument("input", nargs="?", help="weekly.yaml 또는 주보 .hwp/.hwpx")
    parser.add_argument("--bulletin", action="store_true", help="주보 폴더의 최신 한글 파일 사용")
    parser.add_argument("-o", "--output", help="저장할 PDF 경로")
    parser.add_argument("--prefetch", metavar="장번호", nargs="?", const="전체",
                        help="찬송가 악보를 미리 받아 저장: 전체 / 1-100 / 305,455 (곡마다 10초, 이어받기 가능)")
    args = parser.parse_args()
    if args.prefetch is not None:
        from worship import hymns
        try:
            hymns.prefetch(hymns.parse_numbers(args.prefetch))
        except hymns.HymnError as e:
            print(f"\n[오류] {e}")
            return 1
        except KeyboardInterrupt:
            print("\n중지했습니다. 다음에 다시 시작하면 이어서 받습니다.")
        return 0
    try:
        path = newest_bulletin() if args.bulletin and not args.input else args.input
        run(path, args.output)
    except ERRORS as e:
        print(f"\n[오류] {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
