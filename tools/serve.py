"""Local preview of the homepage: serves site/ like `python -m http.server`, but asks the browser to
check for a newer file on every load (Cache-Control: no-cache), so an ordinary refresh shows the
latest edit instead of a copy the browser decided was still fresh. The content types of the site's
files are pinned, because the Windows registry can map .js to text/plain. Listens on 127.0.0.1 only.

Draft previews are served at /preview/<draft-id>/: the page files come from site/, and
assets/ comes from .local/output/homepage-images/drafts/<draft-id>/assets/. Nothing formal is changed.

Creative drafts are served at /creative-preview/<preview-id>/: the files come from
.local/output/creative-assets/projects/<project>/previews/<preview-id>/overlay/ where the draft
shadows a site file, and from site/ otherwise. The preview route never writes the site and never
runs the ABOUT build.

Whenever the site's own page is asked for (/, /index.html), ABOUT's text is brought up to date
from content/about.*.md first (build_about.py); where a file cannot be read, the browser is
shown why instead of the page. Draft previews are served without building or writing the formal
page.

Usage: python tools/serve.py [port] [--creative-root DIR]    (default 8766)
"""

import functools
import html
import http.server
import os
import re
import sys
import threading
from pathlib import Path
from urllib.parse import unquote, urlparse

import build_about

HOME = Path(__file__).resolve().parent.parent
SITE = HOME / "site"
DRAFTS = HOME / ".local" / "output" / "homepage-images" / "drafts"
CREATIVE = HOME / ".local" / "output" / "creative-assets"
DRAFT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
CREATIVE_PREVIEW_ID = re.compile(r"^pv-[0-9a-f]{8}$")
# The formal page itself, at the top or as index.html.  Draft previews are served
# from the same files but must not run the ABOUT build (it writes site/index.html).
PAGE_PATH = re.compile(r"^/(?:index\.html)?$")
ABOUT_LOCK = threading.Lock()   # (requests come in on threads of their own)


def _safe(root, value):
    root = root.resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root) or path == root:
        return None
    return path


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    site_root = SITE
    creative_root = CREATIVE
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
                return str(self.site_root / "__invalid_preview__")
            rest = "/".join(parts[3:]) or "index.html"
            if rest.startswith("assets/"):
                target = _safe(DRAFTS / draft / "assets", rest[len("assets/"):])
            else:
                target = _safe(self.site_root, rest)
            return str(target or self.site_root / "__invalid_preview__")
        if len(parts) >= 3 and parts[1] == "creative-preview":
            preview_id = parts[2]
            if not CREATIVE_PREVIEW_ID.match(preview_id):
                return str(self.site_root / "__invalid_creative_preview__")
            rest = "/".join(parsed.path.split("/")[3:]) or "index.html"
            try:
                from creative_workbench import preview as creative_preview
            except Exception:
                return str(self.site_root / "__invalid_creative_preview__")
            target = creative_preview.resolve(
                self.creative_root, self.site_root, preview_id, rest)
            return str(target or self.site_root / "__invalid_creative_preview__")
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
        if parsed.path.startswith("/creative-preview/") and not parsed.path.endswith("/"):
            parts = parsed.path.split("/")
            if len(parts) == 3 and CREATIVE_PREVIEW_ID.match(parts[2]):
                self.send_response(301)
                self.send_header("Location", parsed.path + "/")
                self.end_headers()
                return
        if PAGE_PATH.match(parsed.path):
            try:
                with ABOUT_LOCK:
                    build_about.build()
            except build_about.AboutError as error:
                self._about_failed(error)
                return
        super().do_GET()

    def _about_failed(self, error):
        print(f"ABOUT 没有更新：{error}", flush=True)
        body = ("<!doctype html><meta charset=\"utf-8\"><title>ABOUT 需要修改</title>"
                "<body style=\"font: 16px/1.8 system-ui, sans-serif; padding: 40px; max-width: 720px\">"
                f"<h1 style=\"font-size: 20px\">ABOUT 的 md 文件需要修改</h1><p>{html.escape(str(error))}</p>"
                "<p>改好后保存，再刷新这个页面。</p>").encode("utf-8")
        self.send_response(500)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    creative_root = Path(os.environ.get("CREATIVE_ROOT") or CREATIVE).resolve()
    if "--creative-root" in argv:
        index = argv.index("--creative-root")
        if index + 1 >= len(argv):
            print("--creative-root 需要一个目录", flush=True)
            return 2
        creative_root = Path(argv[index + 1]).resolve()
        del argv[index:index + 2]
    try:
        port = int(argv[0]) if argv else 8766
    except ValueError:
        print(f"端口不合法：{argv[0]}", flush=True)
        return 2
    NoCacheHandler.site_root = SITE
    NoCacheHandler.creative_root = creative_root
    handler = functools.partial(NoCacheHandler, directory=str(SITE))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"预览地址：http://127.0.0.1:{port}/", flush=True)
        if DRAFTS.is_dir():
            print(f"草稿预览：http://127.0.0.1:{port}/preview/<draft-id>/", flush=True)
        if creative_root.is_dir():
            print(f"制作预览：http://127.0.0.1:{port}/creative-preview/<preview-id>/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
