#!/usr/bin/env python3
"""Treetop Benchmark Viewer - a tiny zero-dependency local server.

Serves the viewer frontend (web/), the raw model HTML files (models/), and a
live listing of the models folder at /api/models. Standard library only.

Usage:
    python3 server.py [port]

Then open the printed URL in Chrome.
"""

import json
import re
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
MODELS_DIR = ROOT / "models"
PROMPT_FILE = ROOT / "prompt.txt"
DEFAULT_PORT = 8777

# Frontend files we are willing to serve from web/, mapped to their media type.
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


def label_for(filename: str) -> str:
    """Derive a clean display label from a model filename.

    'Treetop_village_GPT6_Astra_High.html' -> 'GPT6 Astra High'
    """
    name = filename[:-5] if filename.lower().endswith(".html") else filename
    name = re.sub(r"^Treetop_village_", "", name, flags=re.IGNORECASE)
    return name.replace("_", " ").strip() or filename


def list_models() -> list[dict]:
    """Read models/ live and return sorted {file, label} entries for .html files."""
    if not MODELS_DIR.is_dir():
        return []
    entries = [
        {"file": p.name, "label": label_for(p.name)}
        for p in MODELS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() == ".html"
    ]
    entries.sort(key=lambda e: e["label"].lower())
    return entries


def safe_resolve(base: Path, filename: str) -> Path | None:
    """Resolve filename inside base, rejecting traversal/absolute paths.

    Returns the resolved path if it is an existing file inside base, else None.
    """
    filename = unquote(filename)
    if not filename or filename.startswith("/") or ".." in filename.split("/"):
        return None
    candidate = (base / filename).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


class Handler(BaseHTTPRequestHandler):
    server_version = "TreetopViewer/1.0"

    # ---- helpers -------------------------------------------------------

    def _send(self, status, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str):
        try:
            self._send(HTTPStatus.OK, path.read_bytes(), content_type)
        except OSError:
            self._send_text(HTTPStatus.INTERNAL_SERVER_ERROR, "Could not read file")

    def _send_text(self, status, message: str):
        self._send(status, message.encode("utf-8"), "text/plain; charset=utf-8")

    def _send_json(self, payload):
        self._send(
            HTTPStatus.OK,
            json.dumps(payload).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    # ---- routing -------------------------------------------------------

    def do_GET(self):
        self.route()

    def do_HEAD(self):
        self.route()

    def route(self):
        path = urlparse(self.path).path

        if path == "/api/models":
            self._send_json({"models": list_models()})
            return

        if path == "/api/prompt":
            if PROMPT_FILE.is_file():
                self._send_file(PROMPT_FILE, "text/plain; charset=utf-8")
            else:
                self._send_text(HTTPStatus.NOT_FOUND, "prompt.txt not found")
            return

        if path in STATIC_FILES:
            name, content_type = STATIC_FILES[path]
            target = WEB_DIR / name
            if target.is_file():
                self._send_file(target, content_type)
            else:
                self._send_text(HTTPStatus.NOT_FOUND, f"Missing frontend file: {name}")
            return

        if path.startswith("/models/"):
            resolved = safe_resolve(MODELS_DIR, path[len("/models/"):])
            if resolved:
                self._send_file(resolved, "text/html; charset=utf-8")
            else:
                self._send_text(HTTPStatus.NOT_FOUND, "Model not found")
            return

        self._send_text(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, fmt, *args):  # quieter, single-line logging
        sys.stderr.write("  %s\n" % (fmt % args))


def main():
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port '{sys.argv[1]}', using {DEFAULT_PORT}")

    if not WEB_DIR.is_dir():
        print(f"Warning: {WEB_DIR} does not exist yet.")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}/"
    print("Treetop Benchmark Viewer")
    print(f"  serving on {url}")
    print(f"  models:    {MODELS_DIR}")
    print("  press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
