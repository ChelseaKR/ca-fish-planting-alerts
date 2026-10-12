#!/usr/bin/env python3
"""A static file server with HTTP Range support, for the site checks.

GitHub Pages answers `Range: bytes=…` requests, and the site's map reads its
tiles that way (PMTiles, DECISIONS 0026). `python -m http.server` does not,
so a map checked through it never loads. This serves one directory on
127.0.0.1 and answers a single byte range with 206; anything else is the
standard library's own handling.

    python3 scripts/serve_ranges.py DIRECTORY PORT
    python3 scripts/serve_ranges.py --self-test
"""

from __future__ import annotations

import argparse
import http.server
import os
import re
import shutil
import sys
import tempfile
import threading
import urllib.request
from functools import partial
from typing import Any

_RANGE = re.compile(r"^bytes=(\d+)-(\d*)$")


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler plus single-range GETs."""

    _remaining: int | None = None

    def send_head(self) -> Any:
        header = self.headers.get("Range")
        path = self.translate_path(self.path)
        match = _RANGE.match(header or "")
        if match is None or not os.path.isfile(path):
            self._remaining = None
            return super().send_head()
        size = os.path.getsize(path)
        start = int(match[1])
        end = min(int(match[2]) if match[2] else size - 1, size - 1)
        if start > end:
            self.send_error(416, "Range Not Satisfiable")
            return None
        f = open(path, "rb")  # noqa: SIM115 -- the base class closes it after copyfile (#57)
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self._remaining = end - start + 1
        return f

    def copyfile(self, source: Any, outputfile: Any) -> None:
        if self._remaining is None:
            shutil.copyfileobj(source, outputfile)
            return
        outputfile.write(source.read(self._remaining))

    def log_message(self, format: str, *args: Any) -> None:
        return


def serve(directory: str, port: int) -> http.server.ThreadingHTTPServer:
    handler = partial(RangeHandler, directory=directory)
    return http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)


def self_test() -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "f.bin"), "wb") as f:
            f.write(bytes(range(100)))
        server = serve(tmp, 0)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{port}/f.bin"
            req = urllib.request.Request(url, headers={"Range": "bytes=10-19"})
            with urllib.request.urlopen(req) as r:  # noqa: S310 -- a fixed 127.0.0.1 test URL (#57)
                if r.status != 206 or r.read() != bytes(range(10, 20)):
                    problems.append("a range did not come back as 206 with its bytes")
            with urllib.request.urlopen(url) as r:
                if r.status != 200 or len(r.read()) != 100:
                    problems.append("a plain GET did not return the whole file")
        finally:
            server.shutdown()
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?")
    parser.add_argument("port", nargs="?", type=int)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        problems = self_test()
        print(f"serve_ranges self-test: {len(problems)} failure(s)")
        for p in problems:
            print(f"  {p}")
        return 1 if problems else 0
    if args.directory is None or args.port is None:
        parser.error("DIRECTORY and PORT are required")
    serve(args.directory, args.port).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
