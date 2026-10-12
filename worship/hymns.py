"""찬송가 악보 슬라이드 준비.

순서:
  1. hymns/076.pdf 처럼 이미 만들어 둔 캐시가 있으면 그대로 사용
  2. hymns/inbox/ 에 직접 받아 둔 파일(파일명에 장 번호 포함)이 있으면 변환
  3. bibletoppt.com (배경 없는 찬송가 PPT) 에서 자동 다운로드 후 변환

변환 결과는 hymns/NNN.pdf 로 저장되어 다음부터는 바로 쓰입니다.
"""

import io
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin

import pymupdf

from . import layout

from .paths import HYMN_DIR, INBOX

SITE = "https://bibletoppt.com"
LIST_URL = SITE + "/hymn/hymnppt/no-bg"
API_URL = SITE + "/api/download"
WAIT_SECONDS = 10
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
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
        auto = False
        if not source and not ALLOW_DOWNLOAD:
            raise HymnError(f"찬송가 {num}장 악보 파일이 없습니다. 악보 파일(PDF/PPTX)을 올려 주세요.")
        if not source:
            failed_at = _FAILED.get(int(num))
            if failed_at and time.time() - failed_at < RETRY_AFTER:
                raise HymnError(_manual_help(num, "조금 전에 자동 다운로드에 실패했습니다."))
            try:
                source = _download(num, log)
                auto = True
            except HymnError:
                _FAILED[int(num)] = time.time()
                raise
        log(f"  찬송가 {num}장 변환 중: {source.name}")
        _convert(source, path)
        if auto:  # 변환해 저장했으니 받은 원본(PPTX)은 지워서 용량을 아낍니다
            source.unlink(missing_ok=True)
    return pymupdf.open(path)


# ---------------------------------------------------------------- 미리 받아 두기

HYMN_COUNT = 645
SECONDS_PER_HYMN = WAIT_SECONDS + 4  # 대기 + 받기/변환


def parse_numbers(text):
    """'전체' / '1-100, 305, 455' → 장 번호 목록 (중복 없이, 순서 유지)."""
    text = (text or "").strip()
    if text in ("전체", "all", "*", ""):
        return list(range(1, HYMN_COUNT + 1))
    out = []
    for part in re.split(r"[,\s]+", text):
        if not part:
            continue
        m = re.fullmatch(r"(\d{1,3})\s*[-~]\s*(\d{1,3})", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out.extend(range(min(a, b), max(a, b) + 1))
        elif part.isdigit():
            out.append(int(part))
        else:
            raise HymnError(f"장 번호 형식을 알 수 없습니다: '{part}'  (예: 전체, 1-100, 305, 455)")
    nums = list(dict.fromkeys(out))
    bad = [n for n in nums if not 1 <= n <= HYMN_COUNT]
    if bad:
        raise HymnError(f"새찬송가는 1~{HYMN_COUNT}장입니다: {bad[:5]}")
    return nums


def prefetch(numbers, log=print, progress=None, should_stop=lambda: False, max_failures=5):
    """찬송가를 미리 받아 hymns/NNN.pdf 로 저장해 둡니다. 이미 있는 곡은 건너뜁니다.

    사이트 규칙에 따라 곡마다 10초씩 기다리며 한 곡씩 받습니다.
    progress(지금까지 한 곡 수, 받을 곡 수, 지금 곡 번호) 로 진행 상황을 알려 줍니다.
    """
    todo = [n for n in numbers if not cache_path(n).exists()]
    result = {"requested": len(numbers), "already": len(numbers) - len(todo), "downloaded": 0, "failed": []}
    log(f"전체 {len(numbers)}곡 중 이미 있는 {result['already']}곡을 빼고 {len(todo)}곡을 받습니다. "
        f"(약 {len(todo) * SECONDS_PER_HYMN // 60}분)")
    streak = 0
    for i, n in enumerate(todo):
        if should_stop():
            log("중지했습니다. 다음에 다시 시작하면 이어서 받습니다.")
            break
        if progress:
            progress(i, len(todo), n)
        _FAILED.pop(n, None)
        try:
            get_hymn(n, log).close()
            result["downloaded"] += 1
            streak = 0
        except Exception as e:  # noqa: BLE001  한 곡 실패가 전체를 멈추지 않게
            result["failed"].append(n)
            streak += 1
            log(f"  [실패] 찬송가 {n}장: {str(e).splitlines()[0]}")
            if streak >= max_failures:
                log(f"연속 {max_failures}번 실패해서 멈춥니다. 인터넷 연결이나 사이트 상태를 확인한 뒤 다시 시작하세요.")
                break
    if progress:
        progress(result["downloaded"] + len(result["failed"]), len(todo), 0)
    log(f"끝: 새로 받은 곡 {result['downloaded']}, 실패 {len(result['failed'])}"
        + (f" ({', '.join(map(str, result['failed'][:20]))}{' …' if len(result['failed']) > 20 else ''})"
           if result["failed"] else ""))
    return result


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

def detect_extension(data, disposition=""):
    """받은 파일이 무엇인지 (내용의 앞부분으로) 판단: .pdf / .pptx / .ppt / .zip / 그림."""
    if data[:4] == b"%PDF":
        return ".pdf"
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return ".ppt"
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                return ".pptx" if any(n.startswith("ppt/") for n in z.namelist()) else ".zip"
        except zipfile.BadZipFile:
            return ""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    m = re.search(r"filename\*?=(?:UTF-8\'\')?\"?([^\";]+)", disposition or "")
    ext = Path(m.group(1)).suffix.lower() if m else ""
    return ext if ext in SLIDE_EXT else ""


def _download(num, log):
    """bibletoppt.com 의 '배경 없음' 찬송가 PPT 를 받습니다.

    사이트의 [PPT 다운로드] 버튼과 같은 순서입니다:
      ① 10초 기다림 → ② /api/download?action=token… 으로 일회용 토큰 → ③ /api/download?token=… 로 파일
    사이트가 정한 10초 대기를 그대로 지키며, 필요한 곡만 한 곡씩 받습니다.
    """
    try:
        import requests
    except ImportError as e:
        raise HymnError("requests 패키지가 필요합니다: pip install -r requirements.txt") from e

    n = int(num)
    if not 1 <= n <= 645:
        raise HymnError(f"찬송가 {num}장은 새찬송가 범위(1~645장)가 아닙니다.")
    page = f"{SITE}/hymn/hymnppt/no-bg/{n:03d}"
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Referer": page})
    try:
        r = session.get(page, timeout=30)
        if r.status_code == 404:
            raise HymnError(_manual_help(num, "사이트에 이 장이 없습니다."))
        r.raise_for_status()
        log(f"  찬송가 {n}장 악보를 bibletoppt.com 에서 받는 중… (사이트 규칙에 따라 {WAIT_SECONDS}초 기다립니다)")
        time.sleep(WAIT_SECONDS)
        params = {"type": "hymn", "design": "no-bg", "number": f"{n:03d}"}
        r = session.get(API_URL, params={"action": "token", **params}, timeout=30)
        token = r.json().get("token") if r.status_code == 200 else None
        if not token:
            raise HymnError(_manual_help(num, f"다운로드 허가를 받지 못했습니다 (응답 {r.status_code})."))
        r = session.get(API_URL, params={"token": token}, timeout=120)
        if r.status_code != 200 or len(r.content) < 1000:
            raise HymnError(_manual_help(num, f"파일을 받지 못했습니다 (응답 {r.status_code})."))
    except HymnError:
        raise
    except Exception as e:
        raise HymnError(_manual_help(num, f"다운로드 오류: {e}")) from e
    ext = detect_extension(r.content, r.headers.get("content-disposition", ""))
    if not ext:
        raise HymnError(_manual_help(num, "받은 파일 형식을 알 수 없습니다."))
    INBOX.mkdir(parents=True, exist_ok=True)
    path = INBOX / f"{n:03d}{ext}"
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
