# church-worship-automation

## 🎚 stem_splitter — 노래를 **보컬 / 반주 / 이펙트** 3가지로 분리

보컬·반주 2분리는 흔합니다. 이 도구의 핵심은 **이펙트(리버브·에코·딜레이 같은 공간계 효과)까지
따로 떼어내는 3분리**입니다. 필요하면 악기별 6분리도 됩니다.

| 모드 | 결과 |
|---|---|
| `3way` (기본) | ① 보컬(효과 제거된 마른 목소리) ② 반주(효과 제거된 악기) ③ **이펙트**(리버브·에코만) |
| `6stem` | 보컬 / 드럼 / 베이스 / 기타 / 피아노 / 기타악기(other) |
| `all` | 위 두 가지 모두 |

### 동작 원리 (3way)

```
원곡 ─[BS-Roformer 보컬 분리]─┬─ 보컬(효과 포함) ─[DeEcho-DeReverb]─┬─ ① 마른 보컬
                               │                                    └─ 보컬 이펙트 ─┐
                               └─ 반주(효과 포함) ─[DeEcho-DeReverb]─┬─ ② 마른 반주   ├─ ③ 이펙트
                                                                    └─ 반주 이펙트 ─┘
```

`extras/` 폴더에는 효과가 남아 있는 보컬·반주와 보컬 이펙트·반주 이펙트를 각각 따로 저장합니다
(예: "리버브 낀 보컬만", "반주의 잔향만").

### 설치

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
ffmpeg 가 필요합니다 (mp3/m4a 읽기). 처음 실행할 때 AI 모델(약 0.9GB)을 자동으로 받습니다.

### 사용법

```bash
python -m stem_splitter 노래.mp3                    # 보컬 / 반주 / 이펙트
python -m stem_splitter 노래.mp3 --mode 6stem       # 악기별
python -m stem_splitter 노래.mp3 --mode all         # 둘 다
python -m stem_splitter 찬양폴더/ -o 결과폴더         # 폴더 일괄 처리
python -m stem_splitter 노래.mp3 --exact            # 세 트랙 합 = 원곡 (정확 복원)
python -m stem_splitter 노래.mp3 --fast             # 빠른 모델
```

결과 (`separated/노래/`):
```
노래_1_vocals.wav          ① 보컬
노래_2_accompaniment.wav   ② 반주
노래_3_effects.wav         ③ 이펙트
extras/                    효과 포함 보컬·반주, 보컬 이펙트만, 반주 이펙트만
노래_report.json           에너지 비율, 복원 정확도(SNR)
```

### 참고
- **속도**: CPU 에서 3분 곡 기준 수십 분 걸릴 수 있습니다. NVIDIA GPU 가 있으면
  `pip install "audio-separator[gpu]"` 로 바꾸면 수십 배 빨라집니다.
- **`--exact`**: 기본값은 이펙트를 AI 모델이 직접 뽑습니다(더 깨끗함). `--exact` 는
  이펙트 = 원곡 − 보컬 − 반주 로 계산해서 세 트랙을 합치면 원곡과 정확히 같아집니다
  (대신 분리 잔여물이 이펙트에 섞임).
- **저작권**: 분리한 음원을 예배·연습용으로 쓰는 것과 별개로, 재배포·공연 시에는 원곡 저작권 및
  교회 저작권 라이선스(CCLI 등) 범위를 확인하세요.
