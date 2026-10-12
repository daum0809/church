"""bibletoppt.com 의 다운로드 버튼이 넘기는 값과 동작을 살펴봅니다. (임시 조사용)"""

import re

import requests

BASE = "https://bibletoppt.com"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Referer": BASE + "/hymn/hymnppt/no-bg/064"}
s = requests.Session()
s.headers.update(UA)

html = s.get(f"{BASE}/hymn/hymnppt/no-bg/064", timeout=40).text
print("== 페이지가 컴포넌트에 넘기는 값 (design / number 주변) ==")
seen = 0
for m in re.finditer(r'design', html):
    a, b = max(0, m.start() - 160), min(len(html), m.end() + 260)
    print("...", html[a:b].replace("\\\"", "\"")[:420])
    seen += 1
    if seen >= 6:
        break

print("\n== 버튼 클릭 동작 코드 ==")
shown = 0
for c in sorted(set(re.findall(r"/_next/static/chunks/[\w\-]+\.js", html))):
    js = s.get(BASE + c, timeout=40).text
    for m in re.finditer(r"readyColor|downloadUrl|URLSearchParams|\.blob\(\)|createObjectURL", js):
        a, b = max(0, m.start() - 900), min(len(js), m.end() + 900)
        print(f"\n===== {c} @ {m.start()} ({m.group(0)}) =====")
        print(js[a:b])
        shown += 1
        break
    if shown >= 2:
        break
