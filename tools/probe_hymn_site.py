"""bibletoppt.com 의 찬송가(배경 없음) 목록 구조를 살펴봅니다. (임시 조사용)"""

import re
import sys
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

LIST = "https://bibletoppt.com/hymn/hymnppt/no-bg"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.items.append(("a", a["href"], a.get("title", ""), {k: v for k, v in a.items() if k.startswith("data-")}))
        if tag == "script" and a.get("src"):
            self.scripts.append(a["src"])
        if tag in ("button", "form", "iframe"):
            self.items.append((tag, a.get("action") or a.get("src") or "", a.get("id", ""), {k: v for k, v in a.items() if k.startswith("data-") or k == "onclick"}))


def show(r, label):
    print(f"\n==== {label}: {r.status_code} {r.url}")
    for k in ("content-type", "content-length", "content-disposition", "access-control-allow-origin",
              "x-frame-options", "server", "cf-ray", "location"):
        if k in r.headers:
            print(f"  {k}: {r.headers[k]}")


s = requests.Session()
s.headers.update(UA)
r = s.get(LIST, timeout=40)
show(r, "목록 페이지")
html = r.text
print("글자 수:", len(html))
print("--- 본문 앞부분 ---")
print(re.sub(r"\s+", " ", html)[:2500])

p = Links()
p.feed(html)
print("\n--- 링크/버튼 (앞 80개) ---")
for it in p.items[:80]:
    print(it)
print("총", len(p.items), "개")
print("--- 스크립트 ---")
for sc in p.scripts[:20]:
    print(sc)

# 파일 링크처럼 보이는 것
files = [urljoin(LIST, h) for _, h, _, _ in p.items if re.search(r"\.(pptx?|zip|pdf|png|jpg)(\?|$)", h, re.I)]
print("\n--- 파일 링크 후보 ---", len(files))
for f in files[:10]:
    print(f)

# 다른 곳에 나오는 URL/엔드포인트 단서
print("\n--- 글 속 URL 단서 ---")
for m in sorted(set(re.findall(r"""["'](/[A-Za-z0-9_\-./?=&%]{4,120})["']""", html)))[:60]:
    print(m)

# 목록 중 하나를 따라가 보기: 숫자 64 가 들어간 링크
for label, num in (("64장", "64"),):
    cand = [urljoin(LIST, h) for _, h, t, _ in p.items if re.search(rf"(?<!\d)0*{num}(?!\d)", h + " " + t)]
    print(f"\n--- {label} 후보 링크 ---", cand[:10])
    for u in cand[:3]:
        try:
            rr = s.get(u, timeout=40)
            show(rr, f"{label} 후보")
            ctype = rr.headers.get("content-type", "")
            if "html" in ctype:
                q = Links(); q.feed(rr.text)
                print("   페이지 속 링크:", [(a, b) for _, a, b, _ in q.items][:40])
                print("   앞부분:", re.sub(r"\s+", " ", rr.text)[:800])
            else:
                print("   파일 크기:", len(rr.content))
        except Exception as e:
            print("   오류:", e)

# 브라우저(다른 출처)에서 파일을 직접 받을 수 있는지: CORS 확인
for u in files[:2]:
    rr = s.get(u, headers={"Origin": "https://daum0809.github.io"}, timeout=60, stream=True)
    show(rr, "CORS 확인")
sys.exit(0)
