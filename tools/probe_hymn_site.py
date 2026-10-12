"""bibletoppt.com 의 '/api/download' 사용법을 살펴봅니다. (임시 조사용)"""

import re

import requests

BASE = "https://bibletoppt.com"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
s = requests.Session()
s.headers.update(UA)

html = s.get(f"{BASE}/hymn/hymnppt/no-bg/064", timeout=40).text
chunks = sorted(set(re.findall(r"/_next/static/chunks/[\w\-]+\.js", html)))
for c in chunks:
    js = s.get(BASE + c, timeout=40).text
    for m in re.finditer(r"/api/download", js):
        a, b = max(0, m.start() - 700), min(len(js), m.end() + 700)
        print(f"\n===== {c} @ {m.start()} =====")
        print(js[a:b])
