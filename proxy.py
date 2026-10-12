"""찬송가 받기 도우미 (작은 중계 프로그램).

폰의 브라우저는 bibletoppt.com 에서 파일을 직접 받을 수 없습니다 (사이트가 막아 둠).
이 프로그램이 대신 받아서 폰에 넘겨 주면, 폰이 변환해서 저장합니다.
이 프로그램은 아무것도 저장하지 않습니다 (잠깐 쓰는 임시 보관만).

    python proxy.py                 # 포트 8000
    ALLOWED_ORIGINS=https://내주소.github.io python proxy.py

환경 변수
  PORT             듣는 포트 (기본 8000)
  ALLOWED_ORIGINS  접속을 허용할 웹 주소들, 쉼표로 구분
                   (기본: https://daum0809.github.io 와 같은 PC 의 localhost)
  PROXY_KEY        적어 두면 폰 화면에도 같은 값을 넣어야 쓸 수 있습니다 (선택)
"""

import os
import re
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from worship import hymns

DEFAULT_ORIGINS = "https://daum0809.github.io"
CACHE = Path(tempfile.gettempdir()) / "worship-proxy-cache"
LOCK = threading.Lock()          # 사이트에는 한 번에 한 곡만 요청
KEEP = 80                        # 임시 보관은 최근 80곡까지


def allowed_origins():
    return [o.strip().rstrip("/") for o in os.environ.get("ALLOWED_ORIGINS", DEFAULT_ORIGINS).split(",") if o.strip()]


def origin_ok(origin):
    if not origin:
        return False
    origin = origin.rstrip("/")
    if origin in allowed_origins():
        return True
    return bool(re.fullmatch(r"https?://(localhost|127\.0\.0\.1)(:\d+)?", origin))


def cached(num):
    for f in CACHE.glob(f"{num:03d}.*"):
        return f
    return None


def get_hymn_file(num, log=print):
    """(내용, 확장자). 임시 보관에 있으면 사이트에 다시 묻지 않습니다."""
    with LOCK:
        hit = cached(num)
        if hit:
            return hit.read_bytes(), hit.suffix
        data, ext = hymns.fetch_bytes(num, log)
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / f"{num:03d}{ext}").write_bytes(data)
        files = sorted(CACHE.iterdir(), key=lambda f: f.stat().st_mtime)
        for old in files[:-KEEP]:
            old.unlink(missing_ok=True)
        return data, ext


class Handler(BaseHTTPRequestHandler):
    server_version = "HymnHelper"

    def log_message(self, fmt, *args):
        print("  " + fmt % args)

    def _cors(self):
        origin = self.headers.get("Origin", "")
        if origin_ok(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Expose-Headers", "X-Filename, X-Ext")

    def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status, message):
        import json
        self._send(status, json.dumps({"ok": False, "error": message}, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/health", "/api/health"):
            return self._send(HTTPStatus.OK, b'{"ok": true, "name": "hymn-helper"}')
        m = re.fullmatch(r"/hymn/(\d{1,3})", url.path)
        if not m:
            return self._error(HTTPStatus.NOT_FOUND, "주소가 올바르지 않습니다.")
        if not origin_ok(self.headers.get("Origin", "")):
            return self._error(HTTPStatus.FORBIDDEN, "허용되지 않은 웹 주소에서 온 요청입니다.")
        key = os.environ.get("PROXY_KEY")
        if key and parse_qs(url.query).get("key", [""])[0] != key:
            return self._error(HTTPStatus.UNAUTHORIZED, "접속 키가 맞지 않습니다.")
        num = int(m.group(1))
        try:
            data, ext = get_hymn_file(num)
        except hymns.HymnError as e:
            return self._error(HTTPStatus.BAD_GATEWAY, str(e).splitlines()[0])
        except Exception as e:  # noqa: BLE001
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"받는 중 오류가 났습니다: {e}")
        self._send(HTTPStatus.OK, data, "application/octet-stream",
                   {"X-Filename": f"{num:03d}{ext}", "X-Ext": ext})


def main():
    port = int(os.environ.get("PORT", 8000))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"찬송가 받기 도우미를 시작했습니다. 포트 {port}")
    print("  허용한 웹 주소:", ", ".join(allowed_origins()), "(+ localhost)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
