"""State schema, atomic persistence, transitions, and restart recovery for the workbench."""

from __future__ import annotations

import copy
import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / ".local" / "output" / "homepage-images"
SCHEMA_VERSION = 1

RECEIVED = "received"
PREVIEWED = "previewed"
PLANNED = "planned"
WAITING_AI = "waiting_ai"
PROCESSING_LOCAL = "processing_local"
PROCESSED = "processed"
FAILED = "failed"
CANCELLED = "cancelled"
ADOPTED = "adopted"
DRAFT = "draft"
ENABLED = "enabled"
ARCHIVED = "archived"

STATUSES = (RECEIVED, PREVIEWED, PLANNED, WAITING_AI, PROCESSING_LOCAL, PROCESSED,
            FAILED, CANCELLED, ADOPTED, DRAFT, ENABLED, ARCHIVED)

TRANSITIONS = {
    RECEIVED: {PREVIEWED, PLANNED, WAITING_AI, PROCESSING_LOCAL, CANCELLED, ARCHIVED},
    PREVIEWED: {PLANNED, WAITING_AI, PROCESSING_LOCAL, CANCELLED, ARCHIVED},
    PLANNED: {WAITING_AI, PROCESSING_LOCAL, CANCELLED, ARCHIVED},
    WAITING_AI: {PROCESSING_LOCAL, PLANNED, FAILED, CANCELLED, ARCHIVED},
    PROCESSING_LOCAL: {PROCESSED, FAILED, CANCELLED, ARCHIVED},
    PROCESSED: {ADOPTED, PROCESSING_LOCAL, WAITING_AI, ARCHIVED},
    FAILED: {PLANNED, PROCESSING_LOCAL, WAITING_AI, CANCELLED, ARCHIVED},
    CANCELLED: {PLANNED, ARCHIVED},
    ADOPTED: {DRAFT, PROCESSED, WAITING_AI, ARCHIVED},
    DRAFT: {ENABLED, ADOPTED, ARCHIVED},
    ENABLED: {ARCHIVED},
    ARCHIVED: set(),
}

DEFAULT_SETTINGS = {
    "denoise": 0.35,
    "color": 0.4,
    "upscale": "auto",
    "removeText": "auto",
    "trimBorders": True,
    "preserveSignature": True,
}


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_state():
    return {
        "schemaVersion": SCHEMA_VERSION,
        "revision": 0,
        "createdAt": now(),
        "updatedAt": now(),
        "nextItem": 1,
        "items": [],
        "batches": [],
        "aiTasks": [],
        "drafts": [],
        "enabled": {"items": [], "migratedAt": None},
        "publications": [],
        "inbox": {},
        "settings": copy.deepcopy(DEFAULT_SETTINGS),
    }


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _relative_path(value, label):
    _require(isinstance(value, str) and value.strip(), f"{label} 路径不能为空")
    _require(not value.startswith(("/", "\\")) and ":" not in value[:2], f"{label} 必须是相对路径")
    parts = value.replace("\\", "/").split("/")
    _require(all(part not in ("", ".", "..") for part in parts), f"{label} 路径越界")
    return value.replace("\\", "/")


def validate_version(version, item_id):
    _require(isinstance(version, dict), f"{item_id} 的版本记录必须为对象")
    for key in ("versionId", "step", "path", "sha256", "size", "recipe", "processor", "inputSha256", "createdAt"):
        _require(key in version, f"{item_id} 的版本缺少字段: {key}")
    _relative_path(version["path"], "版本")
    _require(isinstance(version["sha256"], str) and len(version["sha256"]) == 64
               and all(c in "0123456789abcdef" for c in version["sha256"]), f"{item_id} 的版本 SHA-256 不合法")
    _require(isinstance(version["size"], list) and len(version["size"]) == 2
               and all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in version["size"]),
               f"{item_id} 的版本尺寸不合法")
    _require(isinstance(version["recipe"], dict), f"{item_id} 的版本配方必须为对象")
    _require(isinstance(version["processor"], str) and version["processor"].strip(), f"{item_id} 的版本处理器不能为空")
    _require(isinstance(version["inputSha256"], str) and len(version["inputSha256"]) == 64,
             f"{item_id} 的版本输入 SHA-256 不合法")


def validate_state(state):
    _require(isinstance(state, dict), "state 必须为对象")
    _require(state.get("schemaVersion") == SCHEMA_VERSION, "state schemaVersion 不支持")
    _require(isinstance(state.get("items"), list), "state.items 必须为列表")
    _require(isinstance(state.get("batches"), list), "state.batches 必须为列表")
    _require(isinstance(state.get("aiTasks"), list), "state.aiTasks 必须为列表")
    _require(isinstance(state.get("drafts"), list), "state.drafts 必须为列表")
    _require(isinstance(state.get("enabled"), dict), "state.enabled 必须为对象")
    _require(isinstance(state.get("settings"), dict), "state.settings 必须为对象")
    ids = set()
    for item in state["items"]:
        _require(isinstance(item, dict), "item 必须为对象")
        item_id = item.get("id")
        _require(isinstance(item_id, str) and item_id and item_id not in ids, f"item id 不合法或重复: {item_id}")
        ids.add(item_id)
        _require(isinstance(item.get("number"), int) and item["number"] > 0, f"{item_id} 的编号不合法")
        _require(item.get("status") in STATUSES, f"{item_id} 的状态不合法")
        original = item.get("original")
        _require(isinstance(original, dict), f"{item_id} 缺少原图记录")
        _relative_path(original.get("path"), "原图")
        _require(isinstance(original.get("sha256"), str) and len(original["sha256"]) == 64, f"{item_id} 原图 SHA-256 不合法")
        _require(isinstance(original.get("size"), list) and len(original["size"]) == 2, f"{item_id} 原图尺寸不合法")
        _require(isinstance(item.get("versions"), list), f"{item_id} 的版本链必须为列表")
        for version in item["versions"]:
            validate_version(version, item_id)
        _require(isinstance(item.get("settings"), dict), f"{item_id} 缺少处理设置")
        _require(isinstance(item.get("history"), list), f"{item_id} 缺少历史记录")
    task_ids = set()
    for task in state["aiTasks"]:
        _require(isinstance(task, dict), "AI 任务必须为对象")
        task_id = task.get("taskId")
        _require(isinstance(task_id, str) and task_id and task_id not in task_ids, f"AI 任务 id 不合法或重复: {task_id}")
        task_ids.add(task_id)
        _require(isinstance(task.get("itemId"), str), f"{task_id} 缺少图片 id")
        _require(isinstance(task.get("version"), int), f"{task_id} 缺少任务版本")
        _require(task.get("status") in ("waiting", "confirmed", "done", "rejected", "late", "conflict", "superseded"),
                 f"{task_id} 的任务状态不合法")
        _relative_path(task.get("jobPath"), "AI 任务")
    draft_ids = set()
    for draft in state["drafts"]:
        _require(isinstance(draft, dict), "草稿必须为对象")
        draft_id = draft.get("draftId")
        _require(isinstance(draft_id, str) and draft_id and draft_id not in draft_ids, f"草稿 id 不合法或重复: {draft_id}")
        draft_ids.add(draft_id)
        _require(draft.get("status") in ("building", "ready", "failed", "partial", "enabled"), f"{draft_id} 的草稿状态不合法")
    enabled = state["enabled"]
    _require(isinstance(enabled.get("items"), list), "已启用清单必须为列表")
    for scene in enabled["items"]:
        _require(isinstance(scene, dict) and isinstance(scene.get("id"), str), "已启用场景缺少 id")
        _require(isinstance(scene.get("master"), dict), f"{scene.get('id')} 缺少母版记录")
        _relative_path(scene["master"].get("path"), "已启用母版")
    return state


def transition(item, status, note=None):
    current = item.get("status")
    if current != status:
        _require(status in TRANSITIONS.get(current, set()), f"{item['id']} 不能从 {current} 转到 {status}")
    item["status"] = status
    item.setdefault("history", []).append({"status": status, "at": now(), **({"note": note} if note else {})})


def find_item(state, item_id):
    for item in state["items"]:
        if item["id"] == item_id:
            return item
    raise ValueError(f"找不到图片: {item_id}")


def find_task(state, task_id):
    for task in state["aiTasks"]:
        if task["taskId"] == task_id:
            return task
    raise ValueError(f"找不到 AI 任务: {task_id}")


def find_draft(state, draft_id):
    for draft in state["drafts"]:
        if draft["draftId"] == draft_id:
            return draft
    raise ValueError(f"找不到草稿: {draft_id}")


def current_version(item, step):
    for version in reversed(item.get("versions", [])):
        if version["step"] == step:
            return version["versionId"]
    return None


def item_summary(item):
    original = item["original"]
    versions = item.get("versions", [])
    latest = versions[-1] if versions else None
    current = item.get("currentVersions") or {}
    return {
        "id": item["id"],
        "number": item["number"],
        "filename": item.get("filename") or original.get("filename") or "",
        "status": item["status"],
        "receivedAt": item.get("receivedAt"),
        "batchId": item.get("batchId"),
        "duplicateOf": item.get("duplicateOf"),
        "original": {
            "path": original["path"],
            "sha256": original["sha256"],
            "size": original["size"],
            "format": original.get("format"),
            "bytes": original.get("bytes"),
        },
        "originalUrl": f"/media/{original['path']}",
        "analysis": item.get("analysis"),
        "settings": item.get("settings"),
        "versions": [
            {key: version[key] for key in
             ("versionId", "step", "path", "sha256", "size", "processor", "createdAt")}
            for version in versions
        ],
        "latestVersion": latest["versionId"] if latest else None,
        "fidelityVersion": current.get("fidelity") or current_version(item, "fidelity"),
        "enhancedVersion": current.get("enhanced") or current_version(item, "enhanced"),
        "currentVersions": current or None,
        "adoptedVersion": item.get("adoptedVersion"),
        "aiTaskId": item.get("aiTaskId"),
        "timeSuggestion": item.get("timeSuggestion"),
        "time": item.get("time"),
        "timeChoice": item.get("timeChoice"),
        "pendingConfirmation": item.get("pendingConfirmation"),
        "draftId": item.get("draftId"),
        "enabledId": item.get("enabledId"),
        "error": item.get("error"),
        "thumbUrl": f"/thumb?path={original['path']}",
    }


def task_summary(task):
    return {
        key: task.get(key) for key in
        ("taskId", "itemId", "version", "operation", "status", "confidence",
         "needsConfirmation", "createdAt", "completedAt", "error", "note", "resultSha256",
         "resultPath", "jobPath", "input")
    }


def draft_summary(draft):
    items = draft.get("items") or []
    return {
        key: draft.get(key) for key in
        ("draftId", "name", "status", "createdAt", "sceneCount", "baselineCount",
         "addedCount", "previewUrl", "assetsPath", "error")
    } | {"itemIds": [entry["itemId"] for entry in items], "items": items}


class StateStore:
    """In-memory state with atomic JSON snapshots and a process-local lock."""

    def __init__(self, root=None, create=True):
        self.root = Path(root or LIBRARY).resolve()
        self.path = self.root / "state.json"
        self.lock = threading.RLock()
        self.root.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.state = self.load()
        elif create:
            self.state = new_state()
            self.save(self.state)
        else:
            raise ValueError(f"缺少工作台状态: {self.path}")

    def load(self):
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return validate_state(data)

    def save(self, state):
        validate_state(state)
        state["updatedAt"] = now()
        temporary = self.path.with_name(self.path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump(state, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def read(self):
        with self.lock:
            return copy.deepcopy(self.state)

    def mutate(self, operation):
        with self.lock:
            state = copy.deepcopy(self.state)
            result = operation(state)
            state["revision"] = int(state.get("revision", 0)) + 1
            validate_state(state)
            self.save(state)
            self.state = state
            return copy.deepcopy(result)

    def replace(self, state):
        with self.lock:
            state = copy.deepcopy(state)
            state["revision"] = int(state.get("revision", 0)) + 1
            validate_state(state)
            self.save(state)
            self.state = state


def recover_interrupted(state):
    """Mark work that a stopped process cannot still be running; keep every version."""
    changed = []
    for item in state["items"]:
        if item["status"] == PROCESSING_LOCAL:
            item["status"] = PLANNED
            item["error"] = {
                "step": "recovery",
                "message": "服务重启恢复：处理未完成，从已有版本继续。",
                "at": now(),
            }
            item.setdefault("history", []).append(
                {"status": PLANNED, "at": now(), "note": "服务重启恢复"})
            changed.append(item["id"])
        for task in state["aiTasks"]:
            if task["itemId"] == item["id"] and task["status"] in ("waiting", "confirmed"):
                task.setdefault("attempts", [])
    return changed
