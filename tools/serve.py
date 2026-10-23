"""Local preview of the homepage: serves site/ like `python -m http.server`, but asks the browser to
check for a newer file on every load (Cache-Control: no-cache), so an ordinary refresh shows the
latest edit instead of a copy the browser decided was still fresh. The content types of the site's
files are pinned, because the Windows registry can map .js to text/plain. Listens on 127.0.0.1 only.

Draft previews are served at /preview/<draft-id>/: the page files come from site/, and
assets/ comes from .local/output/homepage-images/drafts/<draft-id>/assets/. Nothing formal is changed.

Usage: python tools/serve.py [port]    (default 8766)
"""

import functools
import http.server
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

HOME = Path(__file__).resolve().parent.parent
SITE = HOME / "site"
DRAFTS = HOME / ".local" / "output" / "homepage-images" / "drafts"
DRAFT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")


def _safe(root, value):
    root = root.resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root) or path == root:
        return None
    return path


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
        ".webp": "image/webp", ".png": "image/png", ".svg": "image/svg+xml",
    }

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def translate_path(self, path):
        parsed = urlparse(path)
        parts = [unquote(part) for part in parsed.path.split("/")]
        if len(parts) >= 3 and parts[1] == "preview":
            draft = parts[2]
            if not DRAFT_ID.match(draft):
                return str(SITE / "__invalid_preview__")
            rest = "/".join(parts[3:]) or "index.html"
            if rest.startswith("assets/"):
                target = _safe(DRAFTS / draft / "assets", rest[len("assets/"):])
            else:
                target = _safe(SITE, rest)
            return str(target or SITE / "__invalid_preview__")
        return super().translate_path(path)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/preview/") and not parsed.path.endswith("/"):
            parts = parsed.path.split("/")
            if len(parts) == 3 and DRAFT_ID.match(parts[2]):
                self.send_response(301)
                self.send_header("Location", parsed.path + "/")
                self.end_headers()
                return
        super().do_GET()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    handler = functools.partial(NoCacheHandler, directory=str(SITE))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"预览地址：http://127.0.0.1:{port}/", flush=True)
        if DRAFTS.is_dir():
            print(f"草稿预览：http://127.0.0.1:{port}/preview/<draft-id>/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
