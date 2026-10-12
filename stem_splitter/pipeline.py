"""분리 파이프라인.

3분리(기본) — 보컬 / 반주 / 이펙트
------------------------------------
1단계  원곡  → [보컬 분리 모델]       → 보컬(젖은 소리) + 반주(젖은 소리)
2단계  보컬  → [디리버브·디에코 모델] → 마른 보컬     + 보컬 이펙트
3단계  반주  → [디리버브·디에코 모델] → 마른 반주     + 반주 이펙트
4단계  이펙트 = 보컬 이펙트 + 반주 이펙트

"이펙트"는 리버브(잔향), 에코, 딜레이처럼 원음에 덧입혀진 공간계 효과를 뜻한다.
결과 세 파일을 다시 더하면 원곡에 가깝게 복원된다(복원 오차를 리포트로 남긴다).

6분리 — 보컬 / 드럼 / 베이스 / 기타 / 피아노 / 기타악기(other)
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

# 품질 우선 기본 모델 (audio-separator 가 처음 실행 시 자동 다운로드)
VOCAL_MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
VOCAL_MODEL_FAST = "UVR-MDX-NET-Inst_HQ_3.onnx"
DEREVERB_MODEL = "UVR-DeEcho-DeReverb.pth"
SIX_STEM_MODEL = "htdemucs_6s.yaml"

# 모델이 내보내는 스템 이름 중 "효과가 제거된 쪽"을 가리키는 표시
_DRY_MARKERS = ("no reverb", "no echo", "noreverb", "noecho", "dry", "no_reverb", "no_echo")
_VOCAL_MARKERS = ("(vocals)", "_vocals", "(vocal)")


@dataclass
class Result:
    outputs: dict[str, Path] = field(default_factory=dict)
    report: dict = field(default_factory=dict)


def _stem_label(path: Path) -> str:
    """'song_(Vocals)_model.wav' → 'vocals'."""
    name = path.stem
    if "(" in name and ")" in name:
        return name[name.rfind("(") + 1 : name.rfind(")")].strip().lower()
    return name.lower()


class Splitter:
    def __init__(self, model_dir: Path | None = None, fast: bool = False, log_level: int = 30):
        from audio_separator.separator import Separator  # 무거운 import 는 지연

        self._Separator = Separator
        self.model_dir = Path(model_dir) if model_dir else Path.home() / ".cache" / "stem_splitter" / "models"
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.vocal_model = VOCAL_MODEL_FAST if fast else VOCAL_MODEL
        self.log_level = log_level
        self._loaded: dict[tuple[str, str], object] = {}

    # ------------------------------------------------------------------ helpers
    def _run(self, model: str, audio: Path, out_dir: Path) -> list[Path]:
        key = (model, str(out_dir))
        sep = self._loaded.get(key)
        if sep is None:
            sep = self._Separator(
                output_dir=str(out_dir),
                model_file_dir=str(self.model_dir),
                output_format="WAV",
                log_level=self.log_level,
            )
            sep.load_model(model_filename=model)
            self._loaded[key] = sep
        files = sep.separate(str(audio))
        return [p if p.is_absolute() else out_dir / p for p in map(Path, files)]

    def _split_vocals(self, audio: Path, work: Path) -> tuple[Path, Path]:
        files = self._run(self.vocal_model, audio, work / "1_vocals")
        vocals = [f for f in files if any(m in f.name.lower() for m in _VOCAL_MARKERS)]
        if len(files) != 2 or len(vocals) != 1:
            raise RuntimeError(f"보컬 분리 결과를 해석할 수 없습니다: {[f.name for f in files]}")
        return vocals[0], next(f for f in files if f != vocals[0])

    def _split_effects(self, audio: Path, work: Path, tag: str) -> tuple[Path, Path]:
        files = self._run(DEREVERB_MODEL, audio, work / f"2_{tag}")
        dry = [f for f in files if any(m in _stem_label(f) for m in _DRY_MARKERS)]
        if len(files) != 2 or len(dry) != 1:
            raise RuntimeError(f"이펙트 분리 결과를 해석할 수 없습니다: {[f.name for f in files]}")
        return dry[0], next(f for f in files if f != dry[0])

    # ------------------------------------------------------------------ modes
    def split_three(self, audio: Path, out_dir: Path, keep_extras: bool = True, exact: bool = False) -> Result:
        """보컬 / 반주 / 이펙트 3분리.

        exact=True 이면 이펙트 = 원곡 − 보컬 − 반주 로 계산해 세 트랙의 합이 원곡과 정확히 같아진다
        (대신 분리 과정의 잔여물도 이펙트 트랙에 섞인다).
        """
        audio, out_dir = Path(audio), Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="stem_splitter_") as tmp:
            work = Path(tmp)
            vocals_wet, inst_wet = self._split_vocals(audio, work)
            vocals_dry, vocal_fx = self._split_effects(vocals_wet, work, "vocals")
            inst_dry, inst_fx = self._split_effects(inst_wet, work, "inst")

            mix, sr = _read(audio)
            tracks = {k: _read(p, sr)[0] for k, p in {
                "vocals_wet": vocals_wet, "inst_wet": inst_wet,
                "vocals_dry": vocals_dry, "vocal_fx": vocal_fx,
                "inst_dry": inst_dry, "inst_fx": inst_fx,
            }.items()}
            n = min(len(mix), *(len(t) for t in tracks.values()))
            mix = mix[:n]
            tracks = {k: _match_channels(v[:n], mix.shape[1]) for k, v in tracks.items()}
            if exact:
                effects = mix - tracks["vocals_dry"] - tracks["inst_dry"]
            else:
                effects = tracks["vocal_fx"] + tracks["inst_fx"]

            base = audio.stem
            res = Result()
            main = {
                "vocals": tracks["vocals_dry"],
                "accompaniment": tracks["inst_dry"],
                "effects": effects,
            }
            for i, (name, data) in enumerate(main.items(), 1):
                res.outputs[name] = _write(out_dir / f"{base}_{i}_{name}.wav", data, sr)

            if keep_extras:
                extra = out_dir / "extras"
                extra.mkdir(exist_ok=True)
                for name, key in [
                    ("vocals_with_effects", "vocals_wet"),
                    ("accompaniment_with_effects", "inst_wet"),
                    ("vocal_effects_only", "vocal_fx"),
                    ("accompaniment_effects_only", "inst_fx"),
                ]:
                    res.outputs[name] = _write(extra / f"{base}_{name}.wav", tracks[key], sr)

            recon = sum(main.values())
            res.report = {
                "mode": "3way",
                "effects_method": "residual" if exact else "model",
                "input": str(audio),
                "sample_rate": sr,
                "duration_sec": round(n / sr, 2),
                "models": {"vocal_split": self.vocal_model, "effects_split": DEREVERB_MODEL},
                "energy_share_percent": _energy_share(main),
                "reconstruction_snr_db": _snr(mix, recon),
            }
        _write_report(out_dir / f"{base}_report.json", res)
        return res

    def split_six(self, audio: Path, out_dir: Path) -> Result:
        """보컬 / 드럼 / 베이스 / 기타 / 피아노 / 기타악기 6분리."""
        audio, out_dir = Path(audio), Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        res = Result()
        with tempfile.TemporaryDirectory(prefix="stem_splitter_") as tmp:
            for f in self._run(SIX_STEM_MODEL, audio, Path(tmp)):
                label = _stem_label(f)
                res.outputs[label] = Path(shutil.move(str(f), out_dir / f"{audio.stem}_{label}.wav"))
        res.report = {"mode": "6stem", "input": str(audio), "models": {"stems": SIX_STEM_MODEL}}
        _write_report(out_dir / f"{audio.stem}_report.json", res)
        return res


# ---------------------------------------------------------------------- audio io
def _read(path: Path, target_sr: int | None = None) -> tuple[np.ndarray, int]:
    data, sr = sf.read(str(path), always_2d=True, dtype="float32")
    if target_sr is not None and sr != target_sr:
        data = _resample(data, sr, target_sr)
        sr = target_sr
    return data, sr


def _resample(data: np.ndarray, sr: int, target: int) -> np.ndarray:
    n = int(round(len(data) * target / sr))
    x_old = np.arange(len(data)) / sr
    x_new = np.arange(n) / target
    return np.stack([np.interp(x_new, x_old, data[:, c]) for c in range(data.shape[1])], axis=1).astype(np.float32)


def _match_channels(data: np.ndarray, channels: int) -> np.ndarray:
    if data.shape[1] == channels:
        return data
    if data.shape[1] == 1:
        return np.repeat(data, channels, axis=1)
    return data.mean(axis=1, keepdims=True).repeat(channels, axis=1)


def _write(path: Path, data: np.ndarray, sr: int) -> Path:
    sf.write(str(path), data, sr, subtype="PCM_24")
    return path


def _energy_share(tracks: dict[str, np.ndarray]) -> dict[str, float]:
    energy = {k: float(np.sum(v.astype(np.float64) ** 2)) for k, v in tracks.items()}
    total = sum(energy.values()) or 1.0
    return {k: round(100 * e / total, 2) for k, e in energy.items()}


def _snr(ref: np.ndarray, est: np.ndarray) -> float:
    ref = ref.astype(np.float64)
    noise = np.sum((ref - est) ** 2)
    return round(float(10 * np.log10(np.sum(ref**2) / max(noise, 1e-12))), 2)


def _write_report(path: Path, res: Result) -> None:
    payload = dict(res.report, outputs={k: str(v) for k, v in res.outputs.items()})
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
