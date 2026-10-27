"""Creative workbench: projects, references, GPT Image handoff jobs, and manual edits.

The creative workbench owns its own schema-1 state under
``.local/output/creative-assets``; it never writes the picture library state and
never touches the formal site.  This module only holds constants, shared errors,
and small filesystem helpers; submodules are imported by their callers.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CREATIVE = ROOT / ".local" / "output" / "creative-assets"
SCHEMA_VERSION = 1
MAX_PROJECTS = 200
MAX_UPLOAD = 200 * 1024 * 1024

PROJECT_STATUSES = ("draft", "research", "reference-confirmed", "awaiting-image",
                    "review", "adopted", "archived")
PROJECT_TRANSITIONS = {
    "draft": {"research", "reference-confirmed", "review", "archived"},
    "research": {"reference-confirmed", "draft", "review", "awaiting-image", "archived"},
    "reference-confirmed": {"awaiting-image", "research", "review", "archived"},
    "awaiting-image": {"review", "adopted", "awaiting-image", "reference-confirmed", "archived"},
    "review": {"adopted", "awaiting-image", "review", "research",
               "reference-confirmed", "archived"},
    "adopted": {"review", "awaiting-image", "adopted", "research", "archived"},
    "archived": set(),
}
OBJECT_KINDS = ("pointer", "feather", "bird", "star", "other")
REFERENCE_KINDS = ("image", "link", "film-frame")
JOB_KINDS = ("research", "image", "motion")
JOB_OPERATIONS = {
    "research": ("research",),
    "image": ("generate", "edit", "inpaint"),
    "motion": ("motion",),
}
JOB_STATUSES = ("waiting", "done", "rejected", "late", "conflict", "cancelled", "superseded")
VERSION_SOURCES = ("original", "gpt-image", "gpt-image-inpaint",
                   "manual-piskel", "manual-krita", "generated")
VERSION_FORMATS = ("PNG", "JSON", "WEBP")
CONFIRMATION_STATUSES = ("active", "stale", "superseded")
PREVIEW_STATUSES = ("ready", "stale", "applied", "rolled-back")

POINTER_ROLES = ("shima", "adachi", "full")
POINTER_LAYER_ROLES = ("shima", "adachi")
POINTER_EXPRESSIONS = ("open", "shut", "happy", "squint")
POINTER_SIZE = (46, 27)
POINTER_WIDTH, POINTER_HEIGHT = POINTER_SIZE
FEATHER_SIZE = (350, 512)
EDITORS = ("piskel", "krita")

OVERLAY_EXACT = frozenset({
    "pointer-art.js", "pointer.js", "index.html", "styles.css",
    "main.js", "boot.js", "assets/manifest.js",
})
OVERLAY_PREFIXES = ("ornaments/", "assets/creative/")

ID_PATTERNS = {
    "project": re.compile(r"^cp-\d{4}-[0-9a-f]{8}$"),
    "reference": re.compile(r"^ref-[0-9a-f]{8}$"),
    "confirmation": re.compile(r"^cf-[0-9a-f]{8}$"),
    "job": re.compile(r"^job-[0-9a-f]{8}$"),
    "version": re.compile(r"^ver-[0-9a-f]{8}$"),
    "preview": re.compile(r"^pv-[0-9a-f]{8}$"),
    "export": re.compile(r"^mx-[0-9a-f]{8}$"),
}

PALETTE_ORDER = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


class CreativeError(Exception):
    """A creative workbench request that the API can answer with its status."""

    def __init__(self, message, status=400, **extra):
        super().__init__(message)
        self.status = status
        self.extra = extra


class CreativeStateError(CreativeError):
    """Creative state is missing, unreadable, or would become invalid."""

    def __init__(self, message, status=503):
        super().__init__(message, status=status)


class PointerArtError(CreativeError):
    """Pointer art source, PNG, or Piskel document is not usable."""

    def __init__(self, message, status=400):
        super().__init__(message, status=status)


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def id_matches(kind, value):
    pattern = ID_PATTERNS.get(kind)
    return isinstance(value, str) and bool(pattern and pattern.match(value))


def is_hash(value):
    return (isinstance(value, str) and len(value) == 64
            and all(char in "0123456789abcdef" for char in value))


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def digest_file(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def relative_path(value, label="路径", prefix=None):
    """Return a normalised creative-relative path or raise CreativeError."""
    if not isinstance(value, str) or not value.strip():
        raise CreativeError(f"{label}不能为空")
    text = value.replace("\\", "/")
    if text.startswith("/") or (len(text) >= 2 and text[1] == ":"):
        raise CreativeError(f"{label}必须是相对路径")
    parts = text.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise CreativeError(f"{label}越界: {value}")
    if ":" in parts[0]:
        raise CreativeError(f"{label}必须是相对路径")
    if prefix and not text.startswith(prefix):
        raise CreativeError(f"{label}必须位于 {prefix} 下")
    return text


def overlay_allowed(value):
    """True for site-relative draft overlay paths the workbench may shadow."""
    if not isinstance(value, str) or not value:
        return False
    try:
        text = relative_path(value, "草稿覆盖")
    except CreativeError:
        return False
    if text in OVERLAY_EXACT:
        return True
    return any(text.startswith(prefix) and len(text) > len(prefix)
               for prefix in OVERLAY_PREFIXES)


def write_bytes_atomic(path, data):
    """Write bytes to ``path`` through a same-directory temporary file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part-" + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_json_atomic(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    write_bytes_atomic(path, data)


def read_json(path, label="JSON"):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CreativeError(f"{label}无法读取: {error}")
