"""AI task packages, workspace instructions, and receipt-checked results."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

from PIL import Image

from . import state as state_module
from .library import digest
from .processing import ProcessingError, ensure_version, open_image, base_record


TASK_STATUSES = ("waiting", "confirmed", "done", "rejected", "late", "conflict", "superseded")


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part-" + uuid.uuid4().hex)
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def instruction_text(task, job):
    root = Path(job.get("root") or state_module.ROOT).resolve()
    directory = Path(job.get("taskDir") or (root / job["taskPath"])).resolve()
    input_path = directory / job["input"]["path"]
    return f"""# AI 图片处理任务

- 仓库绝对路径：`{root}`
- 任务 ID：`{task['taskId']}`
- 图片：`{task['itemId']}`
- 操作：去除画面中的文字，保留画师签名
- 输入：`{input_path}`
- 输出：`{directory / 'output' / 'result.png'}`
- 回执：`{directory / 'output' / 'receipt.json'}`

## 要求

1. 只读取本任务的 `input/source.*` 和本说明；不要读取或改写图库其他文件。
2. 只写入本任务的 `output/result.png` 和 `output/receipt.json`。
3. 保持输入尺寸、构图、人物、线条和画师签名不变；不得生成新构图或扩大画布。
4. 输出必须是真实 PNG，尺寸与输入完全一致。
5. `receipt.json` 必须包含 `schemaVersion`（1）、`taskId`、`inputSha256`、`outputSha256`、`size`、`format`、`summary`、`completedAt`。
6. 不得直接修改 `site/config/pool.txt`、`scenes-approved.json`、`site/config/time-tags.txt`、`site/assets` 或图库其他内容。
7. 如果画面里其实没有文字，或只剩画师签名，请在 `summary` 里说明，并保持原图像素不变；不要改签名。
8. 可选：在回执里用 `textFound`（布尔）、`signatureFound`（布尔）、`timeSuggestion`（day／dusk／night／any）记录你的判断。

完成后不需要运行其他命令；在图片工作台刷新页面或点“刷新检查”即可。
"""


def create_task(store, library, item_id, confidence=1.0, needs_confirmation=False, root=None):
    library = Path(library).resolve()
    root = Path(root or state_module.ROOT).resolve()
    current = state_module.find_item(store.read(), item_id)
    base = base_record(current)
    source = library / base["path"]
    if not source.is_file():
        raise ValueError(f"AI 任务输入不存在: {base['path']}")
    task_id = "task-" + uuid.uuid4().hex[:12]
    task_dir = library / "ai-jobs" / task_id
    input_dir = task_dir / "input"
    output_dir = task_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=False)
    output_dir.mkdir(parents=True, exist_ok=False)
    extension = Path(base["path"]).suffix.lower() or ".png"
    input_relative = f"input/source{extension}"
    shutil.copyfile(source, task_dir / input_relative)
    if digest(task_dir / input_relative) != base["sha256"]:
        raise ValueError("AI 任务输入复制校验失败")
    version = int(current.get("planRevision") or 0) + 1
    analysis = current.get("analysis") or {}
    job = {
        "schemaVersion": 1,
        "taskId": task_id,
        "itemId": item_id,
        "operation": "remove-text",
        "version": version,
        "createdAt": state_module.now(),
        "taskPath": f"ai-jobs/{task_id}",
        "taskDir": str(task_dir.resolve()),
        "root": str(root),
        "input": {
            "path": input_relative,
            "sha256": base["sha256"],
            "size": list(base["size"]),
            "format": (current.get("original") or {}).get("format") or "PNG",
        },
        "analysis": {
            "text": analysis.get("text"),
            "time": analysis.get("time"),
            "borders": analysis.get("borders"),
            "uncertainties": analysis.get("uncertainties") or [],
        },
        "constraints": {
            "sameSize": True,
            "sameComposition": True,
            "preserveCharacters": True,
            "preserveSignature": True,
            "allowedChanges": ["remove text"],
        },
        "expected": {"result": "output/result.png", "receipt": "output/receipt.json"},
        "confidence": round(float(confidence), 3),
        "needsConfirmation": bool(needs_confirmation),
    }
    _write_json(task_dir / "job.json", job)
    (task_dir / "instruction.md").write_text(instruction_text(
        {"taskId": task_id, "itemId": item_id}, job), encoding="utf-8")
    task = {
        "taskId": task_id,
        "itemId": item_id,
        "version": version,
        "operation": "remove-text",
        "status": "waiting",
        "confidence": job["confidence"],
        "needsConfirmation": bool(needs_confirmation),
        "createdAt": job["createdAt"],
        "jobPath": f"ai-jobs/{task_id}",
        "input": job["input"],
        "resultSha256": None,
        "resultPath": None,
        "completedAt": None,
        "error": None,
        "note": None,
        "rejectedFingerprint": None,
        "attempts": [],
    }

    def add(state):
        target = state_module.find_item(state, item_id)
        target["planRevision"] = version
        target["aiTaskId"] = task_id
        target["pendingConfirmation"] = bool(needs_confirmation)
        state_module.transition(target, state_module.WAITING_AI, "生成 AI 去字任务")
        state["aiTasks"].append(task)
        return task

    return store.mutate(add)


def confirm_task(store, task_id):
    def confirm(state):
        task = state_module.find_task(state, task_id)
        if task["status"] != "waiting":
            raise ValueError(f"任务当前状态不能确认: {task['status']}")
        item = state_module.find_item(state, task["itemId"])
        task["needsConfirmation"] = False
        item["pendingConfirmation"] = False
        item["history"].append({"status": item["status"], "at": state_module.now(),
                                 "note": "用户确认低置信去字任务"})
        return task

    return store.mutate(confirm)


def recreate_task(store, library, task_id, root=None):
    old = state_module.find_task(store.read(), task_id)
    item = state_module.find_item(store.read(), old["itemId"])

    def supersede(state):
        task = state_module.find_task(state, task_id)
        task["status"] = "superseded"
        task["supersededAt"] = state_module.now()
        target = state_module.find_item(state, task["itemId"])
        target["aiTaskId"] = None
        target["pendingConfirmation"] = False
        return target

    store.mutate(supersede)
    return create_task(store, library, item["id"], confidence=old.get("confidence", 0.5),
                       needs_confirmation=old.get("needsConfirmation", False), root=root)


def _receipt_error(receipt, job, result, result_hash):
    if not isinstance(receipt, dict):
        return "回执必须是 JSON 对象"
    if receipt.get("schemaVersion") != 1:
        return "回执 schemaVersion 必须为 1"
    if receipt.get("taskId") != job["taskId"]:
        return "回执 taskId 与任务不一致"
    if receipt.get("inputSha256") != job["input"]["sha256"]:
        return "回执输入 SHA-256 与任务不一致"
    if receipt.get("outputSha256") != result_hash:
        return "回执输出 SHA-256 与结果文件不一致"
    if receipt.get("size") != job["input"]["size"]:
        return f"回执尺寸与输入不一致: {receipt.get('size')}"
    if str(receipt.get("format", "")).upper() != "PNG":
        return "回执格式必须为 PNG"
    if not isinstance(receipt.get("summary"), str) or not receipt["summary"].strip():
        return "回执缺少处理摘要"
    if not isinstance(receipt.get("completedAt"), str) or not receipt["completedAt"].strip():
        return "回执缺少完成时间"
    if "textFound" in receipt and not isinstance(receipt["textFound"], bool):
        return "回执 textFound 必须为布尔值"
    if "signatureFound" in receipt and not isinstance(receipt["signatureFound"], bool):
        return "回执 signatureFound 必须为布尔值"
    if "timeSuggestion" in receipt and receipt["timeSuggestion"] not in ("day", "dusk", "night", "any"):
        return "回执 timeSuggestion 只能是 day、dusk、night 或 any"
    return None


def validate_result(store, library, task, item):
    """Return ('done'|'rejected'|'late'|'conflict'|'waiting', error, receipt)."""
    library = Path(library).resolve()
    task_dir = library / task["jobPath"]
    result = task_dir / "output" / "result.png"
    receipt_path = task_dir / "output" / "receipt.json"
    if not result.exists() and not receipt_path.exists():
        return "waiting", None, None
    if not result.exists() or not receipt_path.exists():
        return "waiting", None, None
    if item.get("aiTaskId") != task["taskId"] or int(item.get("planRevision") or 0) != int(task["version"]):
        return "late", "任务已被重新规划；迟到结果保留在任务目录，不自动接入。", None
    if task.get("resultSha256"):
        if digest(result) == task["resultSha256"]:
            return "done", None, None
        return "conflict", "同一任务已登记另一份不同结果；请重新生成任务。", None
    try:
        job = json.loads((task_dir / "job.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return "rejected", f"任务 job.json 无法读取: {error}", None
    if job.get("taskId") != task["taskId"] or job.get("input", {}).get("sha256") != task["input"]["sha256"]:
        return "rejected", "任务包身份或输入哈希与状态不一致；请重新生成任务。", None
    if digest(task_dir / task["input"]["path"]) != job["input"]["sha256"]:
        return "rejected", "任务输入文件已变化；请重新生成任务。", None
    try:
        with Image.open(result) as image:
            if image.format != "PNG":
                return "rejected", "结果文件不是实际 PNG", None
            image.verify()
        with Image.open(result) as image:
            image.load()
            size = list(image.size)
    except Exception as error:
        return "rejected", f"结果无法完整解码: {error}", None
    if size != job["input"]["size"]:
        return "rejected", f"结果尺寸 {size} 与输入 {job['input']['size']} 不一致；去字不得改变尺寸。", None
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return "rejected", f"回执无法读取: {error}", None
    result_hash = digest(result)
    error = _receipt_error(receipt, job, result, result_hash)
    if error:
        return "rejected", error, None
    return "done", None, receipt


def _fingerprint(task_dir):
    parts = []
    for name in ("result.png", "receipt.json"):
        path = Path(task_dir) / "output" / name
        try:
            stat = path.stat()
            parts.append(f"{name}:{stat.st_size}:{stat.st_mtime_ns}")
        except OSError:
            parts.append(f"{name}:missing")
    return "|".join(parts)


def scan_tasks(store, library):
    """Check task output folders; attach only validated results, never the formal site."""
    library = Path(library).resolve()
    changed = []
    for task in store.read()["aiTasks"]:
        if task["status"] not in ("waiting", "rejected"):
            continue
        task_dir = library / task["jobPath"]
        fingerprint = _fingerprint(task_dir)
        if task["status"] == "rejected" and task.get("rejectedFingerprint") == fingerprint:
            continue
        item = state_module.find_item(store.read(), task["itemId"])
        status, error, receipt = validate_result(store, library, task, item)
        if status == "waiting":
            if task["status"] == "rejected":
                def wait_again(state):
                    target = state_module.find_task(state, task["taskId"])
                    target["status"] = "waiting"
                    target["error"] = None
                    target["note"] = "等待结果和回执同时写入"
                    return state_module.task_summary(target)

                store.mutate(wait_again)
            continue
        version = None
        if status == "done":
            result = task_dir / "output" / "result.png"
            with Image.open(result) as image:
                image.load()
                version = ensure_version(
                    store, library, item["id"], "ai-clean", image,
                    {"path": task["input"]["path"], "sha256": task["input"]["sha256"],
                     "size": task["input"]["size"], "versionId": None},
                    {"taskId": task["taskId"], "version": task["version"]},
                    "ai-remove-text",
                    evidence={"receipt": f"{task['jobPath']}/output/receipt.json"})

        def apply(state):
            target_task = state_module.find_task(state, task["taskId"])
            target_item = state_module.find_item(state, target_task["itemId"])
            if status == "done":
                result = library / target_task["jobPath"] / "output" / "result.png"
                target_task["status"] = "done"
                target_task["resultSha256"] = digest(result)
                target_task["resultPath"] = result.relative_to(library).as_posix()
                target_task["completedAt"] = state_module.now()
                target_task["error"] = None
                target_task["note"] = None
                target_task["rejectedFingerprint"] = None
                target_item["aiTaskId"] = target_task["taskId"]
                target_item["pendingConfirmation"] = False
                target_item["error"] = None
                if receipt and target_item.get("timeChoice") in (None, "auto"):
                    suggestion = receipt.get("timeSuggestion")
                    if suggestion in ("day", "dusk", "night"):
                        target_item["time"] = suggestion
                        target_item["timeChoice"] = "auto"
                        target_item["timeSuggestion"] = {
                            "suggestion": suggestion, "confidence": 0.9,
                            "reason": "AI 回执建议",
                        }
                    elif suggestion == "any":
                        target_item["time"] = None
                        target_item["timeChoice"] = "auto"
                state_module.transition(target_item, state_module.PROCESSING_LOCAL, "AI 回传校验通过")
                return {"itemId": target_item["id"], "taskId": target_task["taskId"],
                        "status": "done", "versionId": version["versionId"]}
            target_task["status"] = status
            target_task["error"] = error
            target_task["note"] = error
            target_task["rejectedFingerprint"] = fingerprint
            target_task["attempts"] = target_task.get("attempts", [])
            target_task["attempts"].append({"at": state_module.now(), "status": status, "error": error})
            target_item["error"] = {"step": "ai", "message": error, "at": state_module.now()}
            return {"itemId": target_item["id"], "taskId": target_task["taskId"],
                    "status": status, "error": error}

        changed.append(store.mutate(apply))
    return changed


def task_instruction(store, task_id):
    task = state_module.find_task(store.read(), task_id)
    path = store.root / task["jobPath"] / "instruction.md"
    if not path.is_file():
        raise ValueError(f"任务说明不存在: {path}")
    return path.read_text(encoding="utf-8")
