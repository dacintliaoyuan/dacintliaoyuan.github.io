"""Local HTTP service for the image workbench (127.0.0.1 only)."""

from __future__ import annotations

import argparse
import copy
import functools
import http.server
import json
import mimetypes
import os
import queue
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

from . import ai_jobs, analysis, drafts, library, migration, processing, publishing
from . import state as state_module

import build_assets


WEB = Path(__file__).resolve().parent / "web"
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".svg": "image/svg+xml", ".woff2": "font/woff2",
    ".ico": "image/x-icon", ".md": "text/markdown; charset=utf-8",
}
SETTINGS_KEYS = {"denoise", "color", "upscale", "removeText", "trimBorders", "preserveSignature"}


class ConfirmationRequired(Exception):
    def __init__(self, plans):
        super().__init__("有低置信度任务需要用户确认")
        self.plans = plans


def _alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _safe(root, value):
    root = Path(root).resolve()
    if not isinstance(value, str) or not value.strip():
        return None
    path = (root / value).resolve()
    if not path.is_relative_to(root) or path == root:
        return None
    return path


def _content_type(path):
    return CONTENT_TYPES.get(Path(path).suffix.lower(), "application/octet-stream")


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def normalize_settings(value, base=None):
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("处理设置必须为对象")
    unknown = set(value) - SETTINGS_KEYS
    if unknown:
        raise ValueError(f"未知处理设置: {', '.join(sorted(unknown))}")
    result = dict(state_module.DEFAULT_SETTINGS)
    result.update(base or {})
    result.update(value)
    for key in ("denoise", "color"):
        number = result.get(key, 0)
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not 0 <= number <= 1:
            raise ValueError(f"{key} 必须在 0 到 1 之间")
        result[key] = round(float(number), 3)
    if result.get("upscale") not in ("auto", "never"):
        raise ValueError("upscale 只能是 auto 或 never")
    if result.get("removeText") not in ("auto", "never"):
        raise ValueError("removeText 只能是 auto 或 never")
    for key in ("trimBorders", "preserveSignature"):
        if not isinstance(result.get(key), bool):
            raise ValueError(f"{key} 必须是布尔值")
    return result


class Workbench:
    def __init__(self, root=None, library_path=None, site=None):
        self.root = Path(root or state_module.ROOT).resolve()
        self.library = Path(library_path or self.root / ".local" / "output" / "homepage-images").resolve()
        self.site = Path(site or self.root / "site").resolve()
        self.library.mkdir(parents=True, exist_ok=True)
        self.store = state_module.StateStore(self.library)
        self.queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker_busy = False
        self.worker_current = None
        self.lock_path = self.library / "workbench.lock"
        self._lock_text = None
        self._worker = threading.Thread(target=self._work, daemon=True)
        self._watcher = threading.Thread(target=self._watch, daemon=True)

    def start(self):
        self._acquire_lock()
        recovered = self.store.mutate(lambda state: state_module.recover_interrupted(state))
        for item_id in recovered:
            item = state_module.find_item(self.store.read(), item_id)
            if item["status"] == state_module.PLANNED:
                self.queue.put(item_id)
        self.refresh_ai()
        self._worker.start()
        self._watcher.start()

    def stop(self):
        self.stop_event.set()
        self.queue.put(None)
        if self._worker.is_alive():
            self._worker.join(timeout=5)
        if self._watcher.is_alive():
            self._watcher.join(timeout=2)
        if self._lock_text and self.lock_path.exists():
            try:
                if self.lock_path.read_text(encoding="utf-8") == self._lock_text:
                    self.lock_path.unlink()
            except OSError:
                pass

    def _acquire_lock(self):
        if self.lock_path.exists():
            try:
                pid = int(self.lock_path.read_text(encoding="utf-8").split("pid=")[1].split()[0])
            except (OSError, ValueError, IndexError):
                pid = None
            if _alive(pid):
                raise ValueError(f"图片工作台已在运行（pid {pid}）；先停止它再启动。")
            self.lock_path.unlink()
        self._lock_text = f"pid={os.getpid()} started={state_module.now()}\n"
        with self.lock_path.open("x", encoding="utf-8") as stream:
            stream.write(self._lock_text)

    def _watch(self):
        while not self.stop_event.is_set():
            try:
                library.scan_inbox(self.store)
            except (ValueError, OSError):
                pass
            self.stop_event.wait(1.5)

    def _work(self):
        while not self.stop_event.is_set():
            try:
                item_id = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if item_id is None:
                self.queue.task_done()
                break
            self.worker_busy = True
            self.worker_current = item_id
            try:
                item = state_module.find_item(self.store.read(), item_id)
                if item["status"] == state_module.CANCELLED:
                    continue
                if item["status"] not in (state_module.PLANNED, state_module.PROCESSING_LOCAL):
                    continue

                def begin(state):
                    target = state_module.find_item(state, item_id)
                    target.pop("cancelRequested", None)
                    target["error"] = None
                    if target["status"] != state_module.PROCESSING_LOCAL:
                        state_module.transition(target, state_module.PROCESSING_LOCAL, "开始本机处理")
                    return target["settings"]

                settings = self.store.mutate(begin)
                processing.process_item(
                    self.store, self.library, item_id, settings,
                    cancel_check=lambda: bool(state_module.find_item(self.store.read(), item_id).get("cancelRequested")))
                self.store.mutate(lambda state: state_module.transition(
                    state_module.find_item(state, item_id), state_module.PROCESSED, "本机处理完成"))
            except processing.ProcessingCancelled:
                self.store.mutate(lambda state: state_module.transition(
                    state_module.find_item(state, item_id), state_module.CANCELLED, "处理已取消"))
            except Exception as error:
                step = getattr(error, "step", None) or "local"
                message = str(error)
                self.store.mutate(lambda state: self._fail(state, item_id, step, message))
            finally:
                self.worker_busy = False
                self.worker_current = None
                self.queue.task_done()

    @staticmethod
    def _fail(state, item_id, step, message):
        item = state_module.find_item(state, item_id)
        item["error"] = {"step": step, "message": message, "at": state_module.now()}
        if item["status"] in (state_module.PROCESSING_LOCAL, state_module.PLANNED):
            state_module.transition(item, state_module.FAILED, f"{step} 失败")
        return item

    def _analysis(self, item):
        if (item.get("analysis") and item["analysis"].get("sourceSha256") == item["original"]["sha256"]):
            return item["analysis"]
        result = analysis.analyze(self.library / item["original"]["path"])
        result["sourceSha256"] = item["original"]["sha256"]
        return result

    def plan_items(self, item_ids, settings=None, overrides=None, confirm=False):
        if not isinstance(item_ids, list) or not item_ids or not all(isinstance(value, str) for value in item_ids):
            raise ValueError("itemIds 必须是非空字符串列表")
        if overrides is None:
            overrides = {}
        if not isinstance(overrides, dict):
            raise ValueError("overrides 必须为对象")
        batch_settings = normalize_settings(settings)
        plans = []
        for item_id in item_ids:
            override = overrides.get(item_id)
            if override is not None and not isinstance(override, dict):
                raise ValueError(f"{item_id} 的单张覆盖设置必须为对象")
            item_settings = normalize_settings(override, batch_settings)
            item = state_module.find_item(self.store.read(), item_id)
            if item["status"] in (state_module.DRAFT, state_module.ENABLED, state_module.ARCHIVED):
                raise ValueError(f"{item_id} 当前状态不能重新处理: {item['status']}")
            if item["status"] == state_module.PROCESSING_LOCAL and item.get("aiTaskId"):
                done = state_module.find_task(self.store.read(), item["aiTaskId"])
                if done["status"] == "done":
                    plans.append({"itemId": item_id, "settings": item_settings,
                                  "action": "local", "needsConfirmation": False})
                    continue
            item_analysis = self._analysis(item)
            uncertainties = analysis.uncertainty_list(item_analysis)
            text = item_analysis.get("text") or {}
            border_uncertain = any(entry.get("kind") == "borders" for entry in uncertainties)
            signature_uncertain = any(entry.get("kind") == "signature" for entry in uncertainties)
            needs_confirmation = bool(
                border_uncertain or signature_uncertain or text.get("needsConfirmation"))
            if confirm and border_uncertain:
                item_analysis = copy.deepcopy(item_analysis)
                item_analysis["borders"]["confirmed"] = True
                uncertainties = [entry for entry in uncertainties
                                if entry.get("kind") != "borders"]
            plan = {"itemId": item_id, "settings": item_settings, "action": "local",
                    "needsConfirmation": False, "uncertainties": uncertainties}

            def apply(state, item_analysis=item_analysis, item_settings=item_settings):
                target = state_module.find_item(state, item_id)
                target["settings"] = item_settings
                target["analysis"] = item_analysis
                suggestion = item_analysis.get("time") or {}
                target["timeSuggestion"] = suggestion
                if not target.get("timeChoice"):
                    target["timeChoice"] = "auto"
                if target["timeChoice"] == "auto":
                    target["time"] = (suggestion.get("suggestion")
                                      if suggestion.get("suggestion") in ("day", "dusk", "night") else None)
                target["pendingConfirmation"] = False
                if target["status"] in (state_module.PROCESSED, state_module.FAILED,
                                         state_module.CANCELLED, state_module.ADOPTED):
                    target["status"] = state_module.PLANNED
                    target["history"].append({"status": state_module.PLANNED,
                                                "at": state_module.now(), "note": "重新规划"})
                return target

            self.store.mutate(apply)
            item = state_module.find_item(self.store.read(), item_id)
            if needs_confirmation and not confirm:
                self.store.mutate(lambda state: self._pending(state, item_id))
                plan["needsConfirmation"] = True
                plan["confidence"] = min((entry.get("confidence", 0) for entry in uncertainties),
                                          default=text.get("confidence", 0))
                plan["action"] = "confirm"
                plans.append(plan)
                continue
            if item_settings["removeText"] != "never" and text.get("needed"):
                task = self._ensure_task(item, text.get("confidence", 0.5))
                plan.update(action="ai", taskId=task["taskId"], confidence=text.get("confidence"))
                plans.append(plan)
                continue
            self.store.mutate(lambda state: state_module.transition(
                state_module.find_item(state, item_id), state_module.PLANNED, "等待本机处理"))
            plans.append(plan)
        return plans

    def _pending(self, state, item_id):
        item = state_module.find_item(state, item_id)
        item["pendingConfirmation"] = True
        if item["status"] != state_module.PLANNED:
            state_module.transition(item, state_module.PLANNED, "等待确认去字任务")
        return item

    def _ensure_task(self, item, confidence):
        task_id = item.get("aiTaskId")
        if task_id:
            task = state_module.find_task(self.store.read(), task_id)
            if task["status"] == "waiting" and task["version"] == int(item.get("planRevision") or 0):
                return task
        return ai_jobs.create_task(self.store, self.library, item["id"], confidence=confidence,
                                   root=self.root)

    def start_items(self, item_ids, settings=None, overrides=None, confirm=False):
        plans = self.plan_items(item_ids, settings, overrides, confirm=confirm)
        pending = [plan for plan in plans if plan.get("needsConfirmation")]
        if pending and not confirm:
            raise ConfirmationRequired(pending)
        for plan in plans:
            if plan.get("needsConfirmation"):
                ai_jobs.confirm_task(self.store, plan["taskId"])
                item = state_module.find_item(self.store.read(), plan["itemId"])
                task = self._ensure_task(item, plan.get("confidence", 0.5))
                plan.update(action="ai", taskId=task["taskId"], needsConfirmation=False)
                continue
            if plan.get("action") == "ai":
                continue
            self.queue.put(plan["itemId"])
        return plans

    def cancel_items(self, item_ids):
        changes = []
        for item_id in item_ids:
            def apply(state, item_id=item_id):
                item = state_module.find_item(state, item_id)
                if item["status"] == state_module.PROCESSING_LOCAL:
                    item["cancelRequested"] = True
                    item["history"].append({"status": item["status"], "at": state_module.now(),
                                              "note": "请求取消当前步骤"})
                    return {"itemId": item_id, "status": "cancelling"}
                if item["status"] == state_module.WAITING_AI and item.get("aiTaskId"):
                    task = state_module.find_task(state, item["aiTaskId"])
                    if task["status"] == "waiting":
                        task["status"] = "superseded"
                        task["supersededAt"] = state_module.now()
                if item["status"] not in (state_module.RECEIVED, state_module.PREVIEWED,
                                          state_module.PLANNED, state_module.WAITING_AI,
                                          state_module.FAILED):
                    raise ValueError(f"{item_id} 当前状态不能取消: {item['status']}")
                state_module.transition(item, state_module.CANCELLED, "用户取消")
                return {"itemId": item_id, "status": state_module.CANCELLED}

            changes.append(self.store.mutate(apply))
        return changes

    def retry_items(self, item_ids):
        changes = []
        for item_id in item_ids:
            def apply(state, item_id=item_id):
                item = state_module.find_item(state, item_id)
                if item["status"] not in (state_module.FAILED, state_module.CANCELLED):
                    raise ValueError(f"{item_id} 当前状态不能重试: {item['status']}")
                state_module.transition(item, state_module.PLANNED, "重试")
                item["error"] = None
                item["cancelRequested"] = False
                return {"itemId": item_id, "status": state_module.PLANNED}

            changes.append(self.store.mutate(apply))
            self.queue.put(item_id)
        return changes

    def set_time(self, item_id, value):
        if value not in ("auto", "day", "dusk", "night", "any"):
            raise ValueError("时段只能是 auto、day、dusk、night 或 any")

        def apply(state):
            item = state_module.find_item(state, item_id)
            if value == "auto":
                suggestion = (item.get("analysis") or {}).get("time") or {}
                proposed = suggestion.get("suggestion")
                item["timeChoice"] = "auto"
                item["time"] = proposed if proposed in ("day", "dusk", "night") else None
            elif value == "any":
                item["timeChoice"] = "any"
                item["time"] = None
            else:
                item["timeChoice"] = value
                item["time"] = value
            item["history"].append({"status": item["status"], "at": state_module.now(),
                                      "note": f"时段改为 {value}"})
            return {"itemId": item_id, "time": item["time"], "timeChoice": item["timeChoice"]}

        return self.store.mutate(apply)

    def adopt(self, item_id, version_id):
        def apply(state):
            item = state_module.find_item(state, item_id)
            if item["status"] not in (state_module.PROCESSED, state_module.ADOPTED):
                raise ValueError(f"{item_id} 尚未处理完成，不能采用")
            version = next((entry for entry in item["versions"]
                            if entry["versionId"] == version_id), None)
            if version is None:
                raise ValueError(f"{item_id} 没有这个版本: {version_id}")
            item["adoptedVersion"] = version_id
            if item["status"] != state_module.ADOPTED:
                state_module.transition(item, state_module.ADOPTED, "用户采用")
            return {"itemId": item_id, "adoptedVersion": version_id}

        return self.store.mutate(apply)

    def refresh_ai(self):
        """Scan AI output on every state read so an ordinary refresh discovers results."""
        try:
            changes = ai_jobs.scan_tasks(self.store, self.library)
        except (ValueError, OSError):
            return []
        for change in changes:
            if change.get("status") == "done":
                self.queue.put(change["itemId"])
        return changes

    def state_payload(self):
        state = self.store.read()
        counts = {status: 0 for status in state_module.STATUSES}
        for item in state["items"]:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        enabled = []
        for scene in state["enabled"]["items"]:
            entry = dict(scene)
            entry["thumbUrl"] = f"/thumb?path={scene['master']['path']}"
            enabled.append(entry)
        return {
            "schemaVersion": state_module.SCHEMA_VERSION,
            "revision": state["revision"],
            "counts": counts,
            "items": [state_module.item_summary(item) for item in state["items"]],
            "tasks": [state_module.task_summary(task) for task in state["aiTasks"]],
            "drafts": [state_module.draft_summary(draft) for draft in state["drafts"]],
            "enabled": enabled,
            "worker": {"busy": self.worker_busy, "current": self.worker_current},
            "inbox": str(self.library / "inbox"),
            "serverTime": state_module.now(),
            "timeSuggestionLabels": {"day": "白天", "dusk": "黄昏", "night": "夜晚", "any": "不分时段"},
        }

    def item_detail(self, item_id):
        item = state_module.find_item(self.store.read(), item_id)
        detail = json.loads(json.dumps(item))
        detail["versionUrls"] = {version["versionId"]: f"/media/{version['path']}"
                                 for version in item["versions"]}
        detail["originalUrl"] = f"/media/{item['original']['path']}"
        return detail

    def get(self, path, query):
        if path in ("/", "/index.html"):
            return 200, "text/html; charset=utf-8", (WEB / "index.html").read_bytes()
        if path in ("/app.js", "/styles.css"):
            return 200, _content_type(path), (WEB / path.lstrip("/")).read_bytes()
        if path == "/favicon.ico":
            return 204, "image/x-icon", b""
        if path == "/api/state":
            self.refresh_ai()
            return 200, "application/json; charset=utf-8", _json_bytes(self.state_payload())
        if path.startswith("/api/item/"):
            return 200, "application/json; charset=utf-8", _json_bytes(
                self.item_detail(path.rsplit("/", 1)[-1]))
        if path.startswith("/api/instruction/"):
            task_id = path.rsplit("/", 1)[-1]
            text = ai_jobs.task_instruction(self.store, task_id)
            return 200, "text/markdown; charset=utf-8", text.encode("utf-8")
        if path == "/media" or path.startswith("/media/"):
            relative = path[len("/media/"):]
            if not relative or relative.split("/", 1)[0] not in (
                    "originals", "versions", "enabled", "drafts", "ai-jobs", "thumbs"):
                return 404, "text/plain; charset=utf-8", b"not found"
            target = _safe(self.library, relative)
            if not target or not target.is_file():
                return 404, "text/plain; charset=utf-8", b"not found"
            return 200, _content_type(target), target
        if path == "/thumb":
            value = (query.get("path") or [""])[0]
            target = _safe(self.library, value)
            if not target or not target.is_file():
                return 404, "text/plain; charset=utf-8", b"not found"
            thumb = processing.thumbnail(self.library, value, 480)
            return 200, "image/webp", thumb
        if path.startswith("/site-assets/"):
            target = _safe(self.site / "assets", path[len("/site-assets/"):])
            if not target or not target.is_file():
                return 404, "text/plain; charset=utf-8", b"not found"
            return 200, _content_type(target), target
        if path.startswith("/fonts/"):
            target = _safe(self.site, path.lstrip("/"))
            if not target or not target.is_file():
                return 404, "text/plain; charset=utf-8", b"not found"
            return 200, _content_type(target), target
        if path == "/preview" or path.startswith("/preview/"):
            parts = path.split("/")
            if len(parts) < 3 or not parts[2]:
                return 404, "text/plain; charset=utf-8", b"not found"
            draft_id = parts[2]
            rest = "/".join(parts[3:]) or "index.html"
            if rest.startswith("assets/"):
                target = _safe(self.library / "drafts" / draft_id / "assets", rest[len("assets/"):])
            else:
                target = _safe(self.site, rest)
            if not target or not target.is_file():
                return 404, "text/plain; charset=utf-8", b"not found"
            return 200, _content_type(target), target
        return 404, "text/plain; charset=utf-8", b"not found"

    def post(self, path, query, body):
        if path == "/api/deliver":
            filename = (query.get("name") or ["image"])[0]
            record = library.ingest_bytes(self.library, body, filename)
            batch_id = (query.get("batch") or [f"web-{state_module.now()[:10]}"])[0]
            item = self.store.mutate(lambda state: library.create_item(
                state, record, batch_id, filename))
            return 200, {"item": state_module.item_summary(item)}
        if path == "/api/scan-inbox":
            ids = library.scan_inbox(self.store)
            return 200, {"ingested": ids}
        if path in ("/api/plan", "/api/start"):
            payload = self._payload(body)
            if path == "/api/plan":
                plans = self.plan_items(payload["itemIds"], payload["settings"],
                                        payload["overrides"], confirm=payload["confirm"])
                return 200, {"plans": plans}
            plans = self.start_items(payload["itemIds"], payload["settings"],
                                       payload["overrides"], confirm=payload["confirm"])
            return 200, {"plans": plans}
        if path == "/api/cancel":
            payload = self._payload(body)
            return 200, {"items": self.cancel_items(payload["itemIds"])}
        if path == "/api/retry":
            payload = self._payload(body)
            return 200, {"items": self.retry_items(payload["itemIds"])}
        if path == "/api/time":
            payload = self._payload(body)
            return 200, {"item": self.set_time(payload["itemId"], payload.get("time"))}
        if path == "/api/adopt":
            payload = self._payload(body)
            return 200, {"item": self.adopt(payload["itemId"], payload["versionId"])}
        if path == "/api/ai/scan":
            return 200, {"changes": self.refresh_ai()}
        if path == "/api/ai/confirm":
            payload = self._payload(body)
            task = ai_jobs.confirm_task(self.store, payload["taskId"])
            return 200, {"task": state_module.task_summary(task)}
        if path == "/api/ai/recreate":
            payload = self._payload(body)
            task = ai_jobs.recreate_task(self.store, self.library, payload["taskId"], root=self.root)
            return 200, {"task": state_module.task_summary(task)}
        if path == "/api/refresh":
            changes = self.refresh_ai()
            library.scan_inbox(self.store)
            return 200, {"changes": changes, "state": self.state_payload()}
        if path == "/api/draft":
            payload = self._payload(body)
            draft = drafts.create_draft(self.store, payload.get("name"), payload["itemIds"],
                                        library=self.library, site=self.site)
            return 200, {"draft": state_module.draft_summary(draft)}
        if path.startswith("/api/draft/") and path.endswith("/cancel"):
            draft_id = path.split("/")[3]
            payload = self._payload(body)
            draft = drafts.cancel_items(self.store, draft_id, payload["itemIds"],
                                         library=self.library, site=self.site)
            return 200, {"draft": state_module.draft_summary(draft)}
        if path.startswith("/api/draft/") and path.endswith("/enable"):
            draft_id = path.split("/")[3]
            payload = self._payload(body)
            result = self.enable_draft(draft_id, payload.get("itemIds"))
            return 200, result
        if path == "/api/publish/recover":
            payload = self._payload(body)
            result = publishing.recover(self.store, payload["token"],
                                         workspace=publishing.Workspace(self.root, self.library, self.site))
            return 200, result
        return 404, {"error": "未知接口"}

    @staticmethod
    def _payload(body):
        if not body:
            raise ValueError("请求缺少 JSON")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"请求 JSON 无法解析: {error}") from error
        if not isinstance(payload, dict):
            raise ValueError("请求必须是 JSON 对象")
        if not payload.get("itemIds") and "itemId" not in payload:
            if payload.get("taskId") or payload.get("token"):
                return {"itemIds": [], **payload}
            raise ValueError("请求缺少 itemIds")
        return {"itemIds": payload.get("itemIds") or [], "settings": payload.get("settings"),
                "overrides": payload.get("overrides") or {}, "confirm": bool(payload.get("confirm")),
                "itemId": payload.get("itemId"), "versionId": payload.get("versionId"),
                "taskId": payload.get("taskId"), "token": payload.get("token"),
                "name": payload.get("name"), "time": payload.get("time")}

    def enable_draft(self, draft_id, item_ids=None):
        state = self.store.read()
        draft = state_module.find_draft(state, draft_id)
        if draft["status"] not in ("ready", "partial"):
            raise ValueError(f"草稿当前状态不能启用: {draft['status']}")
        allowed = {entry["itemId"] for entry in draft["items"]}
        selected = list(item_ids) if item_ids is not None else sorted(allowed)
        if not selected:
            raise ValueError("至少选择一张图片再启用；空选择不会解释成全部启用。")
        unknown = [item_id for item_id in selected if item_id not in allowed]
        if unknown:
            raise ValueError(f"草稿中没有这些图片: {', '.join(unknown)}")
        draft_scenes = {
            scene["id"]: scene for scene in
            json.loads((self.library / "drafts" / draft_id / "approved.json")
                        .read_text(encoding="utf-8"))["scenes"]
        }
        scenes = [dict(scene) for scene in state["enabled"]["items"]]
        chosen = []
        for entry in draft["items"]:
            if entry["itemId"] not in selected:
                continue
            scene = draft_scenes.get(entry["sceneId"])
            if scene is None:
                raise ValueError(f"草稿场景缺失: {entry['sceneId']}")
            scenes.append(dict(scene))
            chosen.append(entry["itemId"])
        result = publishing.publish_scenes(
            self.store, scenes, chosen, name=draft["name"], draft_id=draft_id,
            workspace=publishing.Workspace(self.root, self.library, self.site))
        warning = None
        try:
            reduced = drafts.reduce_after_enable(
                self.store, draft_id, chosen, library=self.library, site=self.site)
        except (ValueError, OSError) as error:
            warning = f"正式站点已启用，但剩余草稿重建失败：{error}"
            reduced = state_module.draft_summary(
                state_module.find_draft(self.store.read(), draft_id))
        return {"publish": result, "draft": reduced,
                **({"warning": warning} if warning else {})}


class Handler(http.server.BaseHTTPRequestHandler):
    def __init__(self, *args, workbench=None, **kwargs):
        self.workbench = workbench
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        return

    def _send(self, status, content_type, body):
        if isinstance(body, Path):
            data = body.read_bytes()
        elif isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            status, content_type, body = self.workbench.get(parsed.path, urllib.parse.parse_qs(parsed.query))
        except ValueError as error:
            status, content_type, body = 400, "text/plain; charset=utf-8", str(error).encode("utf-8")
        except Exception as error:
            status, content_type, body = 500, "text/plain; charset=utf-8", str(error).encode("utf-8")
        self._send(status, content_type, body)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        if length > 200 * 1024 * 1024:
            self._send(413, "text/plain; charset=utf-8", "上传超过 200 MB".encode("utf-8"))
            return
        body = self.rfile.read(length) if length else b""
        try:
            status, payload = self.workbench.post(parsed.path, urllib.parse.parse_qs(parsed.query), body)
        except ConfirmationRequired as error:
            status, payload = 409, {"error": str(error), "confirmationRequired": True,
                                     "plans": error.plans}
        except publishing.PublicationError as error:
            status, payload = 500, {"error": str(error), "recoveryRequired": error.recovery_required,
                                      "token": error.token}
        except ValueError as error:
            status, payload = 400, {"error": str(error)}
        except Exception as error:
            status, payload = 500, {"error": str(error)}
        self._send(status, "application/json; charset=utf-8", _json_bytes(payload))


def main(argv=None):
    parser = argparse.ArgumentParser(description="本机图片工作台（只监听 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--root", type=Path, default=state_module.ROOT)
    parser.add_argument("--library", type=Path)
    parser.add_argument("--site", type=Path)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    workbench = Workbench(args.root, args.library, args.site)
    handler = functools.partial(Handler, workbench=workbench)
    try:
        workbench.start()
    except ValueError as error:
        print(f"图片工作台启动失败: {error}", flush=True)
        return 1
    try:
        with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
            url = f"http://127.0.0.1:{args.port}/"
            print(f"图片工作台：{url}", flush=True)
            print(f"接收文件夹：{workbench.library / 'inbox'}", flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        workbench.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
