"""다운로드 버튼 코드 전체를 출력합니다. (임시 조사용)"""

import re

import requests

BASE = "https://bibletoppt.com"
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"})
html = s.get(f"{BASE}/hymn/hymnppt/no-bg/064", timeout=40).text
for c in sorted(set(re.findall(r"/_next/static/chunks/[\w\-]+\.js", html))):
    if "d2e2826fe763042c" in c:
        js = s.get(BASE + c, timeout=40).text
        # 긴 한 줄을 읽기 좋게 나눠서 출력
        print(re.sub(r"(;|\},|\{)", r"\1\n", js))
