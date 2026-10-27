"""Independent schema-1 creative state: atomic writes, validation, and recovery."""

from __future__ import annotations

import copy
import inspect
import json
import threading
from pathlib import Path

from . import (
    CONFIRMATION_STATUSES,
    CREATIVE,
    ID_PATTERNS,
    JOB_KINDS,
    JOB_OPERATIONS,
    JOB_STATUSES,
    MAX_PROJECTS,
    OBJECT_KINDS,
    PREVIEW_STATUSES,
    PROJECT_STATUSES,
    PROJECT_TRANSITIONS,
    REFERENCE_KINDS,
    SCHEMA_VERSION,
    VERSION_FORMATS,
    VERSION_SOURCES,
    CreativeError,
    CreativeStateError,
    digest_file,
    is_hash,
    now,
    overlay_allowed,
    relative_path,
    write_json_atomic,
)

PROJECT_FIELDS = (
    "projectId", "number", "name", "objectKind", "purpose", "status", "createdAt",
    "updatedAt", "revision", "selectedVersionId", "references", "confirmations",
    "jobs", "versions", "previews", "researchReports", "motionNotes",
    "manualExports", "issues",
)
PROJECT_LISTS = ("references", "confirmations", "jobs", "versions", "previews",
                 "researchReports", "motionNotes", "manualExports", "issues")
ID_KINDS = ("project", "reference", "confirmation", "job", "version", "preview", "export")


def _require(condition, message):
    if not condition:
        raise CreativeStateError(message)


def _text(value, label, allow_empty=False):
    _require(isinstance(value, str), f"{label}必须为字符串")
    if not allow_empty:
        _require(bool(value.strip()), f"{label}不能为空")
    return value


def _items(value, label):
    _require(isinstance(value, list), f"{label}必须为列表")
    return value


def _strings(value, label):
    _items(value, label)
    for item in value:
        _require(isinstance(item, str) and bool(item.strip()),
                 f"{label}必须是非空字符串列表")
    return value


def _object(value, label):
    _require(isinstance(value, dict), f"{label}必须为对象")
    return value


def _integer(value, label, minimum=None):
    _require(isinstance(value, int) and not isinstance(value, bool), f"{label}必须为整数")
    if minimum is not None:
        _require(value >= minimum, f"{label}不能小于 {minimum}")
    return value


def _hash(value, label, allow_none=False):
    if value is None and allow_none:
        return None
    _require(is_hash(value), f"{label} SHA-256 不合法")
    return value


def _size(value, label, allow_none=False):
    if value is None and allow_none:
        return None
    _require(isinstance(value, list) and len(value) == 2, f"{label}尺寸不合法")
    for part in value:
        _require(isinstance(part, int) and not isinstance(part, bool) and part > 0,
                 f"{label}尺寸不合法")
    return value


def _creative_path(value, label, allow_none=False):
    if value is None and allow_none:
        return None
    try:
        return relative_path(value, label, prefix="projects/")
    except CreativeError as error:
        raise CreativeStateError(str(error)) from error


def _id(kind, value, label):
    pattern = ID_PATTERNS[kind]
    _require(isinstance(value, str) and bool(pattern.match(value)),
             f"{label} id 不合法: {value}")
    return value


def new_state():
    stamp = now()
    return {
        "schemaVersion": SCHEMA_VERSION,
        "revision": 0,
        "createdAt": stamp,
        "updatedAt": stamp,
        "nextProject": 1,
        "projects": [],
    }


def validate_reference(reference, project_id):
    _object(reference, f"{project_id} 的参考")
    _id("reference", reference.get("referenceId"), f"{project_id} 的参考")
    label = f"{project_id} 的参考 {reference['referenceId']}"
    _integer(reference.get("revision"), f"{label} revision", minimum=1)
    _require(reference.get("kind") in REFERENCE_KINDS, f"{label} 类型不合法")
    _text(reference.get("title"), f"{label} 标题", allow_empty=True)
    source = _object(reference.get("source"), f"{label} 来源")
    uri = source.get("uri")
    _require(uri is None or isinstance(uri, str), f"{label} 来源 uri 不合法")
    path = _creative_path(reference.get("path"), f"{label} 路径", allow_none=True)
    sha256 = _hash(reference.get("sha256"), f"{label} 哈希", allow_none=True)
    size = _size(reference.get("size"), f"{label} 尺寸", allow_none=True)
    _require(reference.get("format") is None or isinstance(reference.get("format"), str),
             f"{label} 格式不合法")
    if reference["kind"] == "image":
        _require(path is not None and sha256 is not None and size is not None,
                 f"{label} 必须有本地图片文件")
    elif reference["kind"] == "film-frame" and path is not None:
        _require(sha256 is not None and size is not None,
                 f"{label} 有本地文件时必须同时有哈希和尺寸")
    _text(reference.get("findings"), f"{label} 形态要点", allow_empty=True)
    _strings(reference.get("uncertainties"), f"{label} 不确定处")
    _text(reference.get("createdAt"), f"{label} 创建时间")
    _text(reference.get("updatedAt"), f"{label} 更新时间")
    _require(isinstance(reference.get("missing"), bool), f"{label} missing 必须为布尔值")
    return reference


def validate_confirmation(confirmation, project_id, reference_ids):
    _object(confirmation, f"{project_id} 的确认")
    _id("confirmation", confirmation.get("confirmationId"), f"{project_id} 的确认")
    label = f"{project_id} 的确认 {confirmation['confirmationId']}"
    chosen = _strings(confirmation.get("referenceIds"), f"{label} 参考")
    _require(len(set(chosen)) == len(chosen), f"{label} 参考重复")
    _require(set(chosen) <= reference_ids, f"{label} 引用了不存在的参考")
    hashes = _object(confirmation.get("referenceHashes"), f"{label} 参考哈希")
    _require(set(hashes) == set(chosen), f"{label} 参考哈希键不一致")
    for key, value in hashes.items():
        _hash(value, f"{label} 参考哈希 {key}", allow_none=True)
    scope = _object(confirmation.get("scope"), f"{label} 修改范围")
    _strings(scope.get("allowedChanges"), f"{label} 允许改动")
    _strings(scope.get("preserved"), f"{label} 保留项")
    _text(confirmation.get("note"), f"{label} 说明", allow_empty=True)
    _require(confirmation.get("confirmedBy") == "user", f"{label} 只能由用户确认")
    _text(confirmation.get("confirmedAt"), f"{label} 确认时间")
    _require(confirmation.get("status") in CONFIRMATION_STATUSES, f"{label} 状态不合法")
    _require(confirmation.get("staleReason") is None
             or isinstance(confirmation.get("staleReason"), str),
             f"{label} 失效原因不合法")
    superseded = confirmation.get("supersededBy")
    _require(superseded is None
             or bool(ID_PATTERNS["confirmation"].match(str(superseded))),
             f"{label} 取代记录不合法")
    return confirmation


def validate_version(version, project_id, version_ids, job_ids):
    _object(version, f"{project_id} 的版本")
    _id("version", version.get("versionId"), f"{project_id} 的版本")
    label = f"{project_id} 的版本 {version['versionId']}"
    parent = version.get("parentVersionId")
    _require(parent is None or parent in version_ids, f"{label} 父版本不存在")
    _require(version.get("source") in VERSION_SOURCES, f"{label} 来源不合法")
    _creative_path(version.get("path"), f"{label} 路径")
    _hash(version.get("sha256"), f"{label} 哈希")
    _size(version.get("size"), f"{label} 尺寸")
    _require(version.get("format") in VERSION_FORMATS, f"{label} 格式不合法")
    _require(isinstance(version.get("hasAlpha"), bool), f"{label} hasAlpha 必须为布尔值")
    job_id = version.get("jobId")
    _require(job_id is None or job_id in job_ids, f"{label} 任务不存在")
    pointer = version.get("pointerSource")
    _require(pointer is None or isinstance(pointer, dict), f"{label} 指针数据不合法")
    if version["format"] == "JSON":
        _require(pointer is not None, f"{label} 指针版本缺少 pointerSource")
    else:
        _require(pointer is None, f"{label} 图片版本不应内联 pointerSource")
    _creative_path(version.get("previewPath"), f"{label} 预览路径", allow_none=True)
    _require(version.get("manual") is None or isinstance(version.get("manual"), dict),
             f"{label} 手改信息不合法")
    _require(isinstance(version.get("paintedFill"), bool), f"{label} paintedFill 必须为布尔值")
    _text(version.get("createdAt"), f"{label} 创建时间")
    _require(version.get("note") is None or isinstance(version.get("note"), str),
             f"{label} 备注不合法")
    if version["source"] in ("gpt-image", "gpt-image-inpaint"):
        _require(job_id is not None, f"{label} 必须来自任务回传")
    if version["source"] in ("manual-piskel", "manual-krita"):
        _require(version.get("manual") is not None, f"{label} 缺少手改信息")
    return version


def validate_job(job, project_id, version_ids, reference_ids, confirmation_ids):
    _object(job, f"{project_id} 的任务")
    _id("job", job.get("jobId"), f"{project_id} 的任务")
    label = f"{project_id} 的任务 {job['jobId']}"
    kind = job.get("kind")
    _require(kind in JOB_KINDS, f"{label} 类型不合法")
    _require(job.get("operation") in JOB_OPERATIONS[kind], f"{label} 操作不合法")
    _require(job.get("status") in JOB_STATUSES, f"{label} 状态不合法")
    _integer(job.get("revision"), f"{label} revision", minimum=1)
    input_version = job.get("inputVersionId")
    _require(input_version is None or input_version in version_ids,
             f"{label} 输入版本不存在")
    _hash(job.get("inputSha256"), f"{label} 输入哈希", allow_none=True)
    chosen = _strings(job.get("referenceIds"), f"{label} 参考")
    _require(len(set(chosen)) == len(chosen), f"{label} 参考重复")
    _require(set(chosen) <= reference_ids, f"{label} 引用了不存在的参考")
    hashes = _object(job.get("referenceHashes"), f"{label} 参考哈希")
    _require(set(hashes) == set(chosen), f"{label} 参考哈希键不一致")
    for key, value in hashes.items():
        _hash(value, f"{label} 参考哈希 {key}", allow_none=True)
    confirmation = job.get("confirmationId")
    _require(confirmation is None or confirmation in confirmation_ids,
             f"{label} 确认记录不存在")
    _strings(job.get("allowedChanges"), f"{label} 允许改动")
    _strings(job.get("preserved"), f"{label} 保留项")
    _size(job.get("outputSize"), f"{label} 输出尺寸", allow_none=True)
    _require(isinstance(job.get("requireAlpha"), bool),
             f"{label} requireAlpha 必须为布尔值")
    _require(isinstance(job.get("paintedFill"), bool),
             f"{label} paintedFill 必须为布尔值")
    _require(job["paintedFill"] == (job["operation"] == "inpaint"),
             f"{label} 补画标记与操作不一致")
    created_selected = job.get("selectedVersionIdAtCreation")
    _require(created_selected is None or created_selected in version_ids,
             f"{label} 创建时选中版本不存在")
    _creative_path(job.get("jobPath"), f"{label} 目录")
    _text(job.get("createdAt"), f"{label} 创建时间")
    _require(job.get("completedAt") is None or isinstance(job.get("completedAt"), str),
             f"{label} 完成时间不合法")
    _require(job.get("error") is None or isinstance(job.get("error"), str),
             f"{label} 错误信息不合法")
    _require(job.get("receipt") is None or isinstance(job.get("receipt"), dict),
             f"{label} 回执不合法")
    _hash(job.get("resultSha256"), f"{label} 结果哈希", allow_none=True)
    _creative_path(job.get("resultPath"), f"{label} 结果路径", allow_none=True)
    _hash(job.get("conflictSha256"), f"{label} 冲突哈希", allow_none=True)
    _require(job.get("rejectedFingerprint") is None
             or isinstance(job.get("rejectedFingerprint"), str),
             f"{label} 拒绝指纹不合法")
    _items(job.get("attempts"), f"{label} 尝试记录")
    _require(job.get("lateAt") is None or isinstance(job.get("lateAt"), str),
             f"{label} 迟到时间不合法")
    _require(job.get("note") is None or isinstance(job.get("note"), str),
             f"{label} 备注不合法")
    entry = job.get("input")
    if entry is not None:
        _object(entry, f"{label} 输入")
        _creative_path(entry.get("path"), f"{label} 输入路径")
        _hash(entry.get("sha256"), f"{label} 输入哈希")
        _size(entry.get("size"), f"{label} 输入尺寸")
        _require(entry.get("format") == "PNG", f"{label} 输入必须是 PNG")
        _require(entry.get("versionId") in version_ids, f"{label} 输入版本不存在")
        _hash(entry.get("versionSha256"), f"{label} 输入版本哈希")
    return job


def validate_preview(preview, project_id, version_ids):
    _object(preview, f"{project_id} 的草稿")
    _id("preview", preview.get("previewId"), f"{project_id} 的草稿")
    label = f"{project_id} 的草稿 {preview['previewId']}"
    _require(preview.get("versionId") in version_ids, f"{label} 版本不存在")
    _require(preview.get("status") in PREVIEW_STATUSES, f"{label} 状态不合法")
    overlays = _items(preview.get("overlay"), f"{label} 覆盖清单")
    _require(bool(overlays), f"{label} 覆盖清单不能为空")
    for item in overlays:
        _require(overlay_allowed(item), f"{label} 覆盖路径不在允许范围: {item}")
    for key in ("baseline", "overlayHashes"):
        mapping = _object(preview.get(key), f"{label} {key}")
        for name, value in mapping.items():
            _require(overlay_allowed(name), f"{label} {key} 路径不在允许范围: {name}")
            _hash(value, f"{label} {key} 哈希 {name}", allow_none=True)
    _text(preview.get("createdAt"), f"{label} 创建时间")
    for key in ("checkedAt", "appliedAt", "rolledBackAt"):
        _require(preview.get(key) is None or isinstance(preview.get(key), str),
                 f"{label} {key} 不合法")
    _require(preview.get("note") is None or isinstance(preview.get("note"), str),
             f"{label} 备注不合法")
    _items(preview.get("mismatches"), f"{label} 差异清单")
    return preview


def validate_report(report, project_id, job_ids):
    _object(report, f"{project_id} 的报告")
    _require(report.get("jobId") in job_ids, f"{project_id} 的报告任务不存在")
    _text(report.get("summary"), f"{project_id} 的报告摘要", allow_empty=True)
    _creative_path(report.get("path"), f"{project_id} 的报告路径")
    _hash(report.get("sha256"), f"{project_id} 的报告哈希")
    _text(report.get("createdAt"), f"{project_id} 的报告时间")
    return report


def validate_export(export, project_id, version_ids):
    _object(export, f"{project_id} 的导出")
    _id("export", export.get("exportId"), f"{project_id} 的导出")
    label = f"{project_id} 的导出 {export['exportId']}"
    _require(export.get("versionId") in version_ids, f"{label} 版本不存在")
    _require(export.get("role") in ("shima", "adachi", "full"), f"{label} 角色不合法")
    _require(export.get("expression") in ("open", "shut", "happy", "squint"),
             f"{label} 表情不合法")
    _text(export.get("editor"), f"{label} 编辑器")
    _creative_path(export.get("path"), f"{label} 目录")
    _items(export.get("files"), f"{label} 文件清单")
    _require(export.get("piskelVerified") is None
             or isinstance(export.get("piskelVerified"), bool),
             f"{label} Piskel 校验标记不合法")
    _text(export.get("createdAt"), f"{label} 创建时间")
    return export


def validate_issue(issue, project_id):
    _object(issue, f"{project_id} 的问题记录")
    _text(issue.get("kind"), f"{project_id} 的问题类型")
    _text(issue.get("message"), f"{project_id} 的问题说明")
    _require(issue.get("path") is None or isinstance(issue.get("path"), str),
             f"{project_id} 的问题路径不合法")
    _text(issue.get("at"), f"{project_id} 的问题时间")
    return issue


def _collect(records, kind, key, seen, project_id):
    ids = set()
    for record in records:
        _object(record, f"{project_id} 的{kind}")
        value = record.get(key)
        _id(kind, value, f"{project_id} 的{kind}")
        _require(value not in seen[kind], f"{project_id} 的{kind} id 重复: {value}")
        seen[kind].add(value)
        ids.add(value)
    return ids


def validate_project(project, seen, numbers):
    _object(project, "项目")
    for key in PROJECT_FIELDS:
        _require(key in project, f"项目缺少字段: {key}")
    _id("project", project.get("projectId"), "项目")
    project_id = project["projectId"]
    number = _integer(project.get("number"), f"{project_id} 编号", minimum=1)
    _require(number not in numbers, f"{project_id} 编号重复")
    numbers.add(number)
    _require(project_id not in seen["project"], f"项目 id 重复: {project_id}")
    seen["project"].add(project_id)
    _text(project.get("name"), f"{project_id} 名称")
    _require(project.get("objectKind") in OBJECT_KINDS, f"{project_id} 对象类型不合法")
    _text(project.get("purpose"), f"{project_id} 用途", allow_empty=True)
    _require(project.get("status") in PROJECT_STATUSES, f"{project_id} 状态不合法")
    _text(project.get("createdAt"), f"{project_id} 创建时间")
    _text(project.get("updatedAt"), f"{project_id} 更新时间")
    _integer(project.get("revision"), f"{project_id} revision", minimum=0)
    for kind in PROJECT_LISTS:
        _items(project.get(kind), f"{project_id} 的 {kind}")

    reference_ids = _collect(project["references"], "reference", "referenceId", seen, project_id)
    version_ids = _collect(project["versions"], "version", "versionId", seen, project_id)
    job_ids = _collect(project["jobs"], "job", "jobId", seen, project_id)
    confirmation_ids = _collect(project["confirmations"], "confirmation",
                               "confirmationId", seen, project_id)
    _collect(project["previews"], "preview", "previewId", seen, project_id)
    _collect(project["manualExports"], "export", "exportId", seen, project_id)

    for reference in project["references"]:
        validate_reference(reference, project_id)
    for version in project["versions"]:
        validate_version(version, project_id, version_ids, job_ids)
    for job in project["jobs"]:
        validate_job(job, project_id, version_ids, reference_ids, confirmation_ids)
    for confirmation in project["confirmations"]:
        validate_confirmation(confirmation, project_id, reference_ids)
    for preview in project["previews"]:
        validate_preview(preview, project_id, version_ids)
    for report in project["researchReports"]:
        validate_report(report, project_id, job_ids)
    for note in project["motionNotes"]:
        validate_report(note, project_id, job_ids)
    for export in project["manualExports"]:
        validate_export(export, project_id, version_ids)
    for issue in project["issues"]:
        validate_issue(issue, project_id)

    selected = project.get("selectedVersionId")
    _require(selected is None or selected in version_ids, f"{project_id} 选中版本不存在")
    return project


def validate_creative_state(state):
    _object(state, "制作区状态")
    _require(state.get("schemaVersion") == SCHEMA_VERSION, "制作区状态 schemaVersion 不支持")
    _integer(state.get("revision"), "制作区 revision", minimum=0)
    _text(state.get("createdAt"), "制作区创建时间")
    _text(state.get("updatedAt"), "制作区更新时间")
    next_project = _integer(state.get("nextProject"), "制作区 nextProject", minimum=1)
    projects = _items(state.get("projects"), "制作区 projects")
    _require(len(projects) <= MAX_PROJECTS, "制作区项目数超过上限")
    seen = {kind: set() for kind in ID_KINDS}
    numbers = set()
    for project in projects:
        validate_project(project, seen, numbers)
    _require(not numbers or max(numbers) < next_project,
             "制作区 nextProject 必须大于已有编号")
    return state


def find_project(state, project_id):
    for project in state.get("projects") or []:
        if project.get("projectId") == project_id:
            return project
    raise CreativeError(f"找不到项目: {project_id}", status=404)


def _find(records, key, value, label):
    for record in records or []:
        if record.get(key) == value:
            return record
    raise CreativeError(f"找不到{label}: {value}", status=404)


def get_reference(project, reference_id):
    return next((reference for reference in project.get("references") or []
                 if reference.get("referenceId") == reference_id), None)


def get_confirmation(project, confirmation_id):
    return next((item for item in project.get("confirmations") or []
                 if item.get("confirmationId") == confirmation_id), None)


def get_job(project, job_id):
    return next((job for job in project.get("jobs") or []
                 if job.get("jobId") == job_id), None)


def get_version(project, version_id):
    return next((version for version in project.get("versions") or []
                 if version.get("versionId") == version_id), None)


def get_preview(project, preview_id):
    return next((preview for preview in project.get("previews") or []
                 if preview.get("previewId") == preview_id), None)


def get_export(project, export_id):
    return next((export for export in project.get("manualExports") or []
                 if export.get("exportId") == export_id), None)


def find_reference(project, reference_id):
    return _find(project.get("references"), "referenceId", reference_id, "参考")


def find_confirmation(project, confirmation_id):
    return _find(project.get("confirmations"), "confirmationId", confirmation_id, "确认")


def find_job(project, job_id):
    return _find(project.get("jobs"), "jobId", job_id, "任务")


def find_version(project, version_id):
    return _find(project.get("versions"), "versionId", version_id, "版本")


def find_preview(project, preview_id):
    return _find(project.get("previews"), "previewId", preview_id, "草稿")


def find_export(project, export_id):
    return _find(project.get("manualExports"), "exportId", export_id, "导出")


def touch(project):
    project["updatedAt"] = now()
    project["revision"] = int(project.get("revision") or 0) + 1
    return project


def transition_project(project, status):
    current = project.get("status")
    if current == status:
        return project
    if status not in PROJECT_TRANSITIONS.get(current, set()):
        raise CreativeError(f"项目不能从 {current} 转到 {status}")
    project["status"] = status
    touch(project)
    return project


def add_issue(project, kind, message, path=None):
    issues = project.setdefault("issues", [])
    for issue in issues:
        if issue.get("kind") == kind and issue.get("path") == path:
            return None
    issue = {"kind": kind, "message": message, "at": now()}
    if path:
        issue["path"] = path
    issues.append(issue)
    return issue


def mark_stale(project, reference_ids, reason):
    targets = set(reference_ids)
    changed = []
    for confirmation in project.get("confirmations") or []:
        if confirmation.get("status") != "active":
            continue
        if targets & set(confirmation.get("referenceIds") or []):
            confirmation["status"] = "stale"
            confirmation["staleReason"] = reason
            changed.append(confirmation["confirmationId"])
    return changed


def revalidate_confirmations(project):
    references = {reference["referenceId"]: reference
                  for reference in project.get("references") or []}
    changed = []
    for confirmation in project.get("confirmations") or []:
        if confirmation.get("status") != "active":
            continue
        reason = None
        for reference_id in confirmation.get("referenceIds") or []:
            reference = references.get(reference_id)
            if reference is None:
                reason = "参考不存在"
                break
            if reference.get("missing"):
                reason = "参考文件缺失"
                break
            if (confirmation.get("referenceHashes") or {}).get(reference_id) != reference.get("sha256"):
                reason = "参考已变化"
                break
        if reason:
            confirmation["status"] = "stale"
            confirmation["staleReason"] = reason
            changed.append(confirmation["confirmationId"])
    return changed


def gate_state(project):
    """Read-only projection of the reference gate for the workbench UI."""
    references = project.get("references") or []
    active = [item for item in project.get("confirmations") or []
              if item.get("status") == "active"]
    latest = active[-1] if active else None
    covered = list(latest.get("referenceIds") or []) if latest else []
    covered_set = set(covered)
    confirmed = bool(references) and latest is not None and all(
        reference["referenceId"] in covered_set
        and (latest.get("referenceHashes") or {}).get(reference["referenceId"])
        == reference.get("sha256")
        and not reference.get("missing")
        for reference in references)
    return {
        "activeConfirmationId": latest.get("confirmationId") if latest else None,
        "confirmed": confirmed,
        "stale": bool(project.get("confirmations")) and not confirmed,
        "coveredReferenceIds": covered,
    }


def sync_gate_status(project, confirmed_status="reference-confirmed"):
    """Keep the project's status in step with the reference gate.

    A confirmation that covers only some of the references leaves the gate open
    (``confirmed: false``); the project must stay in research rather than claim
    ``reference-confirmed``.  A confirmation that covers every reference moves it
    to ``confirmed_status``.  The caller has already rejected archived projects.
    """
    target = confirmed_status if gate_state(project)["confirmed"] else "research"
    if project.get("status") == target:
        touch(project)
    else:
        transition_project(project, target)
    return project


def project_summary(project):
    return {
        "projectId": project["projectId"],
        "number": project["number"],
        "name": project["name"],
        "objectKind": project["objectKind"],
        "purpose": project["purpose"],
        "status": project["status"],
        "revision": project["revision"],
        "selectedVersionId": project.get("selectedVersionId"),
        "createdAt": project["createdAt"],
        "updatedAt": project["updatedAt"],
        "counts": {
            "references": len(project.get("references") or []),
            "confirmations": len(project.get("confirmations") or []),
            "jobsWaiting": sum(1 for job in project.get("jobs") or []
                               if job.get("status") == "waiting"),
            "versions": len(project.get("versions") or []),
            "previews": len(project.get("previews") or []),
        },
        "gate": gate_state(project),
        "issues": copy.deepcopy(project.get("issues") or []),
    }


def project_detail(project):
    detail = copy.deepcopy(project)
    summary = project_summary(project)
    detail["counts"] = summary["counts"]
    detail["gate"] = summary["gate"]
    return detail


def _digest(path):
    try:
        return digest_file(path)
    except OSError:
        return None


def recover_state(store):
    """Re-check reference and version files; never delete or rewrite a version."""
    state = store.read()
    findings = []
    for project in state.get("projects") or []:
        project_id = project["projectId"]
        for reference in project.get("references") or []:
            relative = reference.get("path")
            if not relative:
                continue
            path = store.root / relative
            present = path.is_file() and _digest(path) == reference.get("sha256")
            if not present:
                findings.append({"projectId": project_id, "kind": "reference-missing",
                                 "message": "参考文件缺失", "path": relative,
                                 "referenceId": reference["referenceId"]})
            elif reference.get("missing"):
                findings.append({"projectId": project_id, "kind": "reference-restored",
                                 "message": "参考文件已恢复", "path": relative,
                                 "referenceId": reference["referenceId"]})
        for version in project.get("versions") or []:
            path = store.root / version["path"]
            if not path.is_file():
                findings.append({"projectId": project_id, "kind": "version-missing",
                                 "message": "版本文件缺失", "path": version["path"]})
            elif _digest(path) != version["sha256"]:
                findings.append({"projectId": project_id, "kind": "version-changed",
                                 "message": "版本文件已变化", "path": version["path"]})
        for export in project.get("manualExports") or []:
            if not (store.root / export["path"]).is_dir():
                findings.append({"projectId": project_id, "kind": "export-missing",
                                 "message": "手改导出目录缺失", "path": export["path"]})
    revalidated = [project["projectId"] for project in state.get("projects") or []
                   if revalidate_confirmations(copy.deepcopy(project))]
    if not findings and not revalidated:
        return []

    def apply(state):
        changes = []
        for project in state.get("projects") or []:
            project_id = project["projectId"]
            local = [entry for entry in findings if entry["projectId"] == project_id]
            if not local and project_id not in revalidated:
                continue
            for entry in local:
                if entry["kind"] == "reference-missing":
                    reference = get_reference(project, entry["referenceId"])
                    if reference is not None:
                        reference["missing"] = True
                    changes.extend(mark_stale(project, [entry["referenceId"]],
                                             "参考文件缺失"))
                    add_issue(project, "reference-missing", entry["message"], entry["path"])
                elif entry["kind"] == "reference-restored":
                    reference = get_reference(project, entry["referenceId"])
                    if reference is not None:
                        reference["missing"] = False
                elif entry["kind"] == "version-missing":
                    add_issue(project, "version-missing", entry["message"], entry["path"])
                elif entry["kind"] == "version-changed":
                    add_issue(project, "version-changed", entry["message"], entry["path"])
                elif entry["kind"] == "export-missing":
                    add_issue(project, "export-missing", entry["message"], entry["path"])
                changes.append(f"{project_id}:{entry['kind']}:{entry['path']}")
            changes.extend(revalidate_confirmations(project))
            touch(project)
        return changes

    return store.mutate(apply)


def recover_all(store, site_root=None):
    """Recover state, handoff jobs, and (when present) draft previews."""
    changes = list(recover_state(store))
    try:
        from . import jobs
    except ImportError:  # pragma: no cover - jobs ships with this package
        jobs = None
    if jobs is not None and hasattr(jobs, "recover_jobs"):
        changes.extend(jobs.recover_jobs(store))
    try:
        from . import preview
    except ImportError:  # pragma: no cover - preview is optional at first
        preview = None
    if preview is not None:
        recover = (getattr(preview, "recover_previews", None)
                   or getattr(preview, "recover", None))
        if recover is not None:
            parameters = inspect.signature(recover).parameters
            if len(parameters) > 1:
                changes.extend(recover(store, site_root))
            else:
                changes.extend(recover(store))
    return changes


class CreativeStore:
    """In-memory schema-1 state with atomic snapshots and a process-local lock."""

    def __init__(self, root=None, create=True):
        self.root = Path(root or CREATIVE).resolve()
        self.path = self.root / "state.json"
        self.lock = threading.RLock()
        if self.path.exists():
            self.state = self.load()
        elif create:
            self.root.mkdir(parents=True, exist_ok=True)
            self.state = new_state()
            self.save(self.state)
        else:
            raise CreativeStateError(f"缺少制作区状态: {self.path}")

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CreativeStateError(f"制作区状态无法读取: {error}") from error
        return validate_creative_state(data)

    def save(self, state):
        try:
            validate_creative_state(state)
        except CreativeStateError as error:
            raise CreativeStateError(str(error), status=500) from error
        state["updatedAt"] = now()
        write_json_atomic(self.path, state)

    def read(self):
        with self.lock:
            return copy.deepcopy(self.state)

    def mutate(self, operation):
        with self.lock:
            state = copy.deepcopy(self.state)
            result = operation(state)
            state["revision"] = int(state.get("revision", 0)) + 1
            self.save(state)
            self.state = state
            return copy.deepcopy(result)

    def replace(self, state):
        with self.lock:
            state = copy.deepcopy(state)
            state["revision"] = int(state.get("revision", 0)) + 1
            self.save(state)
            self.state = state

    def path_for(self, relative):
        text = relative_path(relative, "制作区文件")
        target = (self.root / text).resolve()
        if not target.is_relative_to(self.root):
            raise CreativeError(f"路径越界: {text}")
        return target
