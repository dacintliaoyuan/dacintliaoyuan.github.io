"""Source coverage observations and bounded downloads of explicitly supplied images.

Coverage applies only to the page or scope described by one source record. A
successful HTTP request never marks an account's history as fully inspected.
"""

import copy
import hashlib
import json
import math
import os
import socket
import tempfile
import time
import warnings
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from PIL import Image, ImageSequence, UnidentifiedImageError


COVERAGE_STATUSES = (
    "not_checked", "checked", "access_restricted", "only_preview",
    "original_found", "no_match_found",
)
SOURCE_STATUSES = COVERAGE_STATUSES
MAX_DECODED_PIXELS = 100_000_000
MAX_IMAGE_FRAMES = 200


class DownloadError(ValueError):
    """A rejected or failed download, with the observed HTTP status if available."""

    def __init__(self, message, *, status=None):
        self.status = status
        prefix = f"HTTP {status}: " if status is not None else ""
        super().__init__(prefix + message)


def _text(value, name, *, nonempty=True):
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise ValueError(f"{name} 必须是{'非空' if nonempty else ''}文本")
    if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
        raise ValueError(f"{name} 含有无效控制字符")


def _http_url(value):
    _text(value, "URL")
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value) or "\\" in value:
        raise ValueError("URL 不允许空白、控制字符或反斜杠")
    try:
        parts = urlsplit(value)
        hostname = parts.hostname
        parts.port
    except ValueError as error:
        raise ValueError("URL 格式不合法") from error
    if parts.scheme.lower() not in ("http", "https") or not hostname:
        raise ValueError("来源 URL 必须是有主机名的 http(s) 地址")
    if parts.username is not None or parts.password is not None:
        raise ValueError("URL 不允许携带账号或密码")
    return value


def _timestamp(value):
    _text(value, "checkedAt")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("checkedAt 必须是 ISO 时间") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("checkedAt 必须包含时区")


def validate_source(record):
    """Validate coverage data without inferring a result from URLs or evidence."""
    if not isinstance(record, dict):
        raise ValueError("来源记录必须是对象")
    required = {"id", "category", "title", "pageUrl", "status", "checkedAt", "note", "evidence", "artworkIds"}
    missing = required.difference(record)
    if missing:
        raise ValueError("来源记录缺少字段: " + ", ".join(sorted(missing)))
    for key in ("id", "category", "title"):
        _text(record[key], key)
    _http_url(record["pageUrl"])
    if record["status"] not in COVERAGE_STATUSES:
        raise ValueError(f"无效来源状态: {record['status']}")
    if record["status"] == "not_checked":
        if record["checkedAt"] is not None:
            raise ValueError("not_checked 的 checkedAt 必须为 null")
    else:
        _timestamp(record["checkedAt"])
    _text(record["note"], "note", nonempty=False)
    if not isinstance(record["evidence"], list):
        raise ValueError("evidence 必须是数组")
    for evidence in record["evidence"]:
        if isinstance(evidence, str):
            _text(evidence, "evidence 条目")
        elif isinstance(evidence, dict) and evidence:
            try:
                json.dumps(evidence, allow_nan=False)
            except (TypeError, ValueError) as error:
                raise ValueError("evidence 对象必须可保存为 JSON") from error
        else:
            raise ValueError("evidence 条目必须是非空文本或 JSON 对象")
    if not isinstance(record["artworkIds"], list):
        raise ValueError("artworkIds 必须是数组")
    for artwork_id in record["artworkIds"]:
        _text(artwork_id, "artworkIds 条目")
    if len(set(record["artworkIds"])) != len(record["artworkIds"]):
        raise ValueError("artworkIds 不允许重复")


def set_observation(record, status, note, evidence=(), checked_at=None):
    """Return a new explicit observation; leave the input and nested data intact."""
    validate_source(record)
    if status not in COVERAGE_STATUSES:
        raise ValueError(f"无效来源状态: {status}")
    if isinstance(evidence, (str, bytes, dict)):
        raise ValueError("evidence 必须是条目序列")
    if status == "not_checked" and checked_at is not None:
        raise ValueError("not_checked 不接受检查时间")
    result = copy.deepcopy(record)
    try:
        observed_evidence = copy.deepcopy(list(evidence))
    except TypeError as error:
        raise ValueError("evidence 必须是条目序列") from error
    result.update(
        status=status,
        note=note,
        evidence=observed_evidence,
        checkedAt=None if status == "not_checked" else (
            checked_at if checked_at is not None else datetime.now(timezone.utc).isoformat(timespec="seconds")
        ),
    )
    validate_source(result)
    return result


def summarize(sources):
    """Count explicit coverage states, including zero counts for every state."""
    if not isinstance(sources, list):
        raise ValueError("来源清单必须是数组")
    counts = dict.fromkeys(COVERAGE_STATUSES, 0)
    seen = set()
    for record in sources:
        validate_source(record)
        if record["id"] in seen:
            raise ValueError(f"来源 id 重复: {record['id']}")
        seen.add(record["id"])
        counts[record["status"]] += 1
    return counts


class _SafeRedirect(HTTPRedirectHandler):
    max_redirections = 5

    def __init__(self, deadline):
        self.deadline = deadline

    def redirect_request(self, request, stream, code, message, headers, new_url):
        try:
            _http_url(new_url)
        except ValueError as error:
            raise DownloadError(f"拒绝不安全的重定向: {error}", status=code) from error
        return super().redirect_request(request, stream, code, message, headers, new_url)

    def http_error_302(self, request, stream, code, message, headers):
        # urllib's default redirect handler drains an unbounded response body.
        # Closing it instead keeps redirect pages out of the image body budget.
        try:
            location = headers.get("Location") or headers.get("URI")
            if not location:
                raise DownloadError("重定向响应缺少目标地址", status=code)
            count = getattr(request, "art_redirect_count", 0)
            if count >= self.max_redirections:
                raise DownloadError("超过允许的重定向次数", status=code)
            try:
                new_url = urljoin(request.full_url, location)
            except ValueError as error:
                raise DownloadError("重定向目标地址不合法", status=code) from error
            new_request = self.redirect_request(request, stream, code, message, headers, new_url)
            if new_request is None:
                raise DownloadError("无法处理图片重定向", status=code)
            new_request.art_redirect_count = count + 1
        finally:
            stream.close()
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise DownloadError("图片重定向超过时间限制", status=code)
        return self.parent.open(new_request, timeout=remaining)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def _destination(library, destination):
    root = Path(library).resolve()
    if not root.is_dir():
        raise ValueError("指定图库目录不存在")
    supplied = Path(destination)
    supplied = supplied if supplied.is_absolute() else root / supplied
    path = supplied.resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("下载目标必须是指定图库内的文件")
    if supplied.is_symlink() or path.exists():
        raise FileExistsError(f"下载目标已存在，不会覆盖: {path}")
    return root, path


def _decoded_size(path, status):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                size = list(image.size)
                pixels = 0
                for index, frame in enumerate(ImageSequence.Iterator(image), 1):
                    pixels += frame.width * frame.height
                    if index > MAX_IMAGE_FRAMES or pixels > MAX_DECODED_PIXELS:
                        raise DownloadError("图片解码规模超过限制", status=status)
                    frame.load()
                return size
    except DownloadError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise DownloadError("响应不是完整可解码的图片", status=status) from error


def download_image(url, library, destination, timeout=30, max_bytes=50 * 1024 * 1024):
    """Download only this URL into a new file, preserving the received image bytes.

    Existing targets are rejected, including race-created ones. The caller owns
    hash-based reuse. Temporary files share the target directory, then a hard
    link publishes the fully decoded result atomically without overwriting.
    Network operations have a timeout and an elapsed deadline is checked between
    body reads. Redirects are bounded and cannot change to a non-HTTP scheme.
    """
    _http_url(url)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout 必须是正数秒")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("max_bytes 必须是正整数")
    root, target = _destination(library, destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.parent.resolve().is_relative_to(root):
        raise ValueError("下载目标目录已移出指定图库")
    temp_path = None
    status = None
    deadline = time.monotonic() + timeout
    try:
        request = Request(url, headers={"User-Agent": "HomepageArtPipeline/1.0", "Accept": "image/*"})
        with build_opener(_SafeRedirect(deadline)).open(request, timeout=timeout) as response:
            status = response.status
            if status != 200:
                raise DownloadError("图片下载只接受完整 HTTP 200 响应", status=status)
            final_url = _http_url(response.geturl())
            content_type = response.headers.get_content_type()
            if not content_type.startswith("image/") and content_type not in ("application/octet-stream", "binary/octet-stream"):
                raise DownloadError(f"响应类型不是图片: {content_type}", status=status)
            content_length = response.headers.get("Content-Length")
            expected = None
            if content_length is not None:
                try:
                    expected = int(content_length)
                except ValueError as error:
                    raise DownloadError("Content-Length 不合法", status=status) from error
                if expected < 0:
                    raise DownloadError("Content-Length 不合法", status=status)
                if expected > max_bytes:
                    raise DownloadError("图片响应超过大小限制", status=status)
            descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.download-", suffix=".tmp", dir=target.parent)
            temp_path = Path(name)
            received = 0
            with os.fdopen(descriptor, "wb") as output:
                while True:
                    if time.monotonic() >= deadline:
                        raise DownloadError("图片下载超过时间限制", status=status)
                    # read1 returns after one buffered/network read instead of
                    # waiting for an entire chunk from a slowly trickling body.
                    chunk = response.read1(min(64 * 1024, max_bytes + 1 - received))
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > max_bytes:
                        raise DownloadError("图片响应超过大小限制", status=status)
                    output.write(chunk)
                if expected is not None and received != expected:
                    raise DownloadError("响应提前结束，图片长度不完整", status=status)
                output.flush()
                os.fsync(output.fileno())
        size = _decoded_size(temp_path, status)
        digest = hashlib.sha256()
        with temp_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if not target.parent.resolve().is_relative_to(root):
            raise DownloadError("下载目标目录已移出指定图库", status=status)
        os.link(temp_path, target)
        return {"path": target.relative_to(root).as_posix(), "sha256": digest.hexdigest(),
                "size": size, "url": url, "finalUrl": final_url}
    except HTTPError as error:
        error.close()
        raise DownloadError(f"下载被服务端拒绝: {error.reason}", status=error.code) from error
    except DownloadError:
        raise
    except (URLError, HTTPException, ConnectionError, TimeoutError, socket.timeout) as error:
        raise DownloadError(f"图片下载网络失败或超时: {error}", status=status) from error
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
