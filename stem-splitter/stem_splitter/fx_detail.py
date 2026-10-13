"""이펙트 상세 분리 (--mode fx-detail).

원곡 위에 "덧붙는" 소리는 종류별로 따로 떼어낸다.

  원곡 ─[관중]─┬─ ⑥ 관중·박수
               └─ 음악 ─[보컬 분리]─┬─ 보컬 ─[리버브]─[에코]─ 마른 보컬 ─[노이즈]─[리드/백보컬]
                                    │                                  │         ├─ ① 리드 보컬
                                    │                                  │         └─ ② 백보컬·화음
                                    │                                  └─ ⑦ 노이즈
                                    └─ 반주 ─[리버브]─[에코]─ ③ 반주

  ④ 리버브     = 보컬 리버브 + 반주 리버브
  ⑤ 에코·딜레이 = 보컬 에코   + 반주 에코
  리버브 모델을 에코 모델보다 먼저 건다 (반대로 하면 에코 모델이 리버브까지 가져간다).

원음 자체를 바꾸는 이펙트(오토튠·컴프레서·디스토션·코러스 등)는 분리가 불가능하므로
fx_analysis 로 사용 여부와 강도만 추정해 리포트에 남긴다.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from . import fx_analysis
from .pipeline import (
    Result,
    Splitter,
    _energy_share,
    _match_channels,
    _read,
    _snr,
    _write,
    _write_report,
)

# MDX 관중 모델은 스튜디오 녹음에서도 음악 일부를 관중으로 오인해(테스트 곡 5%) roformer 사용
CROWD_MODEL = "mel_band_roformer_crowd_aufr33_viperx_sdr_8.7144.ckpt"
# 리버브 전용 모델을 먼저, 에코 모델을 나중에 건다. 에코 모델을 먼저 걸면 리버브까지 에코로 가져가
# 리버브 트랙이 거의 비었다(정답을 아는 테스트 곡 기준 리버브 검출량 0.011 → 0.092, 정답 0.25).
# 주의: 일부 roformer 디리버브 모델은 출력 파일 이름이 내용과 반대로 붙어 나와 쓰지 않는다.
REVERB_MODEL = "UVR-De-Reverb-aufr33-jarredou.pth"  # 출력: "dry" / "no dry"(=리버브)
ECHO_MODEL = "UVR-De-Echo-Normal.pth"
# 화이트노이즈를 넣은 테스트에서 노이즈 검출: UVR-DeNoise-Lite 15% → 이 모델 62% (상관 0.55 → 0.87)
NOISE_MODEL = "denoise_mel_band_roformer_aufr33_sdr_27.9959.ckpt"  # 출력: "dry" / "other"(=노이즈)
KARAOKE_MODEL = "UVR_MDXNET_KARA_2.onnx"


def split_fx_detail(sp: Splitter, audio: Path, out_dir: Path, keep_extras: bool = True) -> Result:
    audio, out_dir = Path(audio), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="stem_splitter_fx_") as tmp:
        w = Path(tmp)
        crowd, music = sp._pair(CROWD_MODEL, audio, w / "a_crowd", "crowd")
        vocals_wet, inst_wet = sp._split_vocals(music, w)

        paths = {"crowd": crowd, "vocals_wet": vocals_wet, "inst_wet": inst_wet}
        for src, wet in (("vocal", vocals_wet), ("inst", inst_wet)):
            rev, no_rev = sp._pair(REVERB_MODEL, wet, w / f"b_{src}_reverb", "no dry")
            echo, dry = sp._pair(ECHO_MODEL, no_rev, w / f"c_{src}_echo", "echo")
            paths |= {f"{src}_echo": echo, f"{src}_reverb": rev, f"{src}_dry": dry}

        noise, clean = sp._pair(NOISE_MODEL, paths["vocal_dry"], w / "d_noise", "other")
        lead, backing = sp._pair(KARAOKE_MODEL, clean, w / "e_karaoke", "vocals")
        paths |= {"noise": noise, "lead": lead, "backing": backing}

        mix, sr = _read(audio)
        tr = {k: _read(p, sr)[0] for k, p in paths.items()}
        n = min(len(mix), *(len(t) for t in tr.values()))
        mix = mix[:n]
        tr = {k: _match_channels(v[:n], mix.shape[1]) for k, v in tr.items()}

    main = {
        "lead_vocals": tr["lead"],
        "backing_vocals": tr["backing"],
        "accompaniment": tr["inst_dry"],
        "reverb": tr["vocal_reverb"] + tr["inst_reverb"],
        "echo_delay": tr["vocal_echo"] + tr["inst_echo"],
        "crowd": tr["crowd"],
        "noise": tr["noise"],
    }
    base = audio.stem
    res = Result()
    for i, (name, data) in enumerate(main.items(), 1):
        res.outputs[name] = _write(out_dir / f"{base}_{i}_{name}.wav", data, sr)
    if keep_extras:
        extra = out_dir / "extras"
        extra.mkdir(exist_ok=True)
        for key in ("vocal_reverb", "inst_reverb", "vocal_echo", "inst_echo", "vocals_wet", "inst_wet"):
            res.outputs[key] = _write(extra / f"{base}_{key}.wav", tr[key], sr)

    res.report = {
        "mode": "fx-detail",
        "input": str(audio),
        "sample_rate": sr,
        "duration_sec": round(n / sr, 2),
        "models": {
            "crowd": CROWD_MODEL, "vocal_split": sp.vocal_model, "echo": ECHO_MODEL,
            "reverb": REVERB_MODEL, "noise": NOISE_MODEL, "lead_backing": KARAOKE_MODEL,
        },
        "energy_share_percent": _energy_share(main),
        "reconstruction_snr_db": _snr(mix, sum(main.values())),
        "effect_analysis": fx_analysis.analyze(
            mix=mix, lead=tr["lead"], accompaniment=tr["inst_dry"], sr=sr,
            reverb={"vocals": _ratio(tr["vocal_reverb"], tr["vocals_wet"]),
                    "accompaniment": _ratio(tr["inst_reverb"], tr["inst_wet"])},
            echo={"vocals": _ratio(tr["vocal_echo"], tr["vocals_wet"]),
                  "accompaniment": _ratio(tr["inst_echo"], tr["inst_wet"])},
        ),
    }
    _write_report(out_dir / f"{base}_report.json", res)
    return res


def _ratio(part: np.ndarray, whole: np.ndarray) -> float:
    """part 가 whole 에서 차지하는 에너지 비율(0~1)."""
    w = float(np.sum(whole.astype(np.float64) ** 2))
    return float(np.sum(part.astype(np.float64) ** 2)) / w if w > 0 else 0.0
