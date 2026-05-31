#!/usr/bin/env python3
"""
serve.py — Dev HTTP server for FinLife Web.

Serves from the repo root so Pyodide can fetch .py source files.
Users open http://localhost:8003/web/

Usage:
    cd FinLife/web
    python3 serve.py
"""
import http.server
import socketserver
import os

PORT = 8003
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}")


if __name__ == '__main__':
    os.chdir(REPO_ROOT)
    print(f"🚀  FinLife Web dev server")
    print(f"    Open → http://localhost:{PORT}/web/")
    print(f"    Ctrl+C to stop")
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n👋  Server stopped.")