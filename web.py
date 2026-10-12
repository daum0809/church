"""주일예배 PDF 만들기 - 핸드폰/태블릿용 웹 화면.

    python web.py                # http://<이 PC 주소>:8000 을 핸드폰에서 열기 (같은 와이파이)
    python web.py --port 7860    # 다른 포트

인터넷 서버에 올릴 때는 환경 변수 WORSHIP_PASSWORD 로 비밀번호를 거세요.
(아이디는 아무거나, 비밀번호만 맞으면 됩니다)
"""

import argparse
import base64
import json
import os
import re
import socket
import threading
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from worship import bulletin, memory, paths
from worship.build import load_input
from worship.service import build_result
from worship.hwp import extract_text
from worship.run import ERRORS, HWP_EXT

PAGE = paths.RES / "web_page.html"
MAX_UPLOAD = 60 * 1024 * 1024
LOCK = threading.Lock()  # PDF 만들기는 한 번에 하나씩


def local_addresses():
    ips = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # 실제로 보내지 않음, 내 주소 확인용
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def _save_weekly(data):
    with open(paths.WEEKLY, "w", encoding="utf-8") as f:
        f.write("# 핸드폰/웹 화면에서 마지막으로 만든 내용입니다.\n")
        memory.dump_yaml(data, f)


def make_pdf(data, todo=None):
    """data 로 PDF 를 만들고 화면에 돌려줄 결과."""
    with LOCK:
        pdf, result = build_result(data, todo)
        _save_weekly(result["data"])
    result["pdf"] = "/pdf/" + quote(pdf.name)
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = "WorshipPDF"

    # ------------------------------------------------------------ 공통
    def log_message(self, fmt, *args):  # 조용히
        pass

    def _authorized(self):
        password = os.environ.get("WORSHIP_PASSWORD")
        if not password:
            return True
        header = self.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                _, _, given = base64.b64decode(header[6:]).decode("utf-8").partition(":")
                if given == password:
                    return True
            except ValueError:
                pass
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="worship", charset="UTF-8"')
        self.end_headers()
        return False

    def _send(self, status, body, ctype, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status=HTTPStatus.OK):
        self._send(status, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            raise ValueError("파일이 너무 큽니다.")
        return self.rfile.read(length)

    def _filename(self):
        return Path(unquote(self.headers.get("X-Filename", "upload"))).name

    # ------------------------------------------------------------ GET
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/api/health":  # 서버 상태 확인용 (비밀번호 없이)
            self._json({"ok": True})
            return
        if not self._authorized():
            return
        if url.path in ("/", "/index.html"):
            self._send(HTTPStatus.OK, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/current":
            paths.setup()
            data = load_input(paths.WEEKLY) if paths.WEEKLY.exists() else {}
            self._json({"data": data})
        elif url.path.startswith("/pdf/"):
            name = Path(unquote(url.path[5:])).name
            pdf = paths.OUTPUT / name
            if not name.endswith(".pdf") or not pdf.is_file():
                self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
                return
            self._send(HTTPStatus.OK, pdf.read_bytes(), "application/pdf",
                       {"Content-Disposition": f"inline; filename*=UTF-8''{quote(name)}"})
        else:
            self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")

    # ------------------------------------------------------------ POST
    def do_POST(self):
        if not self._authorized():
            return
        url = urlparse(self.path)
        try:
            paths.setup()
            if url.path == "/api/bulletin":
                self._json(self.bulletin())
            elif url.path == "/api/build":
                data = json.loads(self._body().decode("utf-8"))
                self._json(make_pdf(data))
            elif url.path == "/api/hymn":
                self._json(self.hymn(parse_qs(url.query).get("num", [""])[0]))
            else:
                self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
        except ERRORS + (ValueError,) as e:
            self._json({"ok": False, "error": str(e)}, HTTPStatus.BAD_REQUEST)
        except Exception:
            traceback.print_exc()
            self._json({"ok": False, "error": "예상하지 못한 오류가 났습니다.\n" + traceback.format_exc(limit=3)},
                       HTTPStatus.INTERNAL_SERVER_ERROR)

    def bulletin(self):
        name = self._filename()
        if Path(name).suffix.lower() not in HWP_EXT:
            raise ValueError("주보 한글 파일(.hwp / .hwpx)을 골라 주세요.")
        body = self._body()
        paths.BULLETIN_DIR.mkdir(exist_ok=True)
        saved = paths.BULLETIN_DIR / name
        saved.write_bytes(body)
        data, todo = bulletin.parse(extract_text(saved))
        return make_pdf(data, todo)

    def hymn(self, num):
        if not re.fullmatch(r"\d{1,3}", num or ""):
            raise ValueError("찬송가 장 번호가 올바르지 않습니다.")
        name = self._filename()
        ext = Path(name).suffix.lower()
        if ext not in {".ppt", ".pptx", ".pdf", ".zip", ".png", ".jpg", ".jpeg"}:
            raise ValueError("PPT / PPTX / PDF / ZIP / 그림 파일을 올려 주세요.")
        paths.INBOX.mkdir(parents=True, exist_ok=True)
        cache = paths.HYMN_DIR / f"{int(num):03d}.pdf"
        if cache.exists():
            cache.unlink()  # 새로 올린 악보로 다시 변환
        (paths.INBOX / f"{int(num)}장{ext}").write_bytes(self._body())
        return {"ok": True}


def serve(port=8000, host="0.0.0.0", announce=print):
    paths.setup()
    server = ThreadingHTTPServer((host, port), Handler)
    announce(f"웹 화면을 시작했습니다. 포트 {port}")
    for ip in local_addresses():
        announce(f"  핸드폰(같은 와이파이)에서 열기: http://{ip}:{port}")
    announce(f"  이 PC 에서 열기: http://localhost:{port}")
    return server


def main():
    parser = argparse.ArgumentParser(description="주일예배 PDF 웹 화면")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    server = serve(args.port, args.host)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
