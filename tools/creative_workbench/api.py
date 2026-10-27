"""The creative workbench's HTTP namespace: projects, references, jobs, manual edits, previews.

``Workbench.get``/``post`` hand every ``/api/creative/`` request here; the module
answers with the same shapes the gallery routes use (a ``(status, content_type, bytes)``
tuple for GET and a ``(status, payload)`` tuple for POST) and raises
``CreativeError`` with a status for anything the caller got wrong.  The creative state
and data live under ``.local/output/creative-assets``; the gallery state is never read
or written here, and no request leaves this machine.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from . import CREATIVE, ROOT, CreativeError
from . import jobs, manual, preview, research
from . import state as state_module

JSON_TYPE = "application/json; charset=utf-8"
MARKDOWN_TYPE = "text/markdown; charset=utf-8"


def _json(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _query(query, key, default=None):
    if not isinstance(query, dict):
        return default
    values = query.get(key)
    if not values:
        return default
    return values[0]


def _payload(body):
    if not body:
        raise CreativeError("请求缺少 JSON")
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CreativeError(f"请求 JSON 无法解析: {error}") from error
    if not isinstance(value, dict):
        raise CreativeError("请求必须是 JSON 对象")
    return value


def _text(payload, key, label, allow_empty=False):
    value = payload.get(key)
    if not isinstance(value, str):
        raise CreativeError(f"{label}必须为字符串")
    if not allow_empty and not value.strip():
        raise CreativeError(f"{label}不能为空")
    return value


def _optional(payload, key):
    value = payload.get(key)
    return value if isinstance(value, str) and value.strip() else None


class CreativeApi:
    """Lazy creative state, recovery once, and the creative HTTP routes."""

    def __init__(self, creative_root=None, site_root=None, root=None):
        self.creative_root = Path(creative_root or CREATIVE).resolve()
        self.site_root = Path(site_root or ROOT / "site").resolve()
        self.root = Path(root or ROOT).resolve()
        self._store = None
        self._recovered = False
        self._lock = threading.RLock()

    @property
    def store(self):
        with self._lock:
            if self._store is None:
                self._store = state_module.CreativeStore(self.creative_root, create=True)
            return self._store

    def ensure_recovered(self):
        """Revalidate references, jobs, and interrupted applies, once per process."""
        with self._lock:
            if self._recovered:
                return []
            changes = state_module.recover_all(self.store, self.site_root)
            self._recovered = True
            return changes

    # --- payloads ---------------------------------------------------------

    def state_payload(self):
        state = self.store.read()
        projects = []
        for project in state.get("projects") or []:
            summary = state_module.project_summary(project)
            summary["detailUrl"] = f"/api/creative/project/{project['projectId']}"
            projects.append(summary)
        return {"schemaVersion": state["schemaVersion"], "revision": state["revision"],
                "projects": projects}

    def project_payload(self, project_id):
        project = state_module.find_project(self.store.read(), project_id)
        detail = state_module.project_detail(project)
        detail["referenceUrls"] = {
            reference["referenceId"]: f"/creative-media/{reference['path']}"
            for reference in project.get("references") or [] if reference.get("path")}
        detail["versionUrls"] = {
            version["versionId"]: f"/creative-media/{version['path']}"
            for version in project.get("versions") or []}
        detail["versionPreviewUrls"] = {
            version["versionId"]: f"/creative-media/{version['previewPath']}"
            for version in project.get("versions") or [] if version.get("previewPath")}
        detail["jobInstructionUrls"] = {
            job["jobId"]: f"/api/creative/job/instruction?jobId={job['jobId']}"
            for job in project.get("jobs") or []}
        detail["previewUrls"] = {
            item["previewId"]: f"/creative-preview/{item['previewId']}/"
            for item in project.get("previews") or []}
        detail["exportUrls"] = {
            export["exportId"]: f"/creative-media/{export['path']}/source.png"
            for export in project.get("manualExports") or []}
        return detail

    # --- GET --------------------------------------------------------------

    def get(self, path, query):
        self.ensure_recovered()
        if path == "/api/creative/state":
            return 200, JSON_TYPE, _json(self.state_payload())
        if path.startswith("/api/creative/project/"):
            project_id = path[len("/api/creative/project/"):].strip("/")
            if not project_id or "/" in project_id:
                raise CreativeError("找不到项目", status=404)
            return 200, JSON_TYPE, _json({"project": self.project_payload(project_id)})
        if path == "/api/creative/job/instruction":
            job_id = _query(query, "jobId")
            if not job_id:
                raise CreativeError("缺少 jobId")
            text = jobs.job_instruction(self.store, job_id)
            return 200, MARKDOWN_TYPE, text.encode("utf-8")
        raise CreativeError("未知接口", status=404)

    # --- POST -------------------------------------------------------------

    def post(self, path, query, body):
        self.ensure_recovered()
        if path == "/api/creative/project":
            payload = _payload(body)
            purpose = payload.get("purpose", "")
            if purpose is None:
                purpose = ""
            project = research.create_project(
                self.store, _text(payload, "name", "项目名称"),
                _text(payload, "objectKind", "对象类型"), purpose)
            return 200, {"project": self.project_payload(project["projectId"])}
        if path == "/api/creative/project/archive":
            payload = _payload(body)
            project = research.archive_project(
                self.store, _text(payload, "projectId", "项目"))
            return 200, {"project": self.project_payload(project["projectId"])}
        if path == "/api/creative/reference/file":
            project_id = _query(query, "projectId")
            if not project_id:
                raise CreativeError("缺少 projectId")
            reference = research.add_reference_file(
                self.store, project_id, body,
                filename=_query(query, "name"),
                title=_query(query, "title"),
                kind=_query(query, "kind", "image"),
                timecode=_query(query, "timecode"),
                note=_query(query, "note"),
                findings=_query(query, "findings", ""),
                uncertainties=_query(query, "uncertainties", ""))
            return 200, {"reference": reference}
        if path == "/api/creative/reference/link":
            payload = _payload(body)
            reference = research.add_reference_link(
                self.store, _text(payload, "projectId", "项目"),
                _text(payload, "title", "参考标题"),
                _text(payload, "uri", "参考链接"),
                kind=payload.get("kind") or "link",
                timecode=_optional(payload, "timecode"),
                note=_optional(payload, "note"),
                findings=payload.get("findings") if isinstance(payload.get("findings"), str) else "",
                uncertainties=payload.get("uncertainties"))
            return 200, {"reference": reference}
        if path == "/api/creative/reference/replace":
            project_id = _query(query, "projectId")
            reference_id = _query(query, "referenceId")
            if not project_id or not reference_id:
                raise CreativeError("缺少 projectId 或 referenceId")
            reference = research.replace_reference(
                self.store, project_id, reference_id, body,
                filename=_query(query, "name"))
            return 200, {"reference": reference}
        if path == "/api/creative/reference/confirm":
            payload = _payload(body)
            confirmation = research.confirm_reference(
                self.store, _text(payload, "projectId", "项目"),
                payload.get("referenceIds"), payload.get("allowedChanges"),
                payload.get("preserved"), payload.get("note") or "")
            return 200, {"confirmation": confirmation}
        if path == "/api/creative/job":
            payload = _payload(body)
            job = jobs.create_job(
                self.store, _text(payload, "projectId", "项目"),
                _text(payload, "kind", "任务类型"),
                _text(payload, "operation", "任务操作"),
                input_version_id=payload.get("inputVersionId"),
                reference_ids=payload.get("referenceIds"),
                allowed_changes=payload.get("allowedChanges"),
                preserved=payload.get("preserved"),
                output_size=payload.get("outputSize"),
                require_alpha=payload.get("requireAlpha"),
                painted_fill=payload.get("paintedFill", False))
            return 200, {"job": job,
                         "instructionUrl": f"/api/creative/job/instruction?jobId={job['jobId']}"}
        if path == "/api/creative/jobs/scan":
            payload = _payload(body)
            changes = jobs.scan_project(
                self.store, _text(payload, "projectId", "项目"))
            return 200, {"changes": changes}
        if path == "/api/creative/job/cancel":
            payload = _payload(body)
            job = jobs.cancel_job(
                self.store, _text(payload, "projectId", "项目"),
                _text(payload, "jobId", "任务"))
            return 200, {"job": job}
        if path == "/api/creative/job/rebuild":
            payload = _payload(body)
            job = jobs.rebuild_job(
                self.store, _text(payload, "projectId", "项目"),
                _text(payload, "jobId", "任务"))
            return 200, {"job": job,
                         "instructionUrl": f"/api/creative/job/instruction?jobId={job['jobId']}"}
        if path == "/api/creative/pointer/seed":
            payload = _payload(body)
            version = manual.seed_pointer(
                self.store, _text(payload, "projectId", "项目"),
                _optional(payload, "sourcePath"), self.site_root)
            return 200, {"version": version}
        if path == "/api/creative/seed":
            payload = _payload(body)
            project_id = _text(payload, "projectId", "项目")
            project = state_module.find_project(self.store.read(), project_id)
            if project["objectKind"] == "pointer":
                version = manual.seed_pointer(
                    self.store, project_id, _optional(payload, "sourcePath"),
                    self.site_root)
            else:
                version = manual.seed_reference(
                    self.store, project_id, _text(payload, "referenceId", "参考"))
            return 200, {"version": version}
        if path == "/api/creative/pointer/lids":
            payload = _payload(body)
            version = manual.update_lids(
                self.store, _text(payload, "projectId", "项目"),
                _text(payload, "expression", "表情"), payload.get("rows"),
                _optional(payload, "note"))
            return 200, {"version": version}
        if path == "/api/creative/adopt":
            payload = _payload(body)
            project = research.adopt_version(
                self.store, _text(payload, "projectId", "项目"),
                _text(payload, "versionId", "版本"))
            return 200, {"project": self.project_payload(project["projectId"])}
        if path == "/api/creative/manual/export":
            payload = _payload(body)
            export = manual.export_manual(
                self.store, _text(payload, "projectId", "项目"),
                _text(payload, "versionId", "版本"),
                payload.get("role") or "full",
                payload.get("expression") or "open",
                payload.get("editor") or "piskel")
            return 200, {"export": export}
        if path == "/api/creative/manual/import":
            project_id = _query(query, "projectId")
            parent_id = _query(query, "parentVersionId")
            if not project_id or not parent_id:
                raise CreativeError("缺少 projectId 或 parentVersionId")
            version = manual.import_manual(
                self.store, project_id, parent_id, body,
                role=_query(query, "role", "full"),
                expression=_query(query, "expression", "open"),
                editor=_query(query, "editor", "piskel"),
                note=_query(query, "note"))
            return 200, {"version": version}
        if path == "/api/creative/manual/import-piskel":
            payload = _payload(body)
            version = manual.import_piskel(
                self.store, _text(payload, "projectId", "项目"),
                _text(payload, "parentVersionId", "父版本"),
                payload.get("piskel"),
                role=payload.get("role") or "full",
                expression=payload.get("expression") or "open",
                editor=payload.get("editor") or "piskel",
                note=_optional(payload, "note"))
            return 200, {"version": version}
        if path == "/api/creative/preview":
            payload = _payload(body)
            record = preview.create(
                self.store, self.root, self.creative_root, self.site_root,
                _text(payload, "projectId", "项目"),
                _text(payload, "versionId", "版本"),
                payload.get("overlays"), _optional(payload, "name"))
            return 200, {"preview": record}
        if path == "/api/creative/preview/check":
            payload = _payload(body)
            record = preview.check(
                self.store, self.root, self.creative_root, self.site_root,
                _text(payload, "projectId", "项目"),
                _text(payload, "previewId", "草稿"))
            return 200, {"preview": record}
        if path == "/api/creative/preview/apply":
            payload = _payload(body)
            record = preview.apply(
                self.store, self.root, self.creative_root, self.site_root,
                _text(payload, "projectId", "项目"),
                _text(payload, "previewId", "草稿"),
                confirm=payload.get("confirm") is True)
            return 200, {"preview": record}
        if path == "/api/creative/preview/rollback":
            payload = _payload(body)
            record = preview.rollback(
                self.store, self.root, self.creative_root, self.site_root,
                _text(payload, "projectId", "项目"),
                _text(payload, "previewId", "草稿"))
            return 200, {"preview": record}
        if path == "/api/creative/preview/cancel":
            payload = _payload(body)
            record = preview.cancel(
                self.store, self.root, self.creative_root, self.site_root,
                _text(payload, "projectId", "项目"),
                _text(payload, "previewId", "草稿"))
            return 200, {"preview": record}
        raise CreativeError("未知接口", status=404)
