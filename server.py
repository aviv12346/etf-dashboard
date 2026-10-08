"""Local dashboard server (stdlib only).

Run:   python3 server.py            -> http://localhost:8000
Routes:
  GET /                                   dashboard page
  GET /api/data?extra=AAPL,QQQ[&force=1]  ETF universe (+ user watchlist tickers)
  GET /api/scanner[?force=1]              stocks held by the strongest ETFs
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import fetch_data

import os

PORT = int(os.environ.get("PORT", 8000))
SCANNER_TTL = 900  # scanner result cached for 15 minutes
ROOT = Path(__file__).parent

_scan = {"payload": None, "ts": 0.0}
_scan_lock = threading.Lock()


def get_scanner(force=False):
    with _scan_lock:
        if force or not _scan["payload"] or time.time() - _scan["ts"] > SCANNER_TTL:
            _scan["payload"] = fetch_data.build_scanner(force)
            _scan["ts"] = time.time()
        return _scan["payload"]


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, fn):
        try:
            self._send(200, json.dumps(fn()).encode(), "application/json")
        except Exception as e:  # noqa: BLE001
            self._send(502, json.dumps({"error": str(e)}).encode(), "application/json")

    def do_GET(self):
        url = urlparse(self.path)
        qs = parse_qs(url.query)
        force = qs.get("force") == ["1"]
        if url.path in ("/", "/index.html"):
            self._send(200, (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/data":
            extra = [t.strip().upper() for t in (qs.get("extra") or [""])[0].split(",") if t.strip()]
            self._json(lambda: fetch_data.build_payload(extra, force))
        elif url.path == "/api/scanner":
            self._json(lambda: get_scanner(force))
        else:
            self._send(404, b"Not found", "text/plain")

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}")


if __name__ == "__main__":
    print(f"Dashboard running on 0.0.0.0:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
