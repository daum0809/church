"""찬송가 자동 다운로드를 실제 사이트로 시험합니다. (임시 조사용)"""

import json
import sys
import time
import zipfile
from pathlib import Path

import pymupdf
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from worship import hymns  # noqa: E402

OUT = Path("probe_out")
OUT.mkdir(exist_ok=True)

# 1) 브라우저에서 바로 받을 수 있는지 (CORS)
s = requests.Session()
s.headers.update({"User-Agent": hymns.USER_AGENT, "Origin": "https://daum0809.github.io",
                  "Referer": hymns.SITE + "/hymn/hymnppt/no-bg/064"})
time.sleep(hymns.WAIT_SECONDS)
r = s.get(hymns.API_URL, params={"action": "token", "type": "hymn", "design": "no-bg", "number": "064"}, timeout=30)
print("토큰 요청:", r.status_code, dict((k, v) for k, v in r.headers.items() if k.lower().startswith("access-control") or k.lower() in ("content-type", "vary")))
print("  본문:", r.text[:200])
tok = r.json().get("token")
r2 = s.get(hymns.API_URL, params={"token": tok}, timeout=120)
print("파일 요청:", r2.status_code, dict((k, v) for k, v in r2.headers.items() if k.lower().startswith("access-control") or k.lower() in ("content-type", "content-disposition", "content-length")))
print("  첫 바이트:", r2.content[:8], "크기:", len(r2.content))
op = s.options(hymns.API_URL, headers={"Access-Control-Request-Method": "GET", "Origin": "https://daum0809.github.io"}, timeout=30)
print("OPTIONS:", op.status_code, dict((k, v) for k, v in op.headers.items() if k.lower().startswith("access-control")))

# 2) 실제 프로그램 코드로 받아서 PDF 로 바꾸기
for num in (43, 64):
    t0 = time.time()
    print(f"\n==== 찬송가 {num}장 ====")
    try:
        doc = hymns.get_hymn(num, print)
    except Exception as e:  # noqa: BLE001
        print("실패:", type(e).__name__, e)
        continue
    print(f"변환 완료 {time.time() - t0:.1f}초, PDF {len(doc)}쪽")
    src = next(iter(sorted(hymns.INBOX.glob(f"{num:03d}.*"))), None)
    if src:
        print("받은 파일:", src.name, src.stat().st_size, "바이트")
        if src.suffix == ".pptx":
            with zipfile.ZipFile(src) as z:
                slides = sorted(n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
                media = [n for n in z.namelist() if n.startswith("ppt/media/")]
                print(f"  슬라이드 {len(slides)}개, 그림 {len(media)}개:", media[:6])
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=20)
        dark = sum(1 for v in pix.samples[::3] if v < 128) / (len(pix.samples) / 3)
        print(f"  {i + 1}쪽: 어두운 픽셀 {dark * 100:.1f}%  글자 {len(page.get_text().strip())}자  그림 {len(page.get_images())}개")
    out_pdf = OUT / f"h{num:03d}.pdf"
    doc.save(out_pdf)
    doc[0].get_pixmap(dpi=45).save(OUT / f"h{num:03d}_p1.png")
    if src:
        (OUT / f"h{num:03d}{src.suffix}").write_bytes(src.read_bytes())
print("\n결과 파일:", sorted(p.name for p in OUT.iterdir()))
