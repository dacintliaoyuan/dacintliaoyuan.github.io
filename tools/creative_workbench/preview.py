"""Isolated drafts of the formal site: allowlisted overlays, baseline hashes, apply and rollback.

A draft lives in the creative workbench's own data root, never in the formal site:
``projects/<projectId>/previews/<previewId>/`` holds ``draft.json``, the files the
draft shadows under ``overlay/<site path>``, the originals taken before an apply under
``backup/<site path>``, and ``apply.json`` while an apply is in progress or done.

Only the allowlisted site files (``pointer-art.js``, ``pointer.js``, ``index.html``,
``styles.css``, ``main.js``, ``boot.js``, ``assets/manifest.js``, ``ornaments/*`` and
``assets/creative/*``) can be shadowed or written.  Everything else is read from the
formal site, read-only, by ``resolve``.  Creating, checking, and browsing a draft never
write the formal site; ``apply`` writes only the draft's own overlay files, after the
recorded baselines still match, and keeps a backup it can roll back to.
"""

from __future__ import annotations

import io
import re
import shutil
import urllib.parse
from pathlib import Path

from PIL import Image

from . import (
    FEATHER_SIZE,
    ROOT,
    CreativeError,
    digest_bytes,
    digest_file,
    new_id,
    now,
    overlay_allowed,
    read_json,
    relative_path,
    write_bytes_atomic,
    write_json_atomic,
)
from . import state as state_module

PREVIEW_ID = re.compile(r"^pv-[0-9a-f]{8}$")
# Formal files a draft depends on, whether or not it shadows them: a change to any of
# them means the draft was built against another site and must be checked again.
FORMAL_BASELINE = ("index.html", "main.js", "pointer.js", "pointer-art.js",
                   "assets/manifest.js", "styles.css", "boot.js")
APPLY_SCHEMA = 1


class PreviewApplyError(CreativeError):
    """An apply or rollback failed; ``rolledBack`` says whether the site was restored."""

    def __init__(self, message, rolled_back=False):
        super().__init__(message, status=500, rolledBack=bool(rolled_back))
        self.rolled_back = bool(rolled_back)


def _art():
    try:
        import pointer_art
    except ImportError as error:  # pragma: no cover - shipped beside the package
        raise CreativeError("指针图样工具不可用: tools/pointer_art.py") from error
    return pointer_art


def _inside(root, relative):
    """A resolved path under ``root`` for a safe site-relative path, else None."""
    if not isinstance(relative, str) or not relative:
        return None
    if "\\" in relative or "\x00" in relative:
        return None
    try:
        text = relative_path(relative, "站点路径")
    except CreativeError:
        return None
    try:
        root = Path(root).resolve()
        target = (root / text).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if not target.is_relative_to(root) or target == root:
        return None
    return target


def _digest(path):
    if path is None:
        return None
    try:
        if not Path(path).is_file():
            return None
        return digest_file(path)
    except OSError:
        return None


def _clean_overlay(value):
    """An allowlisted site-relative overlay path with no hidden segments."""
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise CreativeError(f"草稿覆盖路径不合法: {value!r}")
    if not overlay_allowed(value):
        raise CreativeError(f"草稿覆盖路径不在允许范围: {value}")
    if any(part.startswith(".") for part in value.split("/")):
        raise CreativeError(f"草稿覆盖路径不能以点开头: {value}")
    return value


def _formal(site_root, relative):
    return _inside(site_root, relative)


def _require_formal(site_root, relative):
    target = _formal(site_root, relative)
    if target is None or not target.is_file():
        raise CreativeError(f"正式站点缺少 {relative}；无法生成草稿")
    return target


def _baseline(site_root, overlay_paths, feather=None):
    names = set(FORMAL_BASELINE) | set(overlay_paths)
    if feather:
        names.add(feather)
    result = {}
    for name in sorted(names):
        if not overlay_allowed(name):
            continue
        result[name] = _digest(_formal(site_root, name))
    return result


def _pointer_bytes(source):
    module = _art()
    try:
        return module.generate_js(source).encode("utf-8")
    except module.PointerArtError as error:
        raise CreativeError(f"指针图样无法生成: {error}") from error


def _decode_png(payload, label):
    try:
        with Image.open(io.BytesIO(payload)) as probe:
            if probe.format != "PNG":
                raise CreativeError(f"{label}不是实际 PNG")
            if getattr(probe, "n_frames", 1) != 1:
                raise CreativeError(f"{label}必须是单帧 PNG")
            probe.verify()
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            return image.convert("RGBA")
    except CreativeError:
        raise
    except Exception as error:
        raise CreativeError(f"{label}无法完整解码: {error}") from error


def _feather_block(text):
    start = text.find("const FEATHER = {")
    if start < 0:
        raise CreativeError("正式 main.js 找不到 FEATHER 定义；无法生成羽毛草稿")
    end = text.find("\n  };", start)
    if end < 0:
        raise CreativeError("正式 main.js 的 FEATHER 定义不完整")
    end += len("\n  };")
    return start, end, text[start:end]


def _feather_number(block, key, default):
    match = re.search(rf"\b{key}:\s*(\d+)", block)
    return int(match.group(1)) if match else default


def _feather_files(store, site_root, project_id, version):
    """The feather PNG and the formal main.js pointing at it, plus the formal src."""
    if version.get("format") != "PNG":
        raise CreativeError("羽毛草稿需要 PNG 版本")
    version_path = store.path_for(version["path"])
    if not version_path.is_file():
        raise CreativeError("羽毛版本文件不存在")
    payload = version_path.read_bytes()
    rgba = _decode_png(payload, "羽毛版本")
    main_path = _require_formal(site_root, "main.js")
    try:
        text = main_path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        raise CreativeError(f"正式 main.js 不是 UTF-8 文本: {error}") from error
    start, end, feather = _feather_block(text)
    sources = re.findall(r"\bsrc:\s*'([^']*)'", feather)
    if len(sources) != 1:
        raise CreativeError("正式 main.js 的 FEATHER 没有唯一的 src；无法生成羽毛草稿")
    formal_src = sources[0]
    width = _feather_number(feather, "width", FEATHER_SIZE[0])
    height = _feather_number(feather, "height", FEATHER_SIZE[1])
    if [rgba.width, rgba.height] != [width, height]:
        raise CreativeError(
            f"羽毛版本尺寸 {rgba.width}×{rgba.height} 与正式羽毛 {width}×{height} 不一致")
    if rgba.getchannel("A").getextrema()[0] == 255:
        raise CreativeError("羽毛版本必须保留透明通道")
    formal_path = _formal(site_root, formal_src)
    if formal_path is None or not formal_path.is_file():
        raise CreativeError("找不到正式羽毛素材；无法核对轮廓")
    try:
        with Image.open(formal_path) as formal:
            formal.load()
            formal_rgba = formal.convert("RGBA")
    except Exception as error:
        raise CreativeError(f"正式羽毛无法读取: {error}") from error
    if formal_rgba.size != rgba.size:
        raise CreativeError("正式羽毛与版本尺寸不一致；无法核对轮廓")
    if formal_rgba.getchannel("A").tobytes() != rgba.getchannel("A").tobytes():
        raise CreativeError("新羽毛轮廓与正式羽毛不一致；本轮不自动生成 FEATHER 几何")
    name = f"ornaments/creative-{project_id}-{version['versionId']}.png"
    updated = re.sub(r"(\bsrc:\s*)'[^']*'",
                     lambda match: f"{match.group(1)}'{name}'",
                     feather, count=1)
    return {name: payload, "main.js": (text[:start] + updated + text[end:]).encode("utf-8")}, formal_src


def _draft_dir(store, project_id, preview_id):
    return store.path_for(f"projects/{project_id}/previews/{preview_id}")


def _overlay_root(draft_dir):
    """The draft's overlay directory, refusing one that resolves outside it."""
    try:
        draft_dir = Path(draft_dir).resolve()
        root = (draft_dir / "overlay").resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if not root.is_relative_to(draft_dir):
        return None
    return root


def _backup_root(draft_dir):
    """The draft's backup directory, refusing one that resolves outside it."""
    try:
        draft_dir = Path(draft_dir).resolve()
        root = (draft_dir / "backup").resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if not root.is_relative_to(draft_dir):
        return None
    return root


def _unique_preview(state):
    existing = {preview["previewId"] for project in state.get("projects") or []
                for preview in project.get("previews") or []}
    for _ in range(64):
        candidate = new_id("pv")
        if candidate not in existing:
            return candidate
    raise CreativeError("无法分配草稿 id；请检查状态")


def create(store, root, creative_root, site_root, project_id, version_id, overlays=None,
           name=None):
    """Build an isolated draft; only the creative data root is written."""
    root = Path(root or ROOT).resolve()
    site_root = Path(site_root or root / "site").resolve()
    project = state_module.find_project(store.read(), project_id)
    if project["status"] == "archived":
        raise CreativeError("项目已归档；不能创建制作草稿")
    version = state_module.find_version(project, version_id)
    kind = project["objectKind"]
    if overlays is None:
        overlays = []
    if not isinstance(overlays, list) or not all(isinstance(item, str) for item in overlays):
        raise CreativeError("overlays 必须是站点相对路径列表")
    overlays = [_clean_overlay(item) for item in overlays]
    if len(set(overlays)) != len(overlays):
        raise CreativeError("overlays 有重复路径")
    _require_formal(site_root, "index.html")
    feather = None
    if kind == "pointer":
        if overlays:
            raise CreativeError("指针草稿由服务端生成覆盖文件；不接受自定义 overlays")
        source = version.get("pointerSource")
        if not isinstance(source, dict):
            raise CreativeError("指针版本缺少 pointerSource；不能创建草稿")
        _require_formal(site_root, "pointer.js")
        files = {"pointer-art.js": _pointer_bytes(source)}
    elif kind == "feather":
        if overlays:
            raise CreativeError("羽毛草稿由服务端生成覆盖文件；不接受自定义 overlays")
        files, feather = _feather_files(store, site_root, project_id, version)
    elif kind == "bird":
        raise CreativeError("青鸟尚未接入正式主页；本轮不生成草稿")
    elif kind in ("star", "other"):
        if not overlays:
            raise CreativeError("星星/其他对象草稿必须显式给出 overlays")
        files = {}
        for relative in overlays:
            target = _formal(site_root, relative)
            if target is None or not target.is_file() or target.is_symlink():
                raise CreativeError(f"覆盖源文件不存在: {relative}", status=404)
            files[relative] = target.read_bytes()
    else:
        raise CreativeError(f"不支持的对象类型: {kind}")

    preview_id = _unique_preview(store.read())
    draft_dir = _draft_dir(store, project_id, preview_id)
    overlay_root = _overlay_root(draft_dir)
    if overlay_root is None:
        raise CreativeError("草稿覆盖目录越界；不能创建草稿")
    try:
        for relative, payload in files.items():
            write_bytes_atomic(overlay_root / relative, payload)
        preview = {
            "previewId": preview_id,
            "projectId": project_id,
            "versionId": version_id,
            "name": name if isinstance(name, str) and name.strip() else None,
            "status": "ready",
            "overlay": sorted(files),
            "baseline": _baseline(site_root, files, feather),
            "overlayHashes": {relative: digest_bytes(payload)
                              for relative, payload in files.items()},
            "createdAt": now(),
            "checkedAt": None,
            "appliedAt": None,
            "rolledBackAt": None,
            "note": None,
            "mismatches": [],
        }
        write_json_atomic(draft_dir / "draft.json", preview)
    except Exception:
        shutil.rmtree(draft_dir, ignore_errors=True)
        raise

    def add(state):
        project = state_module.find_project(state, project_id)
        if project["status"] == "archived":
            raise CreativeError("项目已归档；不能创建制作草稿")
        project["previews"].append(preview)
        state_module.touch(project)
        return preview

    try:
        return store.mutate(add)
    except Exception:
        shutil.rmtree(draft_dir, ignore_errors=True)
        raise


def _mismatches(draft_dir, site_root, preview):
    found = []
    overlay_root = _overlay_root(draft_dir)
    for relative, expected in sorted((preview.get("baseline") or {}).items()):
        actual = _digest(_formal(site_root, relative))
        if actual != expected:
            found.append({"path": relative, "expected": expected, "actual": actual,
                           "kind": "baseline"})
    for relative, expected in sorted((preview.get("overlayHashes") or {}).items()):
        actual = _digest(_inside(overlay_root, relative)) if overlay_root else None
        if actual != expected:
            found.append({"path": relative, "expected": expected, "actual": actual,
                           "kind": "overlay"})
    return found


def check(store, root, creative_root, site_root, project_id, preview_id):
    """Compare the recorded baselines and overlay hashes with the files on disk."""
    root = Path(root or ROOT).resolve()
    site_root = Path(site_root or root / "site").resolve()
    project = state_module.find_project(store.read(), project_id)
    preview = state_module.find_preview(project, preview_id)
    if preview.get("status") == "applied":
        raise CreativeError("草稿已应用；先回滚再检查")
    draft_dir = _draft_dir(store, project_id, preview_id)
    found = _mismatches(draft_dir, site_root, preview)
    status = "stale" if found else "ready"

    def update(state):
        project = state_module.find_project(state, project_id)
        record = state_module.find_preview(project, preview_id)
        record["status"] = status
        record["checkedAt"] = now()
        record["mismatches"] = found
        state_module.touch(project)
        return record

    return store.mutate(update)


def _site_target(site_root, relative):
    """A writable target inside the formal site, refusing symlinked parents."""
    try:
        root = Path(site_root).resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise CreativeError(f"正式站点目录不合法: {error}") from error
    if not root.is_dir():
        raise CreativeError(f"正式站点目录不存在: {root}")
    target = _inside(root, relative)
    if target is None:
        raise CreativeError(f"草稿目标越界: {relative}")
    if target.exists() and target.is_symlink():
        raise CreativeError(f"草稿目标不能是符号链接: {relative}")
    current = target.parent
    while current != root:
        if current.is_symlink():
            raise CreativeError(f"草稿目标父目录不能是符号链接: {relative}")
        current = current.parent
    return target


def _restore(draft_dir, site_root, entries):
    problems = []
    backup_root = _backup_root(draft_dir)
    if backup_root is None:
        return [str(entry.get("path") if isinstance(entry, dict) else entry)
                for entry in entries] or ["backup"]
    for entry in reversed(entries):
        if not isinstance(entry, dict):
            problems.append(str(entry))
            continue
        relative = entry.get("path")
        try:
            relative = _clean_overlay(relative)
            target = _site_target(site_root, relative)
        except CreativeError:
            problems.append(str(relative))
            continue
        try:
            if entry.get("existed"):
                backup = _inside(backup_root, relative)
                if backup is None or not backup.is_file():
                    problems.append(relative)
                    continue
                write_bytes_atomic(target, backup.read_bytes())
                if entry.get("backupSha256") and digest_file(target) != entry["backupSha256"]:
                    problems.append(relative)
            elif target.exists():
                target.unlink()
        except OSError:
            problems.append(relative)
    return problems


def _mark(store, project_id, preview_id, status, note=None):
    def update(state):
        project = state_module.find_project(state, project_id)
        record = state_module.find_preview(project, preview_id)
        record["status"] = status
        if status == "applied":
            record["appliedAt"] = record.get("appliedAt") or now()
            record["mismatches"] = []
        elif status == "rolled-back":
            record["rolledBackAt"] = now()
            record["mismatches"] = []
        elif status == "stale":
            record["mismatches"] = record.get("mismatches") or []
        if note is not None:
            record["note"] = note
        state_module.touch(project)
        return {"projectId": project_id, "previewId": preview_id, "status": status}

    return store.mutate(update)


def _require_asset_lock(site_root):
    """Refuse to write the formal site while an asset build holds its lock."""
    lock = Path(site_root) / ".assets-build.lock"
    if lock.exists():
        raise CreativeError("素材构建锁已被占用；请等构建结束或先核对现场", status=409)


def apply(store, root, creative_root, site_root, project_id, preview_id, confirm=False):
    """Write the draft's allowlisted files to the formal site after a fresh check."""
    if confirm is not True:
        raise CreativeError("应用制作草稿需要用户确认（confirm: true）")
    root = Path(root or ROOT).resolve()
    site_root = Path(site_root or root / "site").resolve()
    project = state_module.find_project(store.read(), project_id)
    preview = state_module.find_preview(project, preview_id)
    if preview.get("status") != "ready":
        raise CreativeError(f"草稿当前状态不能应用: {preview.get('status')}；请先检查")
    _require_asset_lock(site_root)
    checked = check(store, root, creative_root, site_root, project_id, preview_id)
    if checked.get("status") != "ready":
        raise CreativeError("正式站点基线已变化；请重新检查并合并", status=400,
                            mismatches=checked.get("mismatches") or [])
    draft_dir = _draft_dir(store, project_id, preview_id)
    overlay_root = _overlay_root(draft_dir)
    backup_root = _backup_root(draft_dir)
    if overlay_root is None or backup_root is None:
        raise CreativeError("草稿目录越界；不能应用")
    prepared = []
    for relative in sorted(preview.get("overlay") or []):
        relative = _clean_overlay(relative)
        source = _inside(overlay_root, relative)
        if source is None or not source.is_file():
            raise CreativeError(f"草稿覆盖文件缺失: {relative}")
        prepared.append((relative, source, _site_target(site_root, relative)))
    entries = []
    for relative, source, target in prepared:
        existed = target.exists()
        if existed and not target.is_file():
            raise CreativeError(f"正式站点目标不是文件: {relative}")
        backup_sha = None
        if existed:
            payload = target.read_bytes()
            backup_sha = digest_bytes(payload)
            backup = backup_root / relative
            write_bytes_atomic(backup, payload)
            if digest_file(backup) != backup_sha:
                raise CreativeError(f"草稿备份校验失败: {relative}")
        entries.append({"path": relative, "existed": existed,
                        "backupSha256": backup_sha})
    apply_path = draft_dir / "apply.json"
    document = {"schemaVersion": APPLY_SCHEMA, "previewId": preview_id,
                "projectId": project_id, "phase": "writing", "entries": entries,
                "startedAt": now(), "finishedAt": None}
    write_json_atomic(apply_path, document)
    try:
        for relative, source, target in prepared:
            write_bytes_atomic(target, source.read_bytes())
        write_json_atomic(apply_path, {**document, "phase": "done", "finishedAt": now()})

        def finish(state):
            project = state_module.find_project(state, project_id)
            record = state_module.find_preview(project, preview_id)
            record["status"] = "applied"
            record["appliedAt"] = now()
            record["mismatches"] = []
            state_module.touch(project)
            return record

        return store.mutate(finish)
    except Exception as error:
        problems = _restore(draft_dir, site_root, entries)
        write_json_atomic(apply_path, {**document, "phase": "rolled-back",
                                      "finishedAt": now()})
        try:
            _mark(store, project_id, preview_id, "stale", "应用失败，已回滚")
        except Exception:
            pass
        message = f"应用制作草稿失败，已回滚: {error}"
        if problems:
            message += f"；未能恢复: {', '.join(problems)}"
        raise PreviewApplyError(message, rolled_back=not problems) from error


def rollback(store, root, creative_root, site_root, project_id, preview_id):
    """Restore the backups an apply took, deleting the files it created."""
    root = Path(root or ROOT).resolve()
    site_root = Path(site_root or root / "site").resolve()
    project = state_module.find_project(store.read(), project_id)
    preview = state_module.find_preview(project, preview_id)
    if preview.get("status") != "applied":
        raise CreativeError(f"草稿当前状态不能回滚: {preview.get('status')}")
    _require_asset_lock(site_root)
    draft_dir = _draft_dir(store, project_id, preview_id)
    apply_path = draft_dir / "apply.json"
    if not apply_path.is_file():
        raise CreativeError("找不到应用记录；无法回滚", status=400)
    document = read_json(apply_path, "应用记录")
    if not isinstance(document, dict):
        raise CreativeError("应用记录损坏；无法回滚", status=400)
    entries = document.get("entries") or []
    if not isinstance(entries, list):
        raise CreativeError("应用记录损坏；无法回滚", status=400)
    for entry in entries:
        if not isinstance(entry, dict):
            raise CreativeError("应用记录损坏；无法回滚", status=400)
        relative = entry.get("path")
        if not entry.get("existed"):
            continue
        backup_root = _backup_root(draft_dir)
        backup = _inside(backup_root, relative) if backup_root and isinstance(relative, str) else None
        if backup is None or not backup.is_file():
            raise CreativeError(f"备份缺失: {relative}", status=400)
        if entry.get("backupSha256") and digest_file(backup) != entry["backupSha256"]:
            raise CreativeError(f"备份已变化: {relative}", status=400)
    problems = _restore(draft_dir, site_root, entries)
    if problems:
        raise PreviewApplyError(f"回滚未完成: {', '.join(problems)}", rolled_back=False)
    write_json_atomic(apply_path, {**document, "phase": "rolled-back",
                                  "finishedAt": now()})
    return _mark(store, project_id, preview_id, "rolled-back")


def cancel(store, root, creative_root, site_root, project_id, preview_id):
    """Discard a draft that was never applied; the formal site is not touched."""
    project = state_module.find_project(store.read(), project_id)
    preview = state_module.find_preview(project, preview_id)
    if preview.get("status") == "applied":
        raise CreativeError("草稿已应用；先回滚再取消")
    draft_dir = _draft_dir(store, project_id, preview_id)
    shutil.rmtree(draft_dir, ignore_errors=True)

    def update(state):
        project = state_module.find_project(state, project_id)
        record = state_module.find_preview(project, preview_id)
        record["status"] = "stale"
        record["note"] = "已取消"
        record["mismatches"] = []
        state_module.touch(project)
        return record

    return store.mutate(update)


def recover_previews(store, site_root=None):
    """Finish interrupted applies and keep applied drafts marked as applied.

    Site files are only restored when the caller names the site: recovery never
    assumes the repository's formal site.
    """
    site_root = Path(site_root).resolve() if site_root is not None else None
    changes = []
    for project in store.read().get("projects") or []:
        project_id = project["projectId"]
        for preview in project.get("previews") or []:
            preview_id = preview["previewId"]
            draft_dir = _draft_dir(store, project_id, preview_id)
            apply_path = draft_dir / "apply.json"
            if not apply_path.is_file():
                continue
            try:
                document = read_json(apply_path, "应用记录")
            except CreativeError as error:
                changes.append(_issue(store, project_id, "apply-record", str(error),
                                     f"projects/{project_id}/previews/{preview_id}/apply.json"))
                continue
            if not isinstance(document, dict):
                changes.append(_issue(store, project_id, "apply-record",
                                     "应用记录损坏", f"projects/{project_id}/previews/{preview_id}/apply.json"))
                continue
            phase = document.get("phase")
            entries = document.get("entries") or []
            if not isinstance(entries, list):
                changes.append(_issue(store, project_id, "apply-record",
                                     "应用记录损坏", f"projects/{project_id}/previews/{preview_id}/apply.json"))
                continue
            if phase == "writing":
                if site_root is None:
                    changes.append(_issue(
                        store, project_id, "apply-rolled-back",
                        "缺少正式站点目录；未回滚，请带站点目录重试",
                        f"projects/{project_id}/previews/{preview_id}"))
                    continue
                problems = _restore(draft_dir, site_root, entries)
                write_json_atomic(apply_path, {**document, "phase": "rolled-back",
                                              "finishedAt": now()})
                if problems:
                    changes.append(_issue(store, project_id, "apply-rolled-back",
                                         f"应用中断，部分文件未能恢复: {', '.join(problems)}",
                                         f"projects/{project_id}/previews/{preview_id}"))
                changes.append(_mark(store, project_id, preview_id, "stale",
                                    "应用中断，已回滚"))
            elif phase == "done" and preview.get("status") != "applied":
                changes.append(_mark(store, project_id, preview_id, "applied"))
            elif phase == "rolled-back" and preview.get("status") == "applied":
                changes.append(_mark(store, project_id, preview_id, "rolled-back"))
    return [change for change in changes if change]


def _issue(store, project_id, kind, message, path=None):
    def add(state):
        project = state_module.find_project(state, project_id)
        issue = state_module.add_issue(project, kind, message, path)
        if issue is None:
            return None
        state_module.touch(project)
        return {"projectId": project_id, "issue": issue}

    return store.mutate(add)


def _segments(url_path):
    if url_path is None:
        return ["index.html"]
    if isinstance(url_path, bytes):
        try:
            url_path = url_path.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if not isinstance(url_path, str):
        return None
    text = urllib.parse.unquote(url_path)
    if not text:
        return ["index.html"]
    if "\x00" in text or "\\" in text or text.startswith("/"):
        return None
    if re.match(r"^[A-Za-z]:", text):
        return None
    parts = text.split("/")
    if any(part in ("", ".", "..") or part.startswith(".") for part in parts):
        return None
    return parts


def _find_draft(creative_root, preview_id):
    if not creative_root.is_dir():
        return None
    found = []
    for path in creative_root.glob(f"projects/*/previews/{preview_id}/draft.json"):
        if path.is_file():
            found.append(path.parent)
    if len(found) != 1:
        return None
    try:
        resolved = found[0].resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if not resolved.is_relative_to(creative_root):
        return None
    return found[0]


def resolve(creative_root, site_root, preview_id, url_path):
    """The file a preview URL serves: the draft's overlay first, then the formal site."""
    if not isinstance(preview_id, str) or not PREVIEW_ID.match(preview_id):
        return None
    try:
        creative_root = Path(creative_root).resolve()
        site_root = Path(site_root).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    draft_dir = _find_draft(creative_root, preview_id)
    if draft_dir is None:
        return None
    segments = _segments(url_path)
    if segments is None:
        return None
    relative = "/".join(segments)
    overlay_root = _overlay_root(draft_dir)
    if overlay_root is not None and overlay_allowed(relative):
        target = _inside(overlay_root, relative)
        if target is not None and target.is_file():
            return target
    target = _inside(site_root, relative)
    if target is not None and target.is_file():
        return target
    return None
