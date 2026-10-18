#!/usr/bin/env python3
"""Local static server for the Treetop Benchmark Viewer.

The site is plain static files served from the repository root, exactly as
GitHub Pages serves them. This script exists only so you can preview it
locally without installing anything. Standard library only.

    python3 server.py          # http://localhost:8777/
    python3 server.py 9000     # another port
"""

from __future__ import annotations

import mimetypes
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
DEFAULT_PORT = 8777

# What the site is allowed to serve: the viewer, its data, and the model files.
# Everything else in the repo (scripts, tests, runs/, .env) stays private.
ROOT_FILES = {"index.html", "style.css", "app.js", "models.json", "prompt.txt"}
PUBLIC_DIRS = {"models", "docs", "assets"}

mimetypes.add_type("text/markdown", ".md")


def resolve(url_path: str) -> Path | None:
    """Map a URL path to a file we are willing to serve, or None."""
    path = unquote(url_path)
    if path in ("", "/"):
        path = "/index.html"
    rel = Path(path.lstrip("/"))
    if any(part in ("", ".", "..") for part in rel.parts):
        return None
    if len(rel.parts) == 1 and rel.name not in ROOT_FILES:
        return None
    if len(rel.parts) > 1 and rel.parts[0] not in PUBLIC_DIRS:
        return None
    target = (ROOT / rel).resolve()
    try:
        target.relative_to(ROOT)
    except ValueError:
        return None
    return target if target.is_file() else None


class Handler(BaseHTTPRequestHandler):
    server_version = "TreetopViewer/2.0"

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        target = resolve(urlparse(self.path).path)
        if target is None:
            self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain; charset=utf-8")
            return
        ctype, _ = mimetypes.guess_type(target.name)
        ctype = ctype or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/json", "application/javascript"):
            ctype += "; charset=utf-8"
        try:
            self._send(HTTPStatus.OK, target.read_bytes(), ctype)
        except OSError:
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, b"Could not read file", "text/plain; charset=utf-8")

    do_HEAD = do_GET

    def log_message(self, fmt, *args):  # quieter, single-line logging
        sys.stderr.write("  %s\n" % (fmt % args))


def main() -> None:
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port '{sys.argv[1]}', using {DEFAULT_PORT}")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("Treetop Benchmark Viewer")
    print(f"  serving {ROOT}")
    print(f"  on      http://localhost:{port}/")
    print("  press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
