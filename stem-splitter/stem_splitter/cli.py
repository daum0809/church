"""명령줄 실행기.

    python -m stem_splitter 노래.mp3                 # 보컬 / 반주 / 이펙트 3분리 (기본)
    python -m stem_splitter 노래.mp3 --mode 6stem    # 보컬 / 드럼 / 베이스 / 기타 / 피아노 / 기타악기
    python -m stem_splitter 노래.mp3 --mode fx-detail  # 이펙트 종류별 상세 분리 + 분석
    python -m stem_splitter 노래.mp3 --mode all      # 전부
    python -m stem_splitter 폴더/                     # 폴더 안 모든 곡 일괄 처리
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".aiff", ".aif", ".mp4"}


def _collect(inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            files += sorted(f for f in p.rglob("*") if f.suffix.lower() in AUDIO_EXTS)
        elif p.is_file():
            files.append(p)
        else:
            print(f"[건너뜀] 파일을 찾을 수 없음: {p}", file=sys.stderr)
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="stem_splitter", description="노래를 보컬 / 반주 / 이펙트로 분리합니다.")
    ap.add_argument("inputs", nargs="+", help="오디오 파일 또는 폴더")
    ap.add_argument("-o", "--output", default="separated", help="결과 저장 폴더 (기본: ./separated)")
    ap.add_argument("-m", "--mode", choices=["3way", "fx-detail", "6stem", "all"], default="3way",
                    help="3way=보컬/반주/이펙트, fx-detail=이펙트 종류별 상세 분리+분석, "
                         "6stem=악기별, all=전부")
    ap.add_argument("--fast", action="store_true", help="빠른 보컬 분리 모델 사용 (품질 약간 낮음)")
    ap.add_argument("--exact", action="store_true",
                    help="이펙트 = 원곡 - 보컬 - 반주 (세 트랙 합이 원곡과 정확히 일치)")
    ap.add_argument("--no-extras", action="store_true", help="보조 트랙(이펙트 포함 보컬 등) 저장 안 함")
    ap.add_argument("--model-dir", help="모델 캐시 폴더 (기본: ~/.cache/stem_splitter/models)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    files = _collect(args.inputs)
    if not files:
        print("처리할 오디오 파일이 없습니다.", file=sys.stderr)
        return 1

    from .pipeline import Splitter

    splitter = Splitter(model_dir=args.model_dir, fast=args.fast,
                        log_level=logging.INFO if args.verbose else logging.WARNING)
    jobs = []
    if args.mode in ("3way", "all"):
        jobs.append(("3way", lambda f, o: splitter.split_three(
            f, o, keep_extras=not args.no_extras, exact=args.exact)))
    if args.mode in ("fx-detail", "all"):
        from .fx_detail import split_fx_detail

        jobs.append(("fx-detail", lambda f, o: split_fx_detail(splitter, f, o, keep_extras=not args.no_extras)))
    if args.mode in ("6stem", "all"):
        jobs.append(("6stem", splitter.split_six))

    failed = 0
    for i, f in enumerate(files, 1):
        out = Path(args.output) / f.stem
        print(f"[{i}/{len(files)}] {f.name} 분리 중 ...")
        for name, job in jobs:
            try:  # 하나 실패해도 나머지는 계속
                _summary(job(f, out if len(jobs) == 1 else out / name))
            except Exception as e:
                failed += 1
                print(f"  ✗ {name} 실패: {e}", file=sys.stderr)
    total = len(files) * len(jobs)
    print(f"완료: {total - failed}/{total} 작업 성공 → {Path(args.output).resolve()}")
    return 1 if failed else 0


def _summary(r) -> None:
    for name, path in r.outputs.items():
        print(f"  ✓ {name:<28} {path}")
    if "energy_share_percent" in r.report:
        print("  에너지 비율(%):", json.dumps(r.report["energy_share_percent"], ensure_ascii=False))
        print(f"  복원 SNR: {r.report['reconstruction_snr_db']} dB (트랙 합 ≈ 원곡 정도, 높을수록 좋음)")
    fx = r.report.get("effect_analysis")
    if fx:
        print("  ── 이펙트 분석 ──")
        for name, by_src in fx["separated"].items():
            print(f"  {name:<24}", ", ".join(f"{s}: {v['level']}" for s, v in by_src.items()))
        for name, v in fx["estimated_only"].items():
            print(f"  {name:<24} {v['level']}  (추정, 신뢰도 {v.get('confidence', '-')})")
        for name, why in fx["not_detectable"].items():
            print(f"  {name:<24} 판정 안 함 — {why}")
