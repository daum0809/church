"""찬송가 악보 슬라이드 준비.

순서:
  1. hymns/076.pdf 처럼 이미 만들어 둔 캐시가 있으면 그대로 사용
  2. hymns/inbox/ 에 직접 받아 둔 파일(파일명에 장 번호 포함)이 있으면 변환
  3. bibletoppt.com (배경 없는 찬송가 PPT) 에서 자동 다운로드 후 변환

변환 결과는 hymns/NNN.pdf 로 저장되어 다음부터는 바로 쓰입니다.
"""

import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import pymupdf

from . import layout

from .paths import HYMN_DIR, INBOX

SITE = "https://bibletoppt.com"
LIST_URL = SITE + "/hymn/hymnppt/no-bg"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
SLIDE_EXT = {".ppt", ".pptx", ".pdf", ".zip"} | IMAGE_EXT


ALLOW_DOWNLOAD = True  # 브라우저(핸드폰) 버전에서는 False
RETRY_AFTER = 600  # 자동 다운로드에 실패한 곡은 10분 동안 다시 시도하지 않음
_FAILED = {}


class HymnError(Exception):
    pass


def cache_path(num):
    return HYMN_DIR / f"{int(num):03d}.pdf"


def seed_from_template(base):
    """원본 PDF 에 들어 있던 악보를 캐시로 저장 (없을 때만)."""
    HYMN_DIR.mkdir(exist_ok=True)
    for num, pages in layout.SEED_HYMNS.items():
        path = cache_path(num)
        if path.exists():
            continue
        doc = pymupdf.open()
        doc.insert_pdf(base, from_page=pages[0], to_page=pages[-1])
        doc.save(path, garbage=3, deflate=True)


def get_hymn(num, log=print):
    """찬송가 num 장의 악보 PDF 를 열어서 돌려줍니다."""
    path = cache_path(num)
    if not path.exists():
        source = _from_inbox(num)
        if not source and not ALLOW_DOWNLOAD:
            raise HymnError(f"찬송가 {num}장 악보 파일이 없습니다. 악보 파일(PDF/PPTX)을 올려 주세요.")
        if not source:
            failed_at = _FAILED.get(int(num))
            if failed_at and time.time() - failed_at < RETRY_AFTER:
                raise HymnError(_manual_help(num, "조금 전에 자동 다운로드에 실패했습니다."))
            try:
                source = _download(num, log)
            except HymnError:
                _FAILED[int(num)] = time.time()
                raise
        log(f"  찬송가 {num}장 변환 중: {source.name}")
        _convert(source, path)
    return pymupdf.open(path)


# ---------------------------------------------------------------- 받아 둔 파일

def _number_in_name(num, name):
    return re.search(rf"(?<!\d)0*{int(num)}(?!\d)", name) is not None


def _from_inbox(num):
    if not INBOX.exists():
        return None
    for f in sorted(INBOX.iterdir()):
        if f.suffix.lower() in SLIDE_EXT and _number_in_name(num, f.stem):
            return f
    for d in sorted(INBOX.iterdir()):  # 장 번호 폴더 안에 이미지들
        if d.is_dir() and _number_in_name(num, d.name):
            return d
    return None


# ---------------------------------------------------------------- 자동 다운로드

class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self._href, self._text = [], None, []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self._href, self._text = attrs["href"], []
        for key in ("data-href", "data-url", "data-file", "data-download"):
            if attrs.get(key):
                self.links.append((attrs[key], attrs.get("title", "")))

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._text).strip()))
            self._href = None


def _get(session, url):
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r


def _links(session, url):
    parser = _Links()
    parser.feed(_get(session, url).text)
    return [(urljoin(url, h), t) for h, t in parser.links]


def _is_file_link(href):
    return bool(re.search(r"\.(pptx?|zip|pdf)(\?|$)", href, re.I)) or "download" in href.lower()


def _mentions(num, href, text):
    n = int(num)
    return (re.search(rf"(?<!\d)0*{n}\s*장", text) is not None
            or re.search(rf"(?<![\d])0*{n}(?![\d])", text) is not None
            or re.search(rf"[/=_\-]0*{n}(?![\d])", href) is not None)


def _download(num, log):
    try:
        import requests
    except ImportError as e:
        raise HymnError("requests 패키지가 필요합니다: pip install -r requirements.txt") from e

    log(f"  찬송가 {num}장 악보를 bibletoppt.com 에서 찾는 중...")
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (worship-slides)"
    pages = [LIST_URL]
    for key in ("search", "q", "keyword", "s"):
        pages.append(f"{LIST_URL}?{key}={int(num)}")
    pages += [f"{LIST_URL}?page={p}" for p in range(2, 30)]

    seen = set()
    try:
        for page_url in pages:
            try:
                links = _links(session, page_url)
            except Exception:
                continue
            hits = [(h, t) for h, t in links if h not in seen and _mentions(num, h, t)]
            for href, _ in hits:
                seen.add(href)
                if _is_file_link(href):
                    got = _save(session, href, num)
                    if got:
                        return got
                    continue
                # 곡 상세 페이지 → 그 안의 다운로드 링크
                try:
                    for inner, _ in _links(session, href):
                        if _is_file_link(inner):
                            got = _save(session, inner, num)
                            if got:
                                return got
                except Exception:
                    continue
    except Exception as e:
        raise HymnError(_manual_help(num, f"다운로드 오류: {e}")) from e
    raise HymnError(_manual_help(num, "사이트에서 해당 곡의 파일 링크를 찾지 못했습니다."))


def _save(session, url, num):
    r = session.get(url, timeout=60)
    if r.status_code != 200 or len(r.content) < 1000:
        return None
    name = url.split("?")[0].rstrip("/").split("/")[-1]
    cd = r.headers.get("content-disposition", "")
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd)
    if m:
        name = m.group(1)
    ext = Path(name).suffix.lower()
    if ext not in SLIDE_EXT:
        ctype = r.headers.get("content-type", "")
        ext = (".pptx" if "presentationml" in ctype else ".ppt" if "powerpoint" in ctype
               else ".zip" if "zip" in ctype else ".pdf" if "pdf" in ctype else "")
        if not ext:
            return None
    INBOX.mkdir(parents=True, exist_ok=True)
    path = INBOX / f"{int(num):03d}{ext}"
    path.write_bytes(r.content)
    return path


def _manual_help(num, reason):
    return (f"찬송가 {num}장 악보를 자동으로 받지 못했습니다. ({reason})\n"
            f"  → {LIST_URL} 에서 {num}장 파일(PPT/PPTX/PDF)을 받아\n"
            f"    {INBOX} 폴더에 파일명에 '{num}' 이 들어가게 넣은 뒤 다시 실행하세요.\n"
            f"    (예: {num}장.pptx)")


# ---------------------------------------------------------------- 변환

def _soffice():
    for name in ("soffice", "libreoffice"):
        exe = shutil.which(name)
        if exe:
            return exe
    for p in (r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if Path(p).exists():
            return p
    return None


def _powerpoint_to_pdf(src, out_pdf):
    """윈도우에 PowerPoint 가 있으면 그것으로 PDF 변환."""
    try:
        import win32com.client  # type: ignore
    except ImportError:
        return False
    app = win32com.client.Dispatch("PowerPoint.Application")
    pres = app.Presentations.Open(str(Path(src).resolve()), WithWindow=False)
    try:
        pres.SaveAs(str(Path(out_pdf).resolve()), 32)  # 32 = PDF
    finally:
        pres.Close()
    return True


def _office_to_pdf(src, workdir):
    out_pdf = Path(workdir) / (Path(src).stem + ".pdf")
    exe = _soffice()
    if exe:
        subprocess.run([exe, "--headless", "--convert-to", "pdf", "--outdir", str(workdir), str(src)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
        if out_pdf.exists():
            return out_pdf
    if _powerpoint_to_pdf(src, out_pdf) and out_pdf.exists():
        return out_pdf
    return None


def _pptx_images(src):
    """LibreOffice/PowerPoint 가 없을 때: 각 슬라이드에서 가장 큰 그림을 꺼냅니다."""
    images = []
    with zipfile.ZipFile(src) as z:
        names = z.namelist()
        slides = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.search(r"(\d+)", n.split("/")[-1]).group(1)))
        for slide in slides:
            rels = f"ppt/slides/_rels/{slide.split('/')[-1]}.rels"
            if rels not in names:
                continue
            targets = re.findall(r'Target="([^"]+)"', z.read(rels).decode("utf8"))
            best = None
            for t in targets:
                p = urljoin("ppt/slides/", t)
                if p in names and Path(p).suffix.lower() in IMAGE_EXT:
                    data = z.read(p)
                    if best is None or len(data) > len(best):
                        best = data
            if best:
                images.append(best)
    return images


def _pdf_images(pdf_path):
    with pymupdf.open(pdf_path) as doc:
        return [p.get_pixmap(dpi=150).tobytes("png") for p in doc]


def _collect_images(src, workdir):
    src = Path(src)
    ext = src.suffix.lower()
    if src.is_dir():
        files = sorted(f for f in src.iterdir() if f.suffix.lower() in IMAGE_EXT)
        return [f.read_bytes() for f in files]
    if ext in IMAGE_EXT:
        return [src.read_bytes()]
    if ext == ".pdf":
        return _pdf_images(src)
    if ext in (".ppt", ".pptx"):
        pdf = _office_to_pdf(src, workdir)
        if pdf:
            return _pdf_images(pdf)
        if ext == ".pptx":
            return _pptx_images(src)
        raise HymnError(f"{src.name}: .ppt 파일 변환에는 LibreOffice 또는 PowerPoint 가 필요합니다.")
    if ext == ".zip":
        with zipfile.ZipFile(src) as z:
            z.extractall(Path(workdir) / "zip")
        inner = sorted(p for p in (Path(workdir) / "zip").rglob("*") if p.is_file())
        imgs = [p for p in inner if p.suffix.lower() in IMAGE_EXT]
        if imgs:
            return [p.read_bytes() for p in sorted(imgs)]
        for p in inner:
            if p.suffix.lower() in (".pptx", ".ppt", ".pdf"):
                return _collect_images(p, workdir)
    raise HymnError(f"{src.name}: 지원하지 않는 파일 형식입니다.")


def _content_box(pix, threshold=235):
    """흰 여백을 뺀 실제 악보 영역."""
    w, h, n = pix.width, pix.height, pix.n
    data = pix.samples
    step = max(1, min(w, h) // 400)
    xs, ys = [], []
    for y in range(0, h, step):
        row = y * pix.stride
        for x in range(0, w, step):
            i = row + x * n
            if min(data[i:i + min(n, 3)]) < threshold:
                xs.append(x)
                ys.append(y)
    if not xs:
        return pymupdf.IRect(0, 0, w, h)
    pad = max(w, h) // 60
    return pymupdf.IRect(max(0, min(xs) - pad), max(0, min(ys) - pad),
                         min(w, max(xs) + pad), min(h, max(ys) + pad))


def _on_white(pix):
    """투명 배경/흑백 이미지를 흰 바탕 RGB 로."""
    if pix.colorspace is None or pix.colorspace.n != 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    if not pix.alpha:
        return pix
    doc = pymupdf.open()
    page = doc.new_page(width=pix.width, height=pix.height)
    page.draw_rect(page.rect, color=None, fill=(1, 1, 1))
    page.insert_image(page.rect, pixmap=pix)
    return page.get_pixmap(alpha=False)


def _convert(src, out_path):
    with tempfile.TemporaryDirectory() as tmp:
        images = _collect_images(src, tmp)
    if not images:
        raise HymnError(f"{Path(src).name}: 슬라이드 그림을 찾지 못했습니다.")
    doc = pymupdf.open()
    margin = 30
    for data in images:
        pix = pymupdf.Pixmap(data)
        if pix.colorspace is None or pix.colorspace.n != 3 or pix.alpha:
            pix = _on_white(pix)
        box = _content_box(pix)
        crop = pymupdf.Pixmap(pymupdf.csRGB, box, False)
        crop.copy(pix, box)
        page = doc.new_page(width=layout.PAGE_W, height=layout.PAGE_H)
        page.draw_rect(page.rect, color=None, fill=(1, 1, 1))
        avail = pymupdf.Rect(margin, margin, layout.PAGE_W - margin, layout.PAGE_H - margin)
        scale = min(avail.width / crop.width, avail.height / crop.height)
        w, h = crop.width * scale, crop.height * scale
        x0 = avail.x0 + (avail.width - w) / 2
        y0 = avail.y0 + (avail.height - h) / 2
        page.insert_image(pymupdf.Rect(x0, y0, x0 + w, y0 + h), stream=crop.tobytes("png"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path, garbage=3, deflate=True)
