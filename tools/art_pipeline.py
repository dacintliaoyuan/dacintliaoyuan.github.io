"""Resumable local artwork queue. Selection and final adoption remain explicit user decisions."""
import argparse
import copy
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid
import zipfile
import re

from PIL import Image

import prepare_scenes
import build_assets
import art_pipeline_sources as sources
import art_pipeline_processing as processing

HOME = Path(__file__).resolve().parents[1]
LIBRARY = HOME / ".local" / "output" / "adashima-art"
DECISIONS = {"pending", "selected", "paused", "excluded"}
DEFAULT_UPSCAYL = {"binary": "D:/apps/upscayl/resources/bin/upscayl-bin.exe",
                   "modelDir": "D:/apps/upscayl/resources/models", "model": "high-fidelity-4x",
                   "scale": 2, "tile": 256, "timeout": 240, "minLongEdge": 3000}


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".partial")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def verify_artifact(library, artifact):
    path = prepare_scenes.local_path(library, artifact["path"])
    actual = processing.inspect_image(library, path)
    if actual["sha256"] != artifact["sha256"] or actual["size"] != artifact["size"]:
        raise ValueError(f"图片已变化，保留现场，需登记新版本: {artifact['path']}")
    return path


def pipeline_key(item):
    return fingerprint({"source": item["source"], "recipe": item["recipe"]})


def best_artifact(item):
    for name in ("adopted", "enhanced", "cropped", "clean"):
        if item.get("variants", {}).get(name):
            return item["variants"][name]
    return item["source"]


def approved(item):
    review = item.get("approval", {})
    return (review.get("status") == "approved" and review.get("recipeKey") == pipeline_key(item)
            and review.get("artifactSha256") == best_artifact(item)["sha256"])


def process_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        raise ValueError("锁文件没有有效进程身份")
    if os.name == "nt":
        # os.kill(pid, 0) is not a safe liveness probe on Windows.
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return False
            raise ValueError("无法核对锁持有进程，请保留锁文件")
        try:
            code = ctypes.c_ulong()
            if not kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)):
                raise ValueError("无法读取锁持有进程状态")
            return code.value == 259
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError as error:
        raise ValueError("无权核对锁持有进程，请保留锁") from error


class Workspace:
    def __init__(self, library=LIBRARY, directory=None, home=HOME):
        self.library = Path(library).resolve()
        self.directory = Path(directory or self.library / "art-pipeline").resolve()
        if not self.directory.is_relative_to(self.library) or self.directory == self.library:
            raise ValueError("流水线工作目录必须在图库内")
        self.home = Path(home).resolve()
        self.path = self.directory / "pipeline.json"
        self.lock = self.directory / "queue.lock"

    @contextmanager
    def edit(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        try:
            stream = self.lock.open("x", encoding="utf-8")
        except FileExistsError as error:
            raise ValueError(f"已有任务或中断锁: {self.lock}；先查看 status，再按锁token recover") from error
        with stream:
            json.dump({"pid": os.getpid(), "token": token, "at": now()}, stream)
        try:
            yield
        finally:
            if self.lock.exists() and read(self.lock).get("token") == token:
                self.lock.unlink()

    def load(self):
        state = read(self.path)
        if (not isinstance(state, dict) or state.get("schemaVersion") != 1
                or not isinstance(state.get("items"), list) or not isinstance(state.get("sources"), list)):
            raise ValueError("任务清单格式不支持")
        ids = [prepare_scenes.valid_id(x["id"]) for x in state["items"]]
        if len(ids) != len(set(ids)) or any(x["decision"]["status"] not in DECISIONS for x in state["items"]):
            raise ValueError("任务清单有重复ID或无效选择")
        for item in state["items"]:
            item["pipelineKey"] = pipeline_key(item)
        for source in state["sources"]:
            sources.validate_source(source)
        return state

    def write(self, state):
        for item in state["items"]:
            item["pipelineKey"] = pipeline_key(item)
        state["revision"] = state.get("revision", 0) + 1
        state["updatedAt"] = now()
        save(self.path, state)

    def init(self):
        with self.edit():
            if self.path.exists():
                raise ValueError("任务清单已存在，不重复初始化")
            state = {"schemaVersion": 1, "createdAt": now(), "revision": 0,
                     "settings": {"upscayl": DEFAULT_UPSCAYL.copy()}, "sources": [], "items": []}
            self.write(state)
        return state

    @staticmethod
    def item(state, identity):
        for item in state["items"]:
            if item["id"] == identity:
                return item
        raise ValueError(f"没有任务: {identity}")

    def ingest(self, path):
        path = Path(path).resolve()
        with Image.open(path) as image:
            image.load()
        checksum = prepare_scenes.digest(path)
        if path.is_relative_to(self.library):
            return processing.inspect_image(self.library, path)
        extension = path.suffix.lower() if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"} else ".png"
        destination = self.directory / "imports" / (checksum + extension)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            temp = destination.with_name(destination.name + "." + uuid.uuid4().hex + ".partial")
            try:
                shutil.copyfile(path, temp)
                if prepare_scenes.digest(temp) != checksum:
                    raise ValueError("复制期间输入已变化")
                # All writers use the queue lock; no existing original is replaced.
                if destination.exists():
                    raise ValueError("输入归档目标意外出现")
                temp.rename(destination)
            finally:
                temp.unlink(missing_ok=True)
        result = processing.inspect_image(self.library, destination)
        if result["sha256"] != checksum:
            raise ValueError("已有输入归档与源文件不同")
        return result

    def add_image(self, state, identity, title, artist, path, link="", official=False):
        prepare_scenes.valid_id(identity)
        if any(x["id"] == identity for x in state["items"]):
            raise ValueError("已有同ID素材，请使用 set-source 登记新输入版本")
        if link:
            sources.validate_source({"id": "check", "category": "page", "title": title, "pageUrl": link,
                                     "status": "not_checked", "checkedAt": None, "note": "", "evidence": [], "artworkIds": []})
        source = self.ingest(path)
        item = {"id": identity, "title": title, "artist": artist, "official": bool(official), "link": link,
                "source": source, "variants": {"original": source},
                "decision": {"status": "pending", "at": now()},
                "recipe": {"textRemoval": {"mode": "undecided"}, "crop": None,
                           "upscale": {"enabled": True}, "box": [0.05, 0.1, 0.95, 1.0], "cx": 0.5},
                "stages": {}, "approval": {"status": "pending"}, "integrated": {"status": "pending"}}
        state["items"].append(item)
        return item

    def import_restoration(self, state, batch):
        batch = Path(batch).resolve()
        if not batch.is_relative_to(self.library):
            raise ValueError("历史批次必须在图库内")
        manifest, adoption = read(batch / "manifest.json"), read(batch / "review-selection.json")
        if not adoption.get("finalApproval"):
            raise ValueError("只能导入已经用户验收的采用记录")
        frames = {x["id"]: x for x in read(self.library / "scenes-approved.json")["scenes"]}
        existing = {x["id"] for x in state["items"]}
        count = 0
        for row in manifest["items"] + manifest.get("archivedItems", []):
            if row["id"] in existing:
                continue
            raw = row.get("processingSource") or row["original"]
            path = (batch / raw["file"]).resolve()
            source = processing.inspect_image(self.library, path)
            if source["sha256"] != raw["sha256"]:
                raise ValueError(f"历史输入变化: {row['id']}")
            item = self.add_image(state, row["id"], row["title"], row.get("artist", ""), path, row.get("link", ""), True)
            item["number"] = row["number"]
            item["recipe"] = {"imported": True, "batchRevision": adoption["revision"], "box": [0.05, 0.1, 0.95, 1.0], "cx": 0.5}
            for key in ("clean", "enhanced", "cropped"):
                if row.get(key):
                    record = row[key]
                    artifact = processing.inspect_image(self.library, (batch / record["file"]).resolve())
                    if artifact["sha256"] != record["sha256"]:
                        raise ValueError(f"历史结果变化: {row['id']} {key}")
                    item["variants"][key] = artifact
            choice = adoption["choices"].get(row["id"])
            if choice:
                adopted = processing.inspect_image(self.library, (batch / choice["file"]).resolve())
                if adopted["sha256"] != choice["sha256"]:
                    raise ValueError("历史采用稿校验失败")
                item["variants"]["adopted"] = adopted
                item["adoptedVersion"] = choice["version"]
                if row["id"] in frames:
                    frame = frames[row["id"]]
                    build_assets.validate_approved_artwork(self.library, frame)
                    if frame["master"]["sha256"] != adopted["sha256"]:
                        raise ValueError("主页采用记录与批次不同")
                    item["recipe"].update(box=frame["box"], cx=frame["cx"])
                item["decision"] = {"status": "selected", "at": choice["selectedAt"], "reason": "导入既有用户选择"}
                item["approval"] = {"status": "approved", "artifactSha256": adopted["sha256"],
                                    "recipeKey": pipeline_key(item), "reviewer": "user", "note": "导入既有验收记录",
                                    "at": adoption.get("approvedAt", choice["selectedAt"])}
                item["integrated"] = {"status": "integrated" if adoption.get("siteIntegrated") else "pending",
                                      "artifactSha256": adopted["sha256"]}
                item["stages"]["import"] = {"status": "done", "artifact": adopted}
            else:
                status = "paused" if row["number"] in adoption.get("excludedNumbers", []) else "excluded"
                item["decision"] = {"status": status, "reason": row.get("note", "导入原有暂停/移除状态")}
            if row.get("sourceLabel"):
                item["sourceLabel"] = row["sourceLabel"]
            self.add_coverage(state, row.get("link", ""), row["title"], row["id"], batch.name)
            count += 1
        return count

    def add_coverage(self, state, url, title, identity, batch_name=""):
        if not url:
            return
        key = "page-" + fingerprint(url)[:16]
        for row in state["sources"]:
            if row["id"] == key:
                if identity not in row["artworkIds"]:
                    row["artworkIds"].append(identity)
                return
        # An archived artwork proves a download, not exhaustive inspection of an author or site.
        row = {"id": key, "category": "page", "title": title, "pageUrl": url,
               "status": "not_checked", "checkedAt": None, "note": "历史图片出处；尚未登记此来源范围的覆盖检查",
               "evidence": [{"kind": "legacy_artwork", "batch": batch_name}], "artworkIds": [identity]}
        sources.validate_source(row)
        state["sources"].append(row)

    def plan(self, state, identity, mode, prompt="", mask=None, bounds=None, upscale=True, note="", box=None, cx=None):
        item = self.item(state, identity)
        verify_artifact(self.library, item["source"])
        if mode not in {"none", "gpt"} or mode == "gpt" and not prompt.strip():
            raise ValueError("请选择 none/gpt；GPT编辑需要明确提示词")
        if bounds is not None:
            w, h = item["source"]["size"]
            if (len(bounds) != 4 or any(type(x) is not int for x in bounds)
                    or not 0 <= bounds[0] < bounds[2] <= w or not 0 <= bounds[1] < bounds[3] <= h):
                raise ValueError("裁剪矩形越界或不是整数")
        mask_record = self.ingest(mask) if mask else None
        if mask_record and (mode != "gpt" or mask_record["size"] != item["source"]["size"]):
            raise ValueError("去字遮罩必须与源图同尺寸")
        recipe = {"textRemoval": {"mode": mode, "prompt": prompt, "mask": mask_record},
                  "crop": bounds, "upscale": {"enabled": bool(upscale), "settings": copy.deepcopy(state["settings"]["upscayl"])},
                  "box": box or item["recipe"].get("box", [0.05, 0.1, 0.95, 1.0]),
                  "cx": cx if cx is not None else item["recipe"].get("cx", 0.5),
                  "technicalReview": {"reviewer": "assistant", "note": note}}
        if recipe == item["recipe"]:
            return
        item.setdefault("history", []).append({"at": now(), "recipe": item["recipe"], "variants": item["variants"],
                                               "approval": item["approval"]})
        item.update(recipe=recipe, variants={"original": item["source"]}, stages={}, approval={"status": "pending"},
                    integrated={"status": "pending"},
                    lastRun={"status": "planned", "at": now()})

    def stage_key(self, name, source, recipe):
        return fingerprint({"stage": name, "input": {k: source[k] for k in ("sha256", "size")}, "recipe": recipe,
                            "processor": prepare_scenes.digest(Path(processing.__file__))})

    def cached(self, key):
        record = self.directory / "cache" / key / "result.json"
        if not record.exists():
            return None
        result = read(record)
        if result.get("key") != key:
            raise ValueError("缓存身份错误")
        verify_artifact(self.library, result["artifact"])
        return result["artifact"]

    def execute_stage(self, item, name, source, recipe, operation):
        key = self.stage_key(name, source, recipe)
        cached = self.cached(key)
        if cached:
            item["stages"][name] = {"status": "reused", "key": key, "artifact": cached}
            return cached
        folder = self.directory / "cache" / key / ("attempt-" + uuid.uuid4().hex)
        folder.mkdir(parents=True)
        item["stages"][name] = {"status": "running", "key": key, "at": now()}
        if getattr(self, "_running_state", None) is not None:
            self.write(self._running_state)
        artifact = operation(folder / "result.png")
        verify_artifact(self.library, artifact)
        save(folder.parent / "result.json", {"key": key, "artifact": artifact, "completedAt": now()})
        item["stages"][name] = {"status": "done", "key": key, "artifact": artifact}
        return artifact

    def gpt_key(self, item):
        return self.stage_key("clean", item["source"], item["recipe"]["textRemoval"])

    def record_clean(self, state, identity, path, job_key):
        item = self.item(state, identity)
        if item["decision"]["status"] != "selected" or item["recipe"].get("textRemoval", {}).get("mode") != "gpt":
            raise ValueError("仅已选且需要GPT的任务可以登记结果")
        if job_key != self.gpt_key(item):
            raise ValueError("GPT任务已变化，拒绝把旧输出写入新任务")
        with Image.open(path) as image:
            if image.format != "PNG":
                raise ValueError("GPT去字结果必须为实际PNG文件，不只检查扩展名")
            image.load()
        edited = self.ingest(path)
        text = item["recipe"]["textRemoval"]
        cached = self.cached(job_key)
        if cached and cached.get("editedSha256") != edited["sha256"]:
            raise ValueError("该去字任务已有另一结果；请登记新配方版本，旧结果继续保留")
        if text.get("mask"):
            verify_artifact(self.library, text["mask"])
        artifact = self.execute_stage(item, "clean", item["source"], text,
                    lambda destination: processing.composite_clean(self.library, item["source"],
                       self.library / edited["path"], text.get("mask"), destination))
        item["variants"]["clean"] = artifact

    def run_item(self, state, item):
        if item["decision"]["status"] != "selected":
            return item["decision"]["status"]
        verify_artifact(self.library, item["source"])
        if item["recipe"].get("imported"):
            if not approved(item):
                raise ValueError("历史记录未有效验收；先明确新处理方案")
            verify_artifact(self.library, best_artifact(item))
            return "reused_adopted"
        text = item["recipe"]["textRemoval"]
        if text["mode"] == "undecided":
            return "needs_plan"
        if text.get("mask"):
            verify_artifact(self.library, text["mask"])
        if text["mode"] == "gpt":
            key = self.gpt_key(item)
            clean = self.cached(key)
            if not clean:
                job = {"id": item["id"], "key": key, "source": item["source"], "prompt": text["prompt"], "mask": text.get("mask")}
                save(self.directory / "gpt-jobs" / (key + ".json"), job)
                item["stages"]["clean"] = {"status": "waiting_gpt", "key": key}
                return "waiting_gpt"
            item["stages"]["clean"] = {"status": "reused", "key": key, "artifact": clean}
        else:
            clean = item["source"]
            item["stages"]["clean"] = {"status": "skipped", "reason": "确认无需去字", "artifact": clean}
        item["variants"]["clean"] = clean
        result = clean
        if item["recipe"]["crop"]:
            bounds = item["recipe"]["crop"]
            result = self.execute_stage(item, "crop", clean, bounds,
                      lambda destination: processing.crop_image(self.library, clean, bounds, destination))
            item["variants"]["cropped"] = result
        if item["recipe"]["upscale"]["enabled"]:
            settings = item["recipe"]["upscale"].get("settings", state["settings"]["upscayl"])
            if max(result["size"]) >= settings["minLongEdge"]:
                item["stages"]["upscale"] = {"status": "skipped", "reason": "原尺寸已达目标长边", "artifact": result}
            else:
                model = Path(settings["modelDir"])
                signature = {"settings": settings, "binarySha256": prepare_scenes.digest(Path(settings["binary"])),
                             "modelSha256": {ext: prepare_scenes.digest(model / (settings["model"] + "." + ext))
                                             for ext in ("bin", "param")}}
                current = result
                worker_settings = {k: v for k, v in settings.items() if k != "minLongEdge"}
                result = self.execute_stage(item, "upscale", current, signature,
                           lambda destination: processing.upscale_image(self.library, current, destination, worker_settings))
            item["variants"]["enhanced"] = result
        verify_artifact(self.library, item["source"])
        return "approved" if approved(item) else "awaiting_review"

    def run(self, state, identities=(), retry=False):
        chosen = set(identities)
        for identity in chosen:
            self.item(state, identity)
        counts = {}
        self._running_state = state
        try:
            for item in state["items"]:
                if chosen and item["id"] not in chosen:
                    continue
                if item["decision"]["status"] != "selected":
                    result = item["decision"]["status"]
                elif item.get("lastRun", {}).get("status") == "failed" and not retry:
                    result = "failed"
                else:
                    try:
                        result = self.run_item(state, item)
                        item["lastRun"] = {"status": result, "at": now()}
                    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
                        result = "failed"
                        item["lastRun"] = {"status": result, "at": now(), "error": str(error)}
                        for attribute in ("log_path", "receipt_path", "returncode"):
                            value = getattr(error, attribute, None)
                            if value is not None:
                                item["lastRun"][attribute] = str(value) if isinstance(value, Path) else value
                        for stage in item["stages"].values():
                            if stage.get("status") == "running":
                                stage.update(status="failed", error=str(error), at=now())
                    except KeyboardInterrupt:
                        item["lastRun"] = {"status": "interrupted", "at": now()}
                        for stage in item["stages"].values():
                            if stage.get("status") == "running":
                                stage.update(status="interrupted", at=now())
                        self.write(state)
                        raise
                counts[result] = counts.get(result, 0) + 1
                self.write(state)
        finally:
            self._running_state = None
        return counts

    def apply_decisions(self, state, data):
        if data.get("schemaVersion") != 1 or not isinstance(data.get("items"), list):
            raise ValueError("选择文件格式错误")
        changes, seen = [], set()
        for row in data["items"]:
            item = self.item(state, row["id"])
            if row["id"] in seen or row.get("decision") not in DECISIONS or type(row.get("approve")) is not bool:
                raise ValueError("选择文件包含重复项或错误状态")
            if "note" in row and not isinstance(row["note"], str):
                raise ValueError("选择备注必须是文本")
            seen.add(row["id"])
            artifact = best_artifact(item)
            if row.get("pipelineKey") != pipeline_key(item) or row.get("artifactSha256") != artifact["sha256"]:
                raise ValueError(f"选择页面已过期，请刷新再选: {item['id']}")
            verify_artifact(self.library, artifact)
            if row["approve"] and row["decision"] != "selected":
                raise ValueError("暂停/排除/待选不能标记验收通过")
            if row["approve"] and not item["recipe"].get("imported") and item.get("lastRun", {}).get("status") not in {"awaiting_review", "approved"}:
                raise ValueError("处理尚未完成，不能提前验收")
            changes.append((item, row))
        for item, row in changes:
            item["decision"] = {"status": row["decision"], "at": now(), "reason": row.get("note", "").strip() or "用户在处理报告中选择"}
            item["approval"] = ({"status": "approved", "at": now(), "reviewer": "user", "note": row.get("note", "").strip() or "用户验收当前采用版本",
                                 "artifactSha256": row["artifactSha256"], "recipeKey": row["pipelineKey"]}
                                if row["approve"] else {"status": "pending"})

    def status(self, state):
        counts = {}
        for item in state["items"]:
            key = item["decision"]["status"]
            counts[key] = counts.get(key, 0) + 1
        return {"items": len(state["items"]), "decisions": counts,
                "approved": sum(approved(x) for x in state["items"]), "coverage": sources.summarize(state["sources"]),
                "queueLock": read(self.lock) if self.lock.exists() else None}

    def set_source(self, state, identity, path, note):
        if not note.strip():
            raise ValueError("更换输入需要填写原因")
        item = self.item(state, identity)
        source = self.ingest(path)
        if source == item["source"]:
            return "unchanged"
        item.setdefault("history", []).append({"at": now(), "reason": note, "source": item["source"],
                                               "recipe": item["recipe"], "variants": item["variants"],
                                               "approval": item["approval"]})
        item.update(source=source, variants={"original": source}, stages={},
                    recipe={"textRemoval": {"mode": "undecided"}, "crop": None, "upscale": {"enabled": True},
                            "box": item["recipe"].get("box", [0.05, 0.1, 0.95, 1.0]), "cx": item["recipe"].get("cx", 0.5)},
                    approval={"status": "pending"}, integrated={"status": "pending"},
                    lastRun={"status": "needs_plan", "at": now()})
        return "updated"

    def source_add(self, state, url, title, category="page", artwork_ids=()):
        identity = "page-" + fingerprint(url)[:16]
        row = {"id": identity, "category": category, "title": title, "pageUrl": url,
               "status": "not_checked", "checkedAt": None, "note": "尚未检查此页面/注明范围",
               "evidence": [], "artworkIds": list(artwork_ids)}
        sources.validate_source(row)
        for existing in state["sources"]:
            if existing["id"] == identity:
                existing["artworkIds"] = list(dict.fromkeys(existing["artworkIds"] + list(artwork_ids)))
                return existing
        state["sources"].append(row)
        return row

    def source_note(self, state, identity, status, note, evidence=(), checked_at=None):
        for index, row in enumerate(state["sources"]):
            if row["id"] == identity:
                updated = sources.set_observation(row, status, note, evidence, checked_at)
                if updated != row:
                    updated["history"] = row.get("history", []) + [{k: copy.deepcopy(row[k])
                                           for k in ("status", "checkedAt", "note", "evidence")}]
                    state["sources"][index] = updated
                return updated
        raise ValueError("没有该来源，请先 source-add")

    def download(self, state, identity, url, refresh=False):
        item = self.item(state, identity)
        signature = fingerprint(url)
        receipt = self.directory / "downloads" / signature / "receipt.json"
        if not refresh and receipt.is_file():
            artifact = read(receipt)["artifact"]
            verify_artifact(self.library, artifact)
            if artifact not in item.setdefault("downloadCandidates", []):
                item["downloadCandidates"].append(artifact)
            return {"status": "reused", "artifact": artifact}
        destination = receipt.parent / ("attempt-" + uuid.uuid4().hex + ".image")
        row = self.source_add(state, url, "明确提供的图片地址", "image", [identity])
        try:
            artifact = sources.download_image(url, self.library, destination)
        except sources.DownloadError as error:
            # Preserve a failed observation, never infer that an artwork does not exist.
            status = "access_restricted" if error.status in {401, 403, 429, 451} else "checked"
            self.source_note(state, row["id"], status, "下载失败；不代表不存在原图: " + str(error),
                             [{"kind": "download_failure", "status": error.status}])
            self.write(state)
            raise
        save(receipt, {"artifact": artifact, "at": now()})
        item.setdefault("downloadCandidates", []).append(artifact)
        self.source_note(state, row["id"], "checked", "成功取得这个图片地址的文件；是否为最佳原稿仍待核对",
                         [{"kind": "download", "artifact": artifact}])
        # A download is a candidate. Explicit set-source invalidates prior processing and approval.
        return {"status": "downloaded", "artifact": artifact}

    def import_observations(self, state, data):
        rows = data.get("sources") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise ValueError("来源导入需要 sources 数组")
        validated = copy.deepcopy(rows)
        for row in validated:
            sources.validate_source(row)
        if len({x["id"] for x in validated}) != len(validated):
            raise ValueError("来源导入有重复 ID")
        existing = {x["id"]: x for x in state["sources"]}
        for row in validated:
            old = existing.get(row["id"])
            if old and old["pageUrl"] != row["pageUrl"]:
                raise ValueError("同来源 ID 不允许更换页面地址")
        count = 0
        for row in validated:
            old = existing.get(row["id"])
            if old:
                old["artworkIds"] = list(dict.fromkeys(old["artworkIds"] + row["artworkIds"]))
                # Import older evidence without replacing a newer explicit observation.
                if old["checkedAt"] and (not row["checkedAt"] or
                        datetime.fromisoformat(old["checkedAt"].replace("Z", "+00:00")) >=
                        datetime.fromisoformat(row["checkedAt"].replace("Z", "+00:00"))):
                    continue
                old.update({k: row[k] for k in ("status", "checkedAt", "note", "evidence")})
            else:
                state["sources"].append(row)
                existing[row["id"]] = row
            count += 1
        return count

    def seed_legacy_evidence(self, state):
        """Read known saved research only; this command performs no fresh web search."""
        observations = {}

        def add(url, title, status, note, evidence, artwork_ids=(), day="2026-10-14", category="page"):
            if not url:
                return
            identity = "page-" + fingerprint(url)[:16]
            at = day[:10] + "T23:59:59+08:00"
            row = observations.get(identity)
            if row is None:
                row = {"id": identity, "category": category, "title": title, "pageUrl": url,
                       "status": status, "checkedAt": at, "note": note, "evidence": [], "artworkIds": []}
                observations[identity] = row
            row["evidence"].append(evidence)
            row["artworkIds"] = list(dict.fromkeys(row["artworkIds"] + list(artwork_ids)))

        relative = "official-selection-20261014/research/source-results.json"
        path = self.library / relative
        if path.is_file():
            data = read(path)
            witness = {"file": relative, "sha256": prepare_scenes.digest(path), "historical": True}
            for row in data.get("sources", []):
                add(row.get("link"), "出版社页面（保存的调查）", "only_preview",
                    "历史调查取得带字封面或展示图；只覆盖记录中的页面，不表示已查完平台。 " + row.get("notes", ""),
                    {**witness, "candidateId": row.get("candidateId"), "imageUrl": row.get("image_url"),
                     "imagePath": row.get("file"), "imageSha256": row.get("sha256"), "variant": row.get("variant")},
                    [row["candidateId"]] if row.get("candidateId") else [])
            for row in data.get("failures", []):
                add(row.get("image_url") or row.get("link"), "历史下载失败的图片地址", "access_restricted",
                    "当时请求失败；尚未重新核验。 " + str(row.get("status", "")) + " " + str(row.get("error", "")),
                    {**witness, "page": row.get("link"), "status": row.get("status")}, category="image")
        relative = "supplemental-commercial-20261014/search-results.json"
        path = self.library / relative
        if path.is_file():
            data = read(path)
            for row in data.get("results", []):
                add(row.get("officialPage"), "活动/商品来源（保存的调查）", "only_preview",
                    "当时仅找到宣传图或商品预览；没找到独立无字稿。 " + str(row.get("finding", "")),
                    {"file": relative, "sha256": prepare_scenes.digest(path), "historical": True,
                     "independentCleanOriginal": row.get("independentCleanOriginal")},
                    [row["existingBannerId"]] if row.get("existingBannerId") else [])
        relative = "four-art-import-20261015/download-verification.json"
        path = self.library / relative
        if path.is_file():
            for row in read(path).get("items", []):
                add(row.get("page") or row.get("url"), "四幅补图的下载出处", "checked",
                    "历史下载已记录文件哈希和尺寸；该记录不证明是无字稿，也不证明第三方为官方来源。",
                    {"file": relative, "sha256": prepare_scenes.digest(path), "historical": True,
                     "url": row.get("url"), "imageSha256": row.get("sha256"), "size": row.get("size")},
                    day="2026-10-15")
        return self.import_observations(state, {"sources": list(observations.values())})

    def report(self, state, kind="all"):
        from art_pipeline_report import build_report
        if kind not in {"all", "official", "fan"}:
            raise ValueError("报告类型只能是 all/official/fan")
        view = state
        if kind != "all":
            view = copy.deepcopy(state)
            view["items"] = [item for item in view["items"] if bool(item.get("official")) == (kind == "official")]
            identities = {item["id"] for item in view["items"]}
            view["sources"] = [source for source in view["sources"]
                               if identities.intersection(source["artworkIds"])
                               or kind == "fan" and source["category"] == "fan-missing"]
            from art_pipeline_analysis import analyze
            view["analysis"] = analyze(view, self.library)
        identity = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
        directory = self.directory / "reports" / identity
        result = build_report(view, self.library, directory)
        records = {p.relative_to(directory).as_posix(): prepare_scenes.digest(p)
                   for p in directory.rglob("*") if p.is_file()}
        marker = {"kind": "art-pipeline-generated-report", "id": identity, "files": records}
        save(directory / "ownership.json", marker)
        state.setdefault("reports", []).append({"id": identity, "path": directory.relative_to(self.directory).as_posix(),
                                               "markerSha256": prepare_scenes.digest(directory / "ownership.json"), "kind": kind, "at": now()})
        return {"reportId": identity, **result}

    def clean_report(self, state, identity):
        if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[a-f0-9]{8}", identity):
            raise ValueError("报告ID格式错误")
        matches = [r for r in state.get("reports", []) if r["id"] == identity and not r.get("archived")]
        report_root = self.directory / "reports"
        requested = report_root / identity
        directory = requested.resolve()
        if (len(matches) != 1 or report_root.is_symlink() or requested.is_symlink()
                or directory.parent != report_root.resolve() or not directory.is_relative_to(self.directory)):
            raise ValueError("只允许清理本流水线登记的生成报告")
        marker_path = directory / "ownership.json"
        if prepare_scenes.digest(marker_path) != matches[0]["markerSha256"]:
            raise ValueError("报告归属记录已变化，拒绝清理")
        marker = read(marker_path)
        files = {p.relative_to(directory).as_posix(): prepare_scenes.digest(p)
                 for p in directory.rglob("*") if p.is_file()}
        if (marker.get("kind") != "art-pipeline-generated-report" or marker.get("id") != identity
                or {k: v for k, v in files.items() if k != "ownership.json"} != marker.get("files")
                or any(p.is_symlink() or not p.resolve().is_relative_to(directory) for p in directory.rglob("*"))):
            raise ValueError("报告包含变化或用户新增内容，保留现场")
        archive = self.directory / "report-archives" / (identity + ".zip")
        archive.parent.mkdir(parents=True, exist_ok=True)
        if archive.exists():
            raise ValueError("已有报告备份，拒绝覆盖")
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as target:
            for relative in files:
                target.write(directory / relative, relative)
        with zipfile.ZipFile(archive) as target:
            if target.testzip() or any(hashlib.sha256(target.read(name)).hexdigest() != value for name, value in files.items()):
                raise ValueError("归档核验失败，保留原报告")
        # The verified directory is a generated report owned by this queue, never an image source.
        if {p.relative_to(directory).as_posix(): prepare_scenes.digest(p) for p in directory.rglob("*") if p.is_file()} != files:
            raise ValueError("归档期间报告已变化，保留原报告")
        shutil.rmtree(directory)
        matches[0].update(archived=True, archive=archive.relative_to(self.directory).as_posix(), archivedAt=now())
        return {"status": "archived", "archive": str(archive)}

    def recover(self, token):
        lock = read(self.lock)
        if not token or lock.get("token") != token:
            raise ValueError("锁token不符，拒绝恢复")
        if process_alive(lock.get("pid")):
            raise ValueError("锁持有进程仍在运行，拒绝恢复")
        # Never remove a lock replaced while its process was being inspected.
        if read(self.lock) != lock:
            raise ValueError("核对期间锁已变化")
        archive = self.directory / "recovery" / (now().replace(":", "-") + "-" + uuid.uuid4().hex + ".json")
        save(archive, {"recoveredLock": lock, "at": now(), "note": "仅释放本队列的死亡进程锁；图片缓存和网站事务保留"})
        self.lock.unlink()
        return {"status": "queue_unlocked", "receipt": str(archive)}


def parser():
    root = argparse.ArgumentParser(description="官方/同人原图工作流：来源、选择、去字结果登记、裁剪、High Fidelity、人工验收")
    root.add_argument("--library", type=Path, default=LIBRARY, help="原始图库；默认本项目 .local/output/adashima-art")
    root.add_argument("--work", type=Path, help="队列目录，必须在图库内")
    root.add_argument("--home", type=Path, default=HOME, help="本机个人网站目录（仅publish使用）")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="创建独立队列；不修改旧图库")
    commands.add_parser("status", help="查看选择、验收和来源覆盖")
    p = commands.add_parser("import-restoration", help="复用既有验收稿，保留暂停与移除状态")
    p.add_argument("--batch", type=Path)
    commands.add_parser("seed-legacy-evidence", help="导入已保存的调查证据，不做新一轮全网搜索")
    p = commands.add_parser("import-observations", help="导入 sources 数组的来源观察记录")
    p.add_argument("--file", type=Path, required=True)
    p = commands.add_parser("source-add", help="登记一个页面/账号的明确调查范围")
    p.add_argument("--url", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--category", default="page")
    p.add_argument("--artwork-id", action="append", default=[])
    p = commands.add_parser("source-note", help="记录具体来源观察；访问受限不等于没有原图")
    p.add_argument("--id", required=True)
    p.add_argument("--status", choices=sources.SOURCE_STATUSES, required=True)
    p.add_argument("--note", required=True)
    p.add_argument("--evidence", action="append", default=[])
    p.add_argument("--checked-at", help="历史观察须填写带时区ISO时间；省略为当前观察时间")
    p = commands.add_parser("add-image", help="加入新候选，默认待选择")
    p.add_argument("--id", required=True)
    p.add_argument("--file", type=Path, required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--artist", default="")
    p.add_argument("--link", default="")
    p.add_argument("--official", action="store_true")
    p = commands.add_parser("set-source", help="登记更好的原图，旧版本保留并使旧验收失效")
    p.add_argument("--id", required=True)
    p.add_argument("--file", type=Path, required=True)
    p.add_argument("--note", required=True)
    p = commands.add_parser("download", help="下载明确图片URL为候选，不自动替换当前原图")
    p.add_argument("--id", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--refresh", action="store_true")
    p = commands.add_parser("plan", help="明确单图处理配方；不自动开始模型处理")
    p.add_argument("--id", required=True)
    p.add_argument("--text", choices=["none", "gpt"], required=True)
    p.add_argument("--prompt-file", type=Path)
    p.add_argument("--mask", type=Path)
    p.add_argument("--crop", nargs=4, type=int, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    p.add_argument("--no-upscale", action="store_true")
    p.add_argument("--note", default="")
    p.add_argument("--box", nargs=4, type=float)
    p.add_argument("--cx", type=float)
    p = commands.add_parser("run", help="串行执行已选配方；只复用成功缓存，失败项显式重试")
    p.add_argument("--id", action="append", default=[])
    p.add_argument("--retry", action="store_true")
    p = commands.add_parser("record-clean", help="登记GPT编辑PNG；未配置自动GPT接口")
    p.add_argument("--id", required=True)
    p.add_argument("--file", type=Path, required=True)
    p.add_argument("--job-key", required=True)
    p = commands.add_parser("apply-decisions", help="导入网页导出的本人选择及验收记录")
    p.add_argument("--file", type=Path, required=True)
    commands.add_parser("analyze", help="提出重复/黑白/低清候选；不替你筛选")
    p = commands.add_parser("report", help="生成可放大详情和导出选择的本机报告")
    p.add_argument("--kind", choices=["all", "official", "fan"], default="all")
    commands.add_parser("publish", help="将当前已选且已验收的集合纳入本机主页背景池")
    p = commands.add_parser("recover", help="核对死亡进程后释放本队列中断锁")
    p.add_argument("--token", required=True)
    p = commands.add_parser("recover-publication", help="按本队列事务日志恢复网站，未知外部变化拒绝覆盖")
    p.add_argument("--journal", type=Path, required=True)
    p = commands.add_parser("clean-report", help="先压缩并核验，再清理本流水线生成的指定报告")
    p.add_argument("--id", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        workspace = Workspace(args.library, args.work, args.home)
        if args.command == "init":
            result = workspace.status(workspace.init())
        elif args.command == "recover":
            result = workspace.recover(args.token)
        elif args.command == "status":
            result = workspace.status(workspace.load())
        else:
            with workspace.edit():
                state = workspace.load()
                if args.command == "import-restoration":
                    result = {"imported": workspace.import_restoration(state, args.batch or workspace.library / "official-restoration-20261015")}
                elif args.command == "seed-legacy-evidence":
                    result = {"observationsImported": workspace.seed_legacy_evidence(state), "networkRequests": 0}
                elif args.command == "import-observations":
                    result = {"observationsImported": workspace.import_observations(state, read(args.file))}
                elif args.command == "source-add":
                    result = workspace.source_add(state, args.url, args.title, args.category, args.artwork_id)
                elif args.command == "source-note":
                    result = workspace.source_note(state, args.id, args.status, args.note, args.evidence, args.checked_at)
                elif args.command == "add-image":
                    result = workspace.add_image(state, args.id, args.title, args.artist, args.file, args.link, args.official)
                elif args.command == "set-source":
                    result = {"status": workspace.set_source(state, args.id, args.file, args.note)}
                elif args.command == "download":
                    result = workspace.download(state, args.id, args.url, args.refresh)
                elif args.command == "plan":
                    workspace.plan(state, args.id, args.text, args.prompt_file.read_text(encoding="utf-8") if args.prompt_file else "",
                                   args.mask, args.crop, not args.no_upscale, args.note, args.box, args.cx)
                    result = {"status": "planned", "id": args.id}
                elif args.command == "run":
                    result = workspace.run(state, args.id, args.retry)
                elif args.command == "record-clean":
                    workspace.record_clean(state, args.id, args.file, args.job_key)
                    result = {"status": "clean_recorded", "id": args.id}
                elif args.command == "apply-decisions":
                    workspace.apply_decisions(state, read(args.file))
                    result = workspace.status(state)
                elif args.command == "analyze":
                    from art_pipeline_analysis import analyze
                    state["analysis"] = analyze(state, workspace.library)
                    save(workspace.directory / "analysis.json", state["analysis"])
                    result = {"analysis": str(workspace.directory / "analysis.json"),
                              **{key: len(value) for key, value in state["analysis"].items() if isinstance(value, list)}}
                elif args.command == "report":
                    result = workspace.report(state, args.kind)
                elif args.command == "clean-report":
                    result = workspace.clean_report(state, args.id)
                elif args.command == "publish":
                    from art_pipeline_publish import publish
                    result = publish(workspace, state)
                elif args.command == "recover-publication":
                    from art_pipeline_publish import recover
                    result = recover(workspace, args.journal)
                else:
                    raise ValueError("不支持的命令")
                workspace.write(state)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 1 if args.command == "run" and result.get("failed") else 0
    except KeyboardInterrupt:
        print("已中断；原稿及已完成结果保留，可重新 run。", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        print(f"流水线停止，保留已有图片和正式背景: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

