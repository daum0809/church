"""templates/base.pdf (2026-10-11 주일예배) 페이지 구성.

페이지 번호는 0부터 시작합니다. 디자인을 바꿔서 base.pdf 를 교체하면
이 파일의 번호만 맞춰 주면 됩니다.
"""

PAGE_W, PAGE_H = 1440, 810

COVER = 0                 # 표지 (왼쪽 위 날짜)
ENTRANCE_TITLE = 1        # 입례 찬송 제목
CREED = [2, 3]            # 사도신경 (고정)
GLORIA_TITLE = 4          # 영광송 제목
GLORIA_SHEETS = range(5, 11)
READING_TITLE = 11        # 공동기도(교독) 제목
READING_SLIDE = 12        # 교독 본문 슬라이드 틀
HYMN_TITLE = 16           # 찬송 제목
HYMN_SHEETS = range(17, 23)
PRAYER = 23               # 대표기도
SCRIPTURE_TITLE = 24      # 성경봉독 제목
SCRIPTURE_SLIDE = 25      # 성경 본문 슬라이드 틀
RESPONSE = 27             # 응답송 (고정)
ANTHEM = 28               # 찬양 (성가대)
SERMON = 29               # 말씀선포
BLANK = 30                # 빈 화면 (설교 중)
OFFERTORY_TITLE = 31      # 봉헌 찬송 제목
OFFERTORY_SHEETS = range(32, 41)
CLOSING = list(range(41, 49))  # 봉헌기도, 교회소식, 주의기도(+악보), 축도, 마침

# 원본 PDF 안에 이미 들어 있는 찬송가 악보 (처음 실행할 때 캐시로 저장)
SEED_HYMNS = {
    76: GLORIA_SHEETS,
    478: HYMN_SHEETS,
    218: OFFERTORY_SHEETS,
    635: range(44, 47),
}
