"""분리할 수 없는 이펙트의 사용 여부·강도 추정.

오토튠·컴프레서·코러스(스테레오 확장)·EQ 처럼 원음 자체를 바꾸는 이펙트는 트랙으로 떼어낼 수 없다.
대신 분리된 리드 보컬·반주·원곡에서 신호 특성을 재서 "얼마나 걸렸는지"를 추정한다.
모든 값은 추정치이며, 판정 근거(basis)와 신뢰도(confidence)를 함께 남긴다.
"""

from __future__ import annotations

import numpy as np

LEVELS = ("없음", "약함", "보통", "강함")


def _level(value: float, cuts: tuple[float, float, float], higher_is_more: bool = True) -> str:
    """cuts = (약함, 보통, 강함) 경계."""
    if not higher_is_more:
        value, cuts = -value, tuple(-c for c in cuts)
    return LEVELS[sum(value >= c for c in cuts)]


def _mono(x: np.ndarray) -> np.ndarray:
    return x.mean(axis=1) if x.ndim == 2 else x


def _frame_db(x: np.ndarray, sr: int, win_sec: float) -> np.ndarray:
    hop = max(1, int(sr * win_sec))
    n = len(x) // hop
    if n == 0:
        return np.array([])
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop).astype(np.float64) ** 2, axis=1))
    return 20 * np.log10(rms + 1e-12)


def _active(db: np.ndarray, below_peak: float = 30.0) -> np.ndarray:
    """가장 큰 구간보다 below_peak dB 이상 작은(=무음) 프레임 제외."""
    return db[db > (db.max() - below_peak)] if db.size else db


# ------------------------------------------------------------------ 개별 지표
def autotune(lead: np.ndarray, sr: int, max_sec: float = 60.0) -> dict:
    """음정 보정: 음정이 반음 격자에 얼마나 '딱 붙어' 있는지.

    자연스러운 노래는 음정이 반음 사이를 흔들리며 지나가고, 오토튠은 격자에 고정된다.
    보컬이 가장 큰 구간 max_sec 초만 분석한다(pyin 은 느리다).
    """
    import librosa

    y = _mono(lead).astype(np.float32)
    target_sr = 16000
    y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
    y = _loudest_span(y, target_sr, max_sec)
    f0, voiced, _ = librosa.pyin(y, fmin=70, fmax=1000, sr=target_sr, frame_length=1024, hop_length=160)
    f0 = f0[voiced & np.isfinite(f0)]
    if f0.size < 100:
        return {"level": "판정 불가", "basis": "리드 보컬의 음정 구간이 너무 짧음", "confidence": "낮음"}
    cents = 1200 * np.log2(f0 / 440.0)
    # 곡 전체 튜닝 오프셋(A=440 에서 벗어난 정도)을 원형 평균으로 제거
    ang = 2 * np.pi * cents / 100
    offset = 100 * np.angle(np.mean(np.exp(1j * ang))) / (2 * np.pi)
    dev = (cents - offset + 50) % 100 - 50
    snap = float(np.mean(np.abs(dev) <= 10))  # 균일 분포면 0.2
    return {
        "level": _level(snap, (0.35, 0.45, 0.6)),
        "value": {"semitone_snap_ratio": round(snap, 3), "median_abs_cents": round(float(np.median(np.abs(dev))), 1)},
        "basis": "음정이 반음 ±10센트 안에 머문 비율 (자연 발성 약 0.2~0.35, 강한 오토튠 0.6 이상)",
        "confidence": "중간",
    }


def compression(lead: np.ndarray, sr: int) -> dict:
    """보컬 컴프레서: 짧은 구간 음량의 흔들림(표준편차)이 작을수록 강하게 눌린 것."""
    db = _active(_frame_db(_mono(lead), sr, 0.4))
    if db.size < 10:
        return {"level": "판정 불가", "basis": "리드 보컬 구간이 너무 짧음", "confidence": "낮음"}
    spread = float(np.std(db))
    return {
        "level": _level(spread, (6.0, 4.0, 2.5), higher_is_more=False),
        "value": {"loudness_spread_db": round(spread, 2)},
        "basis": "0.4초 단위 음량의 표준편차 (작을수록 압축이 강함)",
        "confidence": "중간",
    }


def mastering_limiter(mix: np.ndarray, sr: int) -> dict:
    """원곡 전체의 리미터·마스터링 압축: 크레스트 팩터(피크 대비 평균 음량)."""
    x = _mono(mix).astype(np.float64)
    rms = np.sqrt(np.mean(x**2)) + 1e-12
    crest = float(20 * np.log10(np.max(np.abs(x)) / rms + 1e-12))
    peak = np.max(np.abs(x))
    clipped = np.abs(x) >= 0.999 * peak
    runs = int(np.sum(clipped[2:] & clipped[1:-1] & clipped[:-2])) if peak >= 0.98 else 0
    return {
        "level": _level(crest, (14.0, 11.0, 8.0), higher_is_more=False),
        "value": {"crest_factor_db": round(crest, 2), "clipped_runs": runs},
        "basis": "피크/평균 음량 차이 (작을수록 강하게 눌린 마스터링), 연속 3샘플 이상 최대치 = 클리핑",
        "confidence": "높음",
    }


def stereo_widening(lead: np.ndarray) -> dict:
    """코러스·더블링·스테레오 확장: 리드 보컬은 보통 가운데(모노)라 좌우 차이가 크면 확장 이펙트."""
    if lead.ndim != 2 or lead.shape[1] < 2:
        return {"level": "판정 불가", "basis": "모노 음원", "confidence": "낮음"}
    mid = (lead[:, 0] + lead[:, 1]) / 2
    side = (lead[:, 0] - lead[:, 1]) / 2
    ratio = float(np.sum(side.astype(np.float64) ** 2) / (np.sum(mid.astype(np.float64) ** 2) + 1e-12))
    return {
        "level": _level(ratio, (0.05, 0.15, 0.35)),
        "value": {"side_to_mid_ratio": round(ratio, 3)},
        "basis": "리드 보컬의 좌우 차이 성분 / 가운데 성분 에너지 비율",
        "confidence": "중간",
    }


def tone(lead: np.ndarray, sr: int) -> dict:
    """EQ 성향: 스펙트럼 무게중심으로 밝음/어두움만 표시 (EQ 사용 여부 자체는 알 수 없음)."""
    import librosa

    y = _mono(lead).astype(np.float32)
    cent = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    rms = librosa.feature.rms(y=y)[0]
    n = min(len(cent), len(rms))
    cent, rms = cent[:n], rms[:n]
    loud = rms > rms.max() * 0.1 if rms.size else rms
    hz = float(np.median(cent[loud])) if np.any(loud) else 0.0
    label = "어두움" if hz < 1500 else "보통" if hz < 3000 else "밝음"
    return {
        "level": label,
        "value": {"spectral_centroid_hz": round(hz)},
        "basis": "리드 보컬 스펙트럼 무게중심 (EQ 를 걸었는지는 원본이 없어 알 수 없고 결과 음색만 표시)",
        "confidence": "낮음",
    }


def _loudest_span(y: np.ndarray, sr: int, sec: float) -> np.ndarray:
    span = int(sr * sec)
    if len(y) <= span:
        return y
    hop = sr
    energy = np.convolve(y.astype(np.float64) ** 2, np.ones(hop), mode="valid")[::hop]
    k = max(1, span // hop)
    window = np.convolve(energy, np.ones(k), mode="valid")
    start = int(np.argmax(window)) * hop
    return y[start : start + span]


# ------------------------------------------------------------------ 종합
def analyze(mix, lead, accompaniment, sr, reverb: dict, echo: dict) -> dict:
    def fx_level(ratios: dict) -> dict:
        return {
            src: {"level": _level(r, (0.03, 0.10, 0.25)), "energy_ratio": round(r, 3)}
            for src, r in ratios.items()
        }

    def safe(fn, *a):
        try:
            return fn(*a)
        except Exception as e:  # 분석 실패가 분리 결과를 막지 않도록
            return {"level": "판정 불가", "basis": f"분석 오류: {e}", "confidence": "낮음"}

    return {
        "separated": {
            "리버브": fx_level(reverb),
            "에코·딜레이": fx_level(echo),
        },
        "estimated_only": {
            "오토튠(음정 보정)": safe(autotune, lead, sr),
            "보컬 컴프레서": safe(compression, lead, sr),
            "마스터링 리미터·클리핑": safe(mastering_limiter, mix, sr),
            "코러스·더블링·스테레오 확장": safe(stereo_widening, lead),
            "EQ 음색": safe(tone, lead, sr),
        },
        "not_detectable": {
            "디스토션·오버드라이브": "악기 고유의 음색과 구분할 수 없어 판정하지 않음",
            "플랜저·페이저": "신뢰할 만한 판정 방법이 없어 판정하지 않음",
        },
        "note": "estimated_only 항목은 분리가 아니라 신호 특성으로 추정한 값입니다.",
    }
