from __future__ import annotations

import argparse
import gzip
import re
import sys
import threading
from email.utils import formatdate
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


class MemoryPalStaticHandler(SimpleHTTPRequestHandler):
    base_prefix = ""
    _compressed_cache: dict[tuple[str, int, int], bytes] = {}
    _compressed_cache_lock = threading.Lock()
    _hashed_asset = re.compile(r"(?:^|[-.])[0-9a-f]{16,}\.", re.IGNORECASE)
    _compressible_suffixes = {".css", ".html", ".js", ".json", ".svg", ".txt"}
    favicon = (
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        b'<rect width="64" height="64" rx="16" fill="#6C63FF"/>'
        b'<path d="M18 20h28v20H31l-9 8v-8h-4z" fill="white"/>'
        b'<circle cx="26" cy="30" r="2" fill="#6C63FF"/>'
        b'<circle cx="32" cy="30" r="2" fill="#6C63FF"/>'
        b'<circle cx="38" cy="30" r="2" fill="#6C63FF"/>'
        b'</svg>'
    )

    def __init__(self, *args, directory: str, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def _strip_prefix(self) -> None:
        parsed = urlsplit(self.path)
        path = parsed.path
        if self.base_prefix and (path == self.base_prefix or path.startswith(f"{self.base_prefix}/")):
            path = path[len(self.base_prefix):] or "/"
            self.path = urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))

    def _serve_favicon(self) -> bool:
        if urlsplit(self.path).path != "/favicon.ico":
            return False
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Length", str(len(self.favicon)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(self.favicon)
        return True

    def end_headers(self) -> None:
        buffered = b"".join(getattr(self, "_headers_buffer", []))
        if b"cache-control:" not in buffered.lower():
            request_path = urlsplit(self.path).path
            filename = Path(request_path).name
            if filename == "index.html" or request_path.endswith("/"):
                self.send_header("Cache-Control", "no-cache")
            elif self._hashed_asset.search(filename):
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            else:
                self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def _compressed_file(self, path: Path) -> bytes:
        handler_type = type(self)
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        with handler_type._compressed_cache_lock:
            cached = handler_type._compressed_cache.get(key)
        if cached is not None:
            return cached
        compressed = gzip.compress(path.read_bytes(), compresslevel=6)
        with handler_type._compressed_cache_lock:
            handler_type._compressed_cache = {
                cached_key: value
                for cached_key, value in handler_type._compressed_cache.items()
                if cached_key[0] != str(path)
            }
            handler_type._compressed_cache[key] = compressed
        return compressed

    def _serve_compressed(self) -> bool:
        accepted = self.headers.get("Accept-Encoding", "").lower()
        if "gzip" not in accepted:
            return False
        path = Path(self.translate_path(self.path))
        if path.is_dir():
            path = next((path / name for name in ("index.html", "index.htm") if (path / name).is_file()), path)
        if not path.is_file() or path.suffix.lower() not in self._compressible_suffixes:
            return False
        payload = self._compressed_file(path)
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Last-Modified", formatdate(path.stat().st_mtime, usegmt=True))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)
        return True

    def do_GET(self) -> None:
        if self._serve_favicon():
            return
        self._strip_prefix()
        if not self._serve_compressed():
            super().do_GET()

    def do_HEAD(self) -> None:
        if self._serve_favicon():
            return
        self._strip_prefix()
        if not self._serve_compressed():
            super().do_HEAD()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--prefix", default="/api_memoripal/main")
    parser.add_argument("--log-file")
    args = parser.parse_args()
    directory = Path(args.directory).resolve()
    if not (directory / "index.html").is_file():
        raise SystemExit(f"Frontend build not found: {directory / 'index.html'}")
    if args.log_file:
        path = Path(args.log_file); path.parent.mkdir(parents=True, exist_ok=True)
        log = path.open("a", encoding="utf-8", buffering=1)
        sys.stdout = log; sys.stderr = log
    MemoryPalStaticHandler.base_prefix = "/" + args.prefix.strip("/") if args.prefix else ""
    def handler(*handler_args, **handler_kwargs):
        return MemoryPalStaticHandler(*handler_args, directory=str(directory), **handler_kwargs)
    ThreadingHTTPServer((args.host, args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
