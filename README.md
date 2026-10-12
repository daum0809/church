# 주일예배 PDF 자동 만들기 (광염교회)

`templates/base.pdf` (2026-10-11 주일예배 PDF) 디자인을 그대로 쓰고,
**매주 바뀌는 부분만 `weekly.yaml` 에 입력**하면 예배 때 띄울 PDF가 만들어집니다.

## 매주 하는 일 (윈도우)

1. `입력하기.bat` 더블클릭 → 메모장에서 `weekly.yaml` 수정 후 저장
2. `만들기.bat` 더블클릭 → `output/주일예배_YYYY-MM-DD.pdf` 생성, 폴더가 자동으로 열림

(맥/리눅스: `python3 make_worship.py`)

처음 한 번만: [Python 3.10+](https://www.python.org/downloads/) 설치
(설치 화면에서 **Add python.exe to PATH** 체크). 필요한 패키지는 `만들기.bat` 이 알아서 설치합니다.

## 입력하는 항목 (`weekly.yaml`)

| 항목 | 화면 |
|---|---|
| 날짜 | 표지 왼쪽 위 (비우면 다가오는 주일) |
| 입례찬송 장/제목 | 입례 찬송 화면 (`악보: true` 면 악보도) |
| 영광송 장/제목 | 영광송 화면 + 악보 |
| 교독 제목/본문 | 공동기도 화면 + 교독 화면 (인도=흰색, 회중=노란색) |
| 찬송 장/제목 | 찬송 화면 + 악보 |
| 대표기도 이름/직분 | 대표기도 화면 |
| 성경봉독 봉독자/본문/말씀 | 성경봉독 화면 + 절마다 한 화면 (마지막에 "(다같이) 아멘." 자동) |
| 찬양 성가대/곡명/작곡/가사 | 찬양 화면 |
| 말씀 제목/본문/설교자 | 말씀선포 화면 |
| 봉헌찬송 장/제목 | 봉헌 화면 + 악보 |

사도신경, 응답송, 봉헌기도, 교회소식, 주의 기도(635장), 축도, 마침 화면은 원본 그대로입니다.

## 찬송가 악보

악보는 [bibletoppt.com 배경없음 찬송가](https://bibletoppt.com/hymn/hymnppt/no-bg) 에서 가져옵니다.

1. `hymns/076.pdf` 처럼 한 번 만든 악보는 저장해 두고 다시 씁니다.
   (원본 PDF에 있던 76·218·478·635장은 이미 들어 있습니다.)
2. 없으면 사이트에서 자동으로 찾아 받습니다.
3. 자동 다운로드가 안 되면 사이트에서 직접 받은 파일(PPT/PPTX/PDF/ZIP/그림 폴더)을
   `hymns/inbox/` 에 **파일명에 장 번호가 들어가게** 넣고 다시 실행하세요. 예: `hymns/inbox/305장.pptx`

PPT → 그림 변환은 PowerPoint(윈도우, `pip install pywin32` 필요) 또는
[LibreOffice](https://ko.libreoffice.org/) 가 있으면 가장 정확합니다. 둘 다 없어도
`.pptx` 는 슬라이드 속 그림을 꺼내서 만듭니다. 악보 화면은 흰 여백을 잘라 화면에 꽉 차게 맞춥니다.

> 개발 환경에서는 bibletoppt.com 접속이 막혀 있어 자동 다운로드는 실제 사이트로 시험하지 못했습니다.
> 실패하면 위 3번 방법으로 넣으면 되고, 오류 메시지에 방법이 나옵니다.

## 글꼴

원본 디자인 글꼴은 **TT옴니고딕(TTOmniGothicM)** 입니다. 이 글꼴이 PC에 설치돼 있으면
자동으로 그 글꼴을 쓰고, 없으면 함께 들어 있는 무료 글꼴 Pretendard(OFL)로
글자 높이·위치를 맞춰 씁니다. 다른 글꼴을 쓰려면 `weekly.yaml` 의 `설정 > 글꼴` 에 파일 경로를 적으세요.

## 디자인을 바꾸고 싶을 때

`templates/base.pdf` 를 새 디자인 PDF로 바꾸고, 페이지 순서가 달라지면
`worship/layout.py` 의 페이지 번호만 맞춰 주면 됩니다.

## 파일 구성

```
weekly.yaml          매주 입력
make_worship.py      실행 파일
만들기.bat / 입력하기.bat
worship/build.py     화면별로 글자 바꾸기
worship/hymns.py     찬송가 악보 받기/변환/저장
worship/text.py      글꼴, 글자 지우기/쓰기
worship/layout.py    원본 PDF 페이지 번호
templates/base.pdf   원본 디자인
hymns/               악보 저장소 (inbox/ 에 직접 받은 파일)
fonts/               Pretendard (SIL OFL 1.1)
```
