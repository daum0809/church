"""bibletoppt.com 의 찬송가 상세 페이지에서 파일 받는 방법을 살펴봅니다. (임시 조사용)"""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

BASE = "https://bibletoppt.com"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
s = requests.Session()
s.headers.update(UA)


def show(r, label):
    print(f"\n==== {label}: {r.status_code} {r.url}")
    for k in ("content-type", "content-length", "content-disposition", "access-control-allow-origin",
              "cache-control", "server", "location"):
        if k in r.headers:
            print(f"  {k}: {r.headers[k]}")


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out = []
        self.text = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self._skip += 1
        if tag in ("a", "button", "form", "iframe", "embed", "object", "source", "img", "link"):
            keep = {k: v for k, v in a.items() if k in ("href", "src", "action", "download", "id", "class", "title",
                                                          "onclick", "type", "rel", "data-url", "data-file")
                    or k.startswith("data-")}
            if tag != "link" or a.get("rel") not in ("stylesheet", "preload"):
                self.out.append((tag, keep))

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.text.append(data.strip())


for num in ("064", "001"):
    url = f"{BASE}/hymn/hymnppt/no-bg/{num}"
    r = s.get(url, timeout=40)
    show(r, f"상세 {num}")
    html = r.text
    t = Tags(); t.feed(html)
    print("--- 화면 글자 ---")
    print(" | ".join(t.text)[:1500])
    print("--- 태그 ---")
    for tag, a in t.out:
        if tag == "img" and "thumbnails" not in str(a):
            continue
        print(tag, a)
    print("--- 파일/API 단서 (HTML) ---")
    for m in sorted(set(re.findall(r"""[\w./:%\-]*(?:\.pptx?|\.zip|\.pdf|/api/[\w./\-?=&%]*|download[\w./\-?=&%]*)""", html, re.I)))[:40]:
        print(m)
    if num == "064":
        chunks = sorted(set(re.findall(r"/_next/static/chunks/[\w\-]+\.js", html)))
        print("--- JS 조각 검사 ---", len(chunks))
        for c in chunks:
            js = s.get(BASE + c, timeout=40).text
            hits = set()
            for m in re.finditer(r"""["'`]([^"'`]{0,120}(?:\.pptx?|\.zip|/api/[^"'`]{0,80}|download[^"'`]{0,80}|\.pdf)[^"'`]{0,60})["'`]""", js, re.I):
                hits.add(m.group(1)[:200])
            if hits:
                print("  ", c, len(js))
                for h in sorted(hits)[:25]:
                    print("      ", h)

# 자주 쓰는 파일 주소 모양 몇 가지를 직접 확인
for path in ("/hymn/hymnppt/no-bg/064/download", "/api/hymn/download?num=64&type=no-bg",
             "/downloads/hymn/no-bg/064.pptx", "/files/hymn/no-bg/064.pptx", "/api/download/hymn/no-bg/064"):
    try:
        r = s.get(BASE + path, timeout=30, allow_redirects=False)
        print(path, r.status_code, r.headers.get("content-type"), r.headers.get("location", ""))
    except Exception as e:
        print(path, "오류", e)
