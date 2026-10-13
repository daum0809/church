"""핸드폰 브라우저용 사이트(site/) 만들기.

    python tools/build_site.py            # site/ 폴더 생성

만들어지는 것:
  index.html      핸드폰 화면 (web_page.html + 브라우저 방식 표시)
  pyworker.js     파이썬을 돌리는 작업 스레드
  app.zip         예배 프로그램 + 원본 디자인 + 글꼴 + 기본 악보/기억 데이터
  wheels/*.whl    PDF 엔진(PyMuPDF, 브라우저용), olefile
  pyodide/        브라우저에서 도는 파이썬 (npm 의 pyodide 패키지)
  manifest.json   위 파일 목록

GitHub Actions 가 이 폴더를 gh-pages 브랜치로 올려 GitHub Pages 주소로 열리게 합니다.
"""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYODIDE_VERSION = "0.29.5"          # PyMuPDF 의 브라우저용 wheel(2025_0)과 맞는 버전
PYODIDE_FILES = ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json")
FONTS = ("Pretendard-Regular.ttf", "Pretendard-SemiBold.ttf", "Pretendard-OFL.txt")


def fetch(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def pypi(name):
    return json.loads(fetch(f"https://pypi.org/pypi/{name}/json"))


def wasm_wheel(name):
    """PyPI 에서 브라우저용(2025_0) wheel 중 가장 최신 것."""
    info = pypi(name)
    versions = sorted(info["releases"], key=lambda v: [int(x) if x.isdigit() else 0 for x in v.split(".")],
                      reverse=True)
    for v in versions:
        for f in info["releases"][v]:
            if "2025_0_wasm32" in f["filename"]:
                return f
    raise SystemExit(f"{name} 의 브라우저용 wheel 을 찾지 못했습니다.")


def pure_wheel(name):
    for f in pypi(name)["urls"]:
        if f["filename"].endswith("none-any.whl"):
            return f
    raise SystemExit(f"{name} wheel 을 찾지 못했습니다.")


def vendor_yaml(dest):
    """PyYAML 순수 파이썬 소스 (브라우저에서는 C 확장이 없으므로 소스째 넣음)."""
    sd = next(f for f in pypi("pyyaml")["urls"] if f["packagetype"] == "sdist")
    tar = tarfile.open(fileobj=io.BytesIO(fetch(sd["url"])))
    for m in tar.getmembers():
        parts = m.name.split("/")
        if m.isfile() and len(parts) >= 4 and parts[1] == "lib" and parts[2] == "yaml":
            (dest / "yaml").mkdir(parents=True, exist_ok=True)
            (dest / "yaml" / parts[-1]).write_bytes(tar.extractfile(m).read())
        elif m.isfile() and parts[-1] == "LICENSE" and len(parts) == 2:
            (dest / "LICENSE-PyYAML.txt").write_bytes(tar.extractfile(m).read())


def pyodide_files(out):
    with tempfile.TemporaryDirectory() as tmp:
        npm = "npm.cmd" if sys.platform.startswith("win") else "npm"
        subprocess.run([npm, "pack", f"pyodide@{PYODIDE_VERSION}", "--silent"], cwd=tmp, check=True,
                       stdout=subprocess.DEVNULL)
        tgz = next(Path(tmp).glob("pyodide-*.tgz"))
        with tarfile.open(tgz) as tar:
            for name in PYODIDE_FILES:
                (out / name).write_bytes(tar.extractfile(f"package/{name}").read())


def make_app_zip(path, yaml_dir):
    skip = {"__pycache__"}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted((ROOT / "worship").rglob("*.py")):
            if not skip & set(f.parts):
                z.write(f, f.relative_to(ROOT))
        z.write(ROOT / "templates" / "base.pdf", "templates/base.pdf")
        for name in FONTS:
            z.write(ROOT / "fonts" / name, f"fonts/{name}")
        for f in sorted((ROOT / "hymns").glob("*.pdf")):
            z.write(f, f"hymns/{f.name}")
        for f in sorted((ROOT / "data").rglob("*")):
            if f.is_file() and f.suffix in (".yaml", ".txt"):
                z.write(f, f.relative_to(ROOT))
        for f in sorted(yaml_dir.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(yaml_dir))


def site_url():
    """사이트 주소: SITE_URL 환경 변수 → GitHub 저장소 이름으로 추정 → 기본값."""
    url = os.environ.get("SITE_URL")
    if not url and os.environ.get("GITHUB_REPOSITORY"):
        owner, repo = os.environ["GITHUB_REPOSITORY"].split("/", 1)
        url = f"https://{owner}.github.io/{repo}/"
    url = url or "https://daum0809.github.io/church-worship-automation/"
    return url if url.endswith("/") else url + "/"


def make_guide(out):
    """사용 안내 페이지(guide.html): 주소와 QR 코드를 채워 넣습니다."""
    import segno
    url = site_url()
    qr = segno.make(url, error="m").svg_inline(scale=4, border=1, dark="#222222", light="#ffffff",
                                               title="사이트 주소 QR 코드")
    html = (ROOT / "guide.html").read_text(encoding="utf-8").replace("{{URL}}", url).replace("{{QR}}", qr)
    (out / "guide.html").write_text(html, encoding="utf-8")
    return url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "site"))
    args = parser.parse_args()
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "pyodide").mkdir(parents=True)
    (out / "wheels").mkdir()

    print("브라우저용 파이썬(Pyodide) 가져오는 중…")
    pyodide_files(out / "pyodide")

    print("PDF 엔진(PyMuPDF) 가져오는 중…")
    wheels = []
    for f in (wasm_wheel("pymupdf"), pure_wheel("olefile")):
        (out / "wheels" / f["filename"]).write_bytes(fetch(f["url"]))
        wheels.append("wheels/" + f["filename"])
        print("  ", f["filename"])

    print("예배 프로그램 묶는 중…")
    with tempfile.TemporaryDirectory() as tmp:
        yaml_dir = Path(tmp)
        vendor_yaml(yaml_dir)
        make_app_zip(out / "app.zip", yaml_dir)

    html = (ROOT / "web_page.html").read_text(encoding="utf-8")
    html = html.replace("<script>\nconst FIELDS", "<script>window.WORSHIP_BROWSER = true;</script>\n<script>\nconst FIELDS", 1)
    assert "WORSHIP_BROWSER = true" in html
    (out / "index.html").write_text(html, encoding="utf-8")
    shutil.copy(ROOT / "pyworker.js", out / "pyworker.js")
    url = make_guide(out)
    print("  사이트 주소:", url)
    (out / ".nojekyll").write_text("")
    (out / "manifest.json").write_text(
        json.dumps({"pyodide": PYODIDE_VERSION, "wheels": wheels, "app": "app.zip"}, indent=1), encoding="utf-8")

    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"완성: {out}  ({total / 1e6:.0f}MB)")


if __name__ == "__main__":
    main()
