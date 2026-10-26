#!/usr/bin/env python3
"""MAPS dashboard server (standard library only).

Serves two pages and the panel files, read-only, on this PC only:
  GET /                    brain.html, the graph of the whole map
  GET /panels              dashboard.html, the due / routines / sync panels
  GET /data/<panel>.json   one of PANELS, read from panels.DATA_DIR
There is deliberately no route that returns a file's text: every account on
this PC can reach 127.0.0.1, so such a route would let claude-agent read F:.
Every other path is 404 and every other method is 405. Nothing is ever
written. No cookies, no login, no third-party JavaScript.

Usage:  python serve_dashboard.py          then open http://127.0.0.1:8765
"""
import ipaddress
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from panels import DATA_DIR

HOST, PORT = "127.0.0.1", 8765
ROOT = os.path.dirname(os.path.abspath(__file__))
PAGES = {"/": "brain.html", "/index.html": "brain.html", "/panels": "dashboard.html"}
PANELS = ("routines", "todo", "sync", "brain")
HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                               "script-src 'self' 'unsafe-inline'; frame-ancestors 'none'",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "maps-dashboard"
    sys_version = ""

    def route(self):
        path = self.path.split("?", 1)[0]
        if path in PAGES:
            return os.path.join(ROOT, PAGES[path]), "text/html; charset=utf-8"
        for name in PANELS:
            if path == "/data/%s.json" % name:
                return os.path.join(DATA_DIR, name + ".json"), "application/json; charset=utf-8"
        return None, None

    def send(self, code, body, ctype, head_only=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def do_GET(self, head_only=False):
        path, ctype = self.route()
        if path is None:
            return self.send(404, b"not found\n", "text/plain", head_only)
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            if ctype.startswith("application/json"):
                return self.send(200, b'{"missing": true}', ctype, head_only)
            return self.send(404, b"not found\n", "text/plain", head_only)
        self.send(200, body, ctype, head_only)

    def do_HEAD(self):
        self.do_GET(head_only=True)

    def refuse(self):
        self.send(405, b"read-only\n", "text/plain")

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = refuse

    def log_message(self, fmt, *args):
        pass  # keep pythonw silent


def main():
    if not ipaddress.ip_address(HOST).is_loopback:
        print("refusing to bind %s: this dashboard is for this PC only" % HOST)
        return 1
    print("MAPS dashboard on http://%s:%d (panels from %s)" % (HOST, PORT, DATA_DIR))
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
