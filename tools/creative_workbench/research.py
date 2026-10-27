"""Projects, references, user confirmations, and the server-side reference gate."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image

from . import (
    MAX_PROJECTS,
    MAX_UPLOAD,
    OBJECT_KINDS,
    POINTER_EXPRESSIONS,
    POINTER_LAYER_ROLES,
    POINTER_ROLES,
    CreativeError,
    new_id,
    now,
    write_bytes_atomic,
)
from . import state as state_module

IMAGE_FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


def text(value, label, allow_empty=False):
    if not isinstance(value, str):
        raise CreativeError(f"{label}必须为字符串")
    if not allow_empty and not value.strip():
        raise CreativeError(f"{label}不能为空")
    return value


def string_list(value, label):
    """Accept a list, or a '|'-separated string from a query parameter."""
    if value is None:
        return []
    if isinstance(value, str):
        value = [part.strip() for part in value.split("|") if part.strip()]
    if not isinstance(value, list):
        raise CreativeError(f"{label}必须为字符串列表")
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise CreativeError(f"{label}必须为字符串列表")
        result.append(item.strip())
    return result


def inspect_image_bytes(data):
    """Decode a single-frame reference image and report its format and size."""
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise CreativeError("参考图片为空")
    if len(data) > MAX_UPLOAD:
        raise CreativeError("参考图片超过 200 MB 上限")
    try:
        with Image.open(io.BytesIO(bytes(data))) as image:
            if getattr(image, "n_frames", 1) != 1:
                raise CreativeError("只接受单帧静态图片")
            image.verify()
        with Image.open(io.BytesIO(bytes(data))) as image:
            image.load()
            image_format = image.format
            size = list(image.size)
    except CreativeError:
        raise
    except Exception as error:
        raise CreativeError(f"无法解码图片: {error}") from error
    if image_format not in IMAGE_FORMATS:
        raise CreativeError(f"不支持的参考图片格式: {image_format or '未知'}")
    return {"format": image_format, "size": size, "extension": IMAGE_FORMATS[image_format]}


def transition_project(project, status):
    return state_module.transition_project(project, status)


def create_project(store, name, object_kind, purpose=""):
    name = text(name, "项目名称")
    if object_kind not in OBJECT_KINDS:
        raise CreativeError(f"项目对象类型不合法: {object_kind}")
    if not isinstance(purpose, str):
        raise CreativeError("项目用途必须为字符串")

    def add(state):
        if len(state.get("projects") or []) >= MAX_PROJECTS:
            raise CreativeError(f"项目数超过上限（{MAX_PROJECTS}）")
        number = int(state["nextProject"])
        stamp = now()
        project = {
            "projectId": f"cp-{number:04d}-{new_id('x').split('-', 1)[1]}",
            "number": number,
            "name": name,
            "objectKind": object_kind,
            "purpose": purpose,
            "status": "draft",
            "createdAt": stamp,
            "updatedAt": stamp,
            "revision": 0,
            "selectedVersionId": None,
            "references": [],
            "confirmations": [],
            "jobs": [],
            "versions": [],
            "previews": [],
            "researchReports": [],
            "motionNotes": [],
            "manualExports": [],
            "issues": [],
        }
        state["nextProject"] = number + 1
        state["projects"].append(project)
        return project

    return store.mutate(add)


def _active(store, project_id, allow_archived=False):
    project = state_module.find_project(store.read(), project_id)
    if project["status"] == "archived" and not allow_archived:
        raise CreativeError("项目已归档；请先恢复项目")
    return project


def archive_project(store, project_id):
    def archive(state):
        project = state_module.find_project(state, project_id)
        if project["status"] == "archived":
            raise CreativeError("项目已归档")
        state_module.mark_stale(
            project, [reference["referenceId"] for reference in project["references"]],
            "项目已归档")
        project["status"] = "archived"
        state_module.touch(project)
        return project

    return store.mutate(archive)


def add_reference_file(store, project_id, data, filename=None, title=None,
                        kind="image", timecode=None, note=None,
                        findings="", uncertainties=None):
    if kind not in ("image", "film-frame"):
        raise CreativeError("文件参考类型必须是 image 或 film-frame")
    info = inspect_image_bytes(data)
    _active(store, project_id)
    reference_id = new_id("ref")
    relative = f"projects/{project_id}/references/{reference_id}{info['extension']}"
    findings = findings if isinstance(findings, str) else ""
    uncertainties = string_list(uncertainties, "参考不确定处")
    stamp = now()
    source = {"uri": relative}
    if timecode:
        source["timecode"] = str(timecode)
    if note:
        source["note"] = str(note)
    reference = {
        "referenceId": reference_id,
        "revision": 1,
        "kind": kind,
        "title": text(title, "参考标题", allow_empty=True) if title else (
            Path(filename).stem if filename else "参考"),
        "source": source,
        "path": relative,
        "sha256": hashlib.sha256(bytes(data)).hexdigest(),
        "size": info["size"],
        "format": info["format"],
        "findings": findings,
        "uncertainties": uncertainties,
        "createdAt": stamp,
        "updatedAt": stamp,
        "missing": False,
    }
    path = store.path_for(relative)
    write_bytes_atomic(path, bytes(data))

    def add(state):
        project = state_module.find_project(state, project_id)
        if project["status"] == "archived":
            raise CreativeError("项目已归档；请先恢复项目")
        project["references"].append(reference)
        state_module.sync_gate_status(project)
        return reference

    try:
        return store.mutate(add)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def add_reference_link(store, project_id, title, uri, kind="link", timecode=None,
                       note=None, findings="", uncertainties=None):
    title = text(title, "参考标题")
    uri = text(uri, "参考链接")
    lowered = uri.strip().lower()
    if lowered.startswith(("javascript:", "data:")):
        raise CreativeError("不接受 javascript: 或 data: 链接")
    if kind not in ("link", "film-frame"):
        raise CreativeError("链接参考类型必须是 link 或 film-frame")
    _active(store, project_id)
    stamp = now()
    source = {"uri": uri}
    if timecode:
        source["timecode"] = str(timecode)
    if note:
        source["note"] = str(note)
    reference = {
        "referenceId": new_id("ref"),
        "revision": 1,
        "kind": kind,
        "title": title,
        "source": source,
        "path": None,
        "sha256": None,
        "size": None,
        "format": None,
        "findings": findings if isinstance(findings, str) else "",
        "uncertainties": string_list(uncertainties, "参考不确定处"),
        "createdAt": stamp,
        "updatedAt": stamp,
        "missing": False,
    }

    def add(state):
        project = state_module.find_project(state, project_id)
        if project["status"] == "archived":
            raise CreativeError("项目已归档；请先恢复项目")
        project["references"].append(reference)
        state_module.sync_gate_status(project)
        return reference

    return store.mutate(add)


def replace_reference(store, project_id, reference_id, data, filename=None):
    info = inspect_image_bytes(data)
    project = _active(store, project_id)
    current = state_module.find_reference(project, reference_id)
    if current["kind"] == "link":
        raise CreativeError("链接参考没有本地文件，不能替换")
    revision = int(current.get("revision") or 0) + 1
    relative = (f"projects/{project_id}/references/"
                f"{reference_id}-r{revision}{info['extension']}")
    path = store.path_for(relative)
    write_bytes_atomic(path, bytes(data))
    digest = hashlib.sha256(bytes(data)).hexdigest()
    stamp = now()

    def apply(state):
        project = state_module.find_project(state, project_id)
        if project["status"] == "archived":
            raise CreativeError("项目已归档；请先恢复项目")
        reference = state_module.find_reference(project, reference_id)
        if reference["kind"] == "link":
            raise CreativeError("链接参考没有本地文件，不能替换")
        if int(reference.get("revision") or 0) + 1 != revision:
            raise CreativeError("参考已被其他操作替换；请刷新后重试")
        reference.update({
            "revision": revision,
            "path": relative,
            "sha256": digest,
            "size": info["size"],
            "format": info["format"],
            "missing": False,
            "updatedAt": stamp,
        })
        if filename and not reference.get("title"):
            reference["title"] = Path(filename).stem
        state_module.mark_stale(project, [reference_id], "参考已替换")
        state_module.sync_gate_status(project)
        return reference

    try:
        return store.mutate(apply)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def confirm_reference(store, project_id, reference_ids, allowed_changes, preserved,
                      note=""):
    reference_ids = string_list(reference_ids, "参考清单")
    if not reference_ids:
        raise CreativeError("确认参考至少需要一个参考")
    if len(set(reference_ids)) != len(reference_ids):
        raise CreativeError("参考清单重复")
    allowed_changes = string_list(allowed_changes, "允许改动")
    preserved = string_list(preserved, "保留项")
    if note is None:
        note = ""
    if not isinstance(note, str):
        raise CreativeError("确认说明必须为字符串")
    _active(store, project_id)

    def add(state):
        project = state_module.find_project(state, project_id)
        if project["status"] == "archived":
            raise CreativeError("项目已归档；请先恢复项目")
        hashes = {}
        for reference_id in reference_ids:
            reference = state_module.get_reference(project, reference_id)
            if reference is None:
                raise CreativeError(f"找不到参考: {reference_id}", status=404)
            hashes[reference_id] = reference.get("sha256")
        confirmation = {
            "confirmationId": new_id("cf"),
            "referenceIds": list(reference_ids),
            "referenceHashes": hashes,
            "scope": {"allowedChanges": list(allowed_changes),
                      "preserved": list(preserved)},
            "note": note,
            "confirmedBy": "user",
            "confirmedAt": now(),
            "status": "active",
            "staleReason": None,
            "supersededBy": None,
        }
        for existing in project["confirmations"]:
            if existing.get("status") == "active":
                existing["status"] = "superseded"
                existing["supersededBy"] = confirmation["confirmationId"]
        project["confirmations"].append(confirmation)
        state_module.sync_gate_status(project)
        return confirmation

    return store.mutate(add)


def gate(project, reference_ids, allowed_changes=None, preserved=None):
    """Refuse image/motion jobs without an active, matching user confirmation."""
    if project.get("status") == "archived":
        raise CreativeError("项目已归档；不能创建制作任务")
    requested = list(reference_ids or [])
    if not requested:
        raise CreativeError("新对象制作前至少需要一个参考")
    if len(set(requested)) != len(requested):
        raise CreativeError("参考清单重复")
    references = {reference["referenceId"]: reference
                  for reference in project.get("references") or []}
    for reference_id in requested:
        reference = references.get(reference_id)
        if reference is None:
            raise CreativeError(f"找不到参考: {reference_id}", status=404)
        if reference.get("missing"):
            raise CreativeError("参考文件缺失；请先恢复或替换参考")
    wanted = set(requested)
    confirmations = project.get("confirmations") or []
    active = [item for item in confirmations if item.get("status") == "active"]
    covering = [item for item in active
                if set(item.get("referenceIds") or []) >= wanted]
    if not covering:
        stale = any(set(item.get("referenceIds") or []) >= wanted
                    for item in confirmations if item.get("status") == "stale")
        if stale:
            raise CreativeError("参考已变化；请重新确认")
        if active:
            raise CreativeError("确认未覆盖这些参考；请重新确认")
        raise CreativeError("参考尚未确认；先确认参考和修改范围")
    confirmation = covering[-1]
    hashes = confirmation.get("referenceHashes") or {}
    for reference_id in requested:
        if hashes.get(reference_id) != references[reference_id].get("sha256"):
            raise CreativeError("参考已变化；请重新确认")
    scope = confirmation.get("scope") or {}
    if not set(allowed_changes or []) <= set(scope.get("allowedChanges") or []):
        raise CreativeError("修改范围超出已确认范围；请重新确认")
    if not set(preserved or []) >= set(scope.get("preserved") or []):
        raise CreativeError("保留项少于已确认范围；请重新确认")
    return confirmation


def adopt_version(store, project_id, version_id):
    _active(store, project_id)

    def adopt(state):
        project = state_module.find_project(state, project_id)
        if project["status"] == "archived":
            raise CreativeError("项目已归档；不能采用版本")
        version = state_module.find_version(project, version_id)
        project["selectedVersionId"] = version["versionId"]
        if project["status"] != "adopted":
            state_module.transition_project(project, "adopted")
        else:
            state_module.touch(project)
        return project

    return store.mutate(adopt)


def pointer_options():
    """Allowed pointer roles and expressions, for the API and front end."""
    return {
        "roles": list(POINTER_ROLES),
        "layerRoles": list(POINTER_LAYER_ROLES),
        "expressions": list(POINTER_EXPRESSIONS),
    }
