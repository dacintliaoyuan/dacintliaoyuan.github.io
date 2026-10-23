"""Content-addressed originals, safe ingestion, and inbox scanning."""

from __future__ import annotations

import hashlib
import os
import shutil
import time
import uuid
from pathlib import Path

from PIL import Image

from . import state as state_module


IMAGE_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "BMP": ".bmp", "TIFF": ".tif", "GIF": ".gif"}
MAX_UPLOAD = 200 * 1024 * 1024
STABLE_SECONDS = 1.0


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def resolve_inside(root, value):
    root = Path(root).resolve()
    if not isinstance(value, str) or not value.strip():
        raise ValueError("路径不能为空")
    candidate = (root / value).resolve()
    if not candidate.is_relative_to(root) or candidate == root:
        raise ValueError(f"路径越界: {value}")
    return candidate


def safe_name(value, fallback="image"):
    name = Path(str(value or "")).name.strip().replace("\x00", "")
    name = "".join(c if ord(c) >= 32 and c not in '<>:"/\\|?*' else "_" for c in name)
    name = name.strip(" .")[:120]
    return name or fallback


def inspect_bytes(data):
    import io
    try:
        with Image.open(io.BytesIO(data)) as image:
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("只接受单帧静态图片")
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            image_format = image.format
            size = list(image.size)
            mode = image.mode
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(f"无法解码图片: {error}") from error
    if image_format not in IMAGE_FORMATS:
        raise ValueError(f"不支持的图片格式: {image_format or '未知'}")
    return {"format": image_format, "size": size, "mode": mode, "extension": IMAGE_FORMATS[image_format]}


def _copy_verified(source, destination, expected_sha=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part-" + uuid.uuid4().hex)
    hasher = hashlib.sha256()
    try:
        with Path(source).open("rb") as reader, temporary.open("xb") as writer:
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                hasher.update(chunk)
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        actual = hasher.hexdigest()
        if expected_sha and actual != expected_sha:
            raise ValueError("复制期间文件内容发生变化")
        if destination.exists():
            if digest(destination) != actual:
                raise ValueError(f"同名内容寻址文件内容不一致: {destination}")
            temporary.unlink()
        else:
            os.replace(temporary, destination)
        return actual
    finally:
        if temporary.exists():
            temporary.unlink()


def ingest_bytes(library, data, filename):
    library = Path(library).resolve()
    if len(data) > MAX_UPLOAD:
        raise ValueError("图片超过 200 MB 上限")
    info = inspect_bytes(data)
    sha256 = hashlib.sha256(data).hexdigest()
    destination = library / "originals" / sha256[:2] / f"{sha256}{info['extension']}"
    if destination.exists():
        if digest(destination) != sha256:
            raise ValueError(f"内容寻址文件哈希不一致: {destination}")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".part-" + uuid.uuid4().hex)
        try:
            with temporary.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if digest(temporary) != sha256:
                raise ValueError("写入原图后哈希不一致")
            if destination.exists():
                temporary.unlink()
            else:
                os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
    return {
        "path": destination.relative_to(library).as_posix(),
        "sha256": sha256,
        "size": info["size"],
        "format": info["format"],
        "mode": info["mode"],
        "bytes": len(data),
        "filename": safe_name(filename),
    }


def ingest_path(library, source, filename=None):
    library = Path(library).resolve()
    source = Path(source)
    if not source.is_file():
        raise ValueError(f"找不到图片: {source}")
    if source.stat().st_size > MAX_UPLOAD:
        raise ValueError("图片超过 200 MB 上限")
    data = source.read_bytes()
    info = inspect_bytes(data)
    sha256 = hashlib.sha256(data).hexdigest()
    destination = library / "originals" / sha256[:2] / f"{sha256}{info['extension']}"
    _copy_verified(source, destination, sha256)
    return {
        "path": destination.relative_to(library).as_posix(),
        "sha256": sha256,
        "size": info["size"],
        "format": info["format"],
        "mode": info["mode"],
        "bytes": len(data),
        "filename": safe_name(filename or source.name),
    }


def create_item(state, record, batch_id, filename=None):
    number = int(state["nextItem"])
    state["nextItem"] = number + 1
    item_id = f"img-{number:04d}"
    duplicate = next((item["id"] for item in state["items"]
                      if item["original"]["sha256"] == record["sha256"]), None)
    item = {
        "id": item_id,
        "number": number,
        "filename": safe_name(filename or record.get("filename") or record["path"]),
        "receivedAt": state_module.now(),
        "batchId": batch_id,
        "duplicateOf": duplicate,
        "original": {key: record[key] for key in ("path", "sha256", "size", "format", "bytes")},
        "status": state_module.RECEIVED,
        "settings": dict(state.get("settings") or state_module.DEFAULT_SETTINGS),
        "analysis": None,
        "versions": [],
        "planRevision": 0,
        "aiTaskId": None,
        "pendingConfirmation": False,
        "adoptedVersion": None,
        "draftId": None,
        "enabledId": None,
        "time": None,
        "timeChoice": None,
        "timeSuggestion": None,
        "currentVersions": None,
        "processingRound": 0,
        "error": None,
        "history": [{"status": state_module.RECEIVED, "at": state_module.now()}],
    }
    state["items"].append(item)
    return item


def stable_inbox_file(path, now=None, previous=None):
    """True once a dropped file has stopped growing for a moment."""
    try:
        stat = Path(path).stat()
    except OSError:
        return False
    if not Path(path).is_file() or Path(path).suffix.lower() in (".part", ".tmp", ".crdownload"):
        return False
    if previous and previous.get("size") == stat.st_size and previous.get("mtime_ns") == stat.st_mtime_ns:
        return True
    if time.time() - stat.st_mtime < STABLE_SECONDS:
        return False
    return True


def scan_inbox(store, batch_id=None):
    """Ingest stable files from the watched folder; never move or delete them."""
    root = store.root
    inbox = root / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    ingested = []
    for path in sorted(inbox.iterdir()):
        if not path.is_file() or path.name.startswith(".") or path.suffix.lower() in (".part", ".tmp", ".crdownload"):
            continue
        stat = path.stat()
        marker = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        previous = store.read()["inbox"].get(path.name)
        if previous and previous.get("size") == marker["size"] and previous.get("mtime_ns") == marker["mtime_ns"]:
            continue
        if time.time() - stat.st_mtime < STABLE_SECONDS:
            continue
        try:
            record = ingest_path(root, path)
        except (ValueError, OSError) as error:
            store.mutate(lambda state: state["inbox"].__setitem__(
                path.name, {**marker, "error": str(error), "at": state_module.now()}))
            continue

        def add(state):
            item = create_item(state, record, batch_id or f"inbox-{state_module.now()[:10]}", path.name)
            state["inbox"][path.name] = {
                **marker, "sha256": record["sha256"], "itemId": item["id"], "at": state_module.now()}
            return item["id"]

        ingested.append(store.mutate(add))
    return ingested
