"""bibletoppt.com 의 '/api/download' 응답을 살펴봅니다. (임시 조사용)"""

import re

import requests

BASE = "https://bibletoppt.com"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Referer": BASE + "/hymn/hymnppt/no-bg/064"}
s = requests.Session()
s.headers.update(UA)

html = s.get(f"{BASE}/hymn/hymnppt/no-bg/064", timeout=40).text
# 버튼 컴포넌트 코드 (endpoint 를 어떻게 부르는지)
for c in sorted(set(re.findall(r"/_next/static/chunks/[\w\-]+\.js", html))):
    js = s.get(BASE + c, timeout=40).text
    for m in re.finditer(r"config\.endpoint|\.endpoint[,)]|endpoint:", js):
        a, b = max(0, m.start() - 300), min(len(js), m.end() + 1400)
        print(f"\n===== {c} @ {m.start()} =====")
        print(js[a:b])
        break


def show(label, r):
    print(f"\n#### {label}: {r.status_code} {r.url}")
    for k in ("content-type", "content-length", "content-disposition", "access-control-allow-origin", "location"):
        if k in r.headers:
            print(f"  {k}: {r.headers[k]}")
    body = r.content[:600]
    try:
        print("  body:", body.decode("utf-8")[:600])
    except UnicodeDecodeError:
        print("  body(bytes):", body[:60], "... 총", len(r.content), "바이트")


for params in ({"type": "hymn", "design": "no-bg", "number": "064"},
               {"type": "hymn", "design": "no-bg", "number": "64"}):
    r = s.get(BASE + "/api/download", params=params, timeout=60, allow_redirects=False)
    show(f"GET {params}", r)
r = s.post(BASE + "/api/download", json={"type": "hymn", "design": "no-bg", "number": 64}, timeout=60, allow_redirects=False)
show("POST json", r)
