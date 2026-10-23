"""Transactional formal-site switch: pool, approved scenes, time tags, and assets together."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from . import state as state_module

import build_assets
import prepare_scenes


KIND = "image-workbench-publication"


@dataclass
class Workspace:
    root: Path = state_module.ROOT
    library: Path = state_module.LIBRARY
    site: Path = state_module.ROOT / "site"

    @classmethod
    def default(cls):
        return cls()


class PublicationError(RuntimeError):
    def __init__(self, message, token=None, recovery_required=False):
        super().__init__(message)
        self.token = token
        self.recovery_required = recovery_required


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def _file(path):
    path = Path(path)
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"预期普通文件: {path}")
    return {"sha256": prepare_scenes.digest(path), "bytes": path.stat().st_size}


def _tree(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"素材目录越界: {path}")
    if not path.exists():
        return None
    if not path.is_dir():
        raise ValueError(f"预期素材目录: {path}")
    entries = []
    for child in sorted(path.rglob("*")):
        child = child.resolve()
        if not child.is_relative_to(root):
            raise ValueError(f"素材目录成员越界: {child}")
        if child.is_file():
            entries.append({"path": child.relative_to(path).as_posix(), "type": "file",
                            **_file(child)})
        elif child.is_dir():
            entries.append({"path": child.relative_to(path).as_posix(), "type": "directory"})
        else:
            raise ValueError(f"不支持的素材成员: {child}")
    return {"fingerprint": _hash(entries), "files": entries}


def _paths(workspace):
    if isinstance(workspace, dict):
        library = Path(workspace["library"]).resolve()
        site = Path(workspace["site"]).resolve()
    else:
        library = Path(workspace.library).resolve()
        site = Path(workspace.site).resolve()
    return {
        "library": library,
        "site": site,
        "pool": site / "config" / "pool.txt",
        "approved": library / "scenes-approved.json",
        "tags": site / "config" / "time-tags.txt",
        "assets": site / "assets",
        "publications": library / "publications",
        "assetLock": site / ".assets-build.lock",
    }


def snapshot(workspace):
    paths = _paths(workspace)
    return {"pool": _file(paths["pool"]), "approved": _file(paths["approved"]),
            "tags": _file(paths["tags"]), "assets": _tree(paths["assets"], paths["site"])}


def _write_pending(folder, scenes):
    approved = {"schemaVersion": 1, "scenes": scenes}
    (folder / "pending-approved.json").write_text(
        json.dumps(approved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (folder / "pending-pool.txt").write_text(
        "\n".join(scene["id"] for scene in scenes) + "\n", encoding="utf-8")
    labels = {"day": "白天", "dusk": "黄昏", "night": "夜晚"}
    tags = [f"{scene['id']}\t{labels[scene['time']]}" for scene in scenes
            if scene.get("time") in labels]
    (folder / "pending-time-tags.txt").write_text(
        "# 发布时的时段标签\n" + "\n".join(tags) + ("\n" if tags else ""), encoding="utf-8")
    return approved


def _replace_copy(source, destination):
    source, destination = Path(source), Path(destination)
    temporary = destination.with_name(destination.name + ".publication-" + uuid.uuid4().hex)
    try:
        with source.open("rb") as reader, temporary.open("xb") as writer:
            shutil.copyfileobj(reader, writer)
        if _file(source) != _file(temporary):
            raise ValueError("发布元数据复制校验失败")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _rename(source, destination):
    source, destination = Path(source), Path(destination)
    if os.path.lexists(destination):
        raise FileExistsError(f"切换目标意外出现，不覆盖: {destination}")
    source.rename(destination)


def _write_journal(folder, journal):
    (Path(folder) / "journal.json").write_text(
        json.dumps(journal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@contextmanager
def _asset_lock(paths, text=None):
    lock = paths["assetLock"]
    text = text or f"pid={os.getpid()} operation={KIND} token={uuid.uuid4().hex}\n"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise PublicationError(f"已有素材构建或待核对中断现场: {lock}") from error
    try:
        with handle:
            handle.write(text)
        yield text
    finally:
        if lock.read_text(encoding="utf-8") != text:
            raise PublicationError(f"素材共享锁已变化，请保留现场: {lock}", recovery_required=True)
        lock.unlink()


def build_staged(workspace, token, scenes):
    paths = _paths(workspace)
    folder = paths["publications"] / token
    folder.mkdir(parents=True, exist_ok=False)
    _write_pending(folder, scenes)
    build_assets.rebuild(
        library=paths["library"],
        assets=folder / "prepared-assets",
        pool_path=folder / "pending-pool.txt",
        approved_path=Path("publications") / token / "pending-approved.json",
        tags_path=folder / "pending-time-tags.txt",
        sky_builder=build_assets.existing_sky_builder(paths["assets"]))
    desired = {
        "pool": _file(folder / "pending-pool.txt"),
        "approved": _file(folder / "pending-approved.json"),
        "tags": _file(folder / "pending-time-tags.txt"),
        "assets": _tree(folder / "prepared-assets", folder),
    }
    journal = {
        "schemaVersion": 1,
        "kind": KIND,
        "token": token,
        "workspace": {"library": str(paths["library"]), "site": str(paths["site"])},
        "baseline": snapshot(workspace),
        "desired": desired,
        "phase": "prepared",
        "events": [{"phase": "prepared", "at": state_module.now()}],
    }
    _write_journal(folder, journal)
    return folder, journal


def _rollback(paths, folder, journal):
    baseline = journal["baseline"]
    desired = journal["desired"]
    current = snapshot({"library": paths["library"], "site": paths["site"]})
    # Only restore objects that still belong to this transaction. Anything else is an
    # outside edit and must be left for a human to inspect.
    for key in ("pool", "approved", "tags"):
        if current[key] not in (baseline[key], desired[key]):
            raise PublicationError(f"恢复拒绝覆盖外来变化: {key}", journal["token"], True)
    if current["assets"] not in (baseline["assets"], desired["assets"], None):
        raise PublicationError("恢复拒绝覆盖外来素材变化", journal["token"], True)
    if (folder / "previous-assets").exists():
        backup = _tree(folder / "previous-assets", folder)
        if backup != baseline["assets"]:
            raise PublicationError("旧素材副本已经变化，拒绝恢复", journal["token"], True)
    if current["assets"] != baseline["assets"]:
        if paths["assets"].exists():
            interrupted = folder / ("interrupted-assets-" + uuid.uuid4().hex)
            _rename(paths["assets"], interrupted)
        if (folder / "previous-assets").exists():
            _rename(folder / "previous-assets", paths["assets"])
    for key in ("pool", "approved", "tags"):
        if current[key] == baseline[key]:
            continue
        if baseline[key] is None:
            if paths[key].exists():
                paths[key].unlink()
        else:
            _replace_copy(folder / f"previous-{key}", paths[key])
    if snapshot({"library": paths["library"], "site": paths["site"]}) != baseline:
        raise PublicationError("恢复后的站点与旧基线不一致", journal["token"], True)
    journal["phase"] = "rolled_back"
    journal.setdefault("events", []).append({"phase": "rolled_back", "at": state_module.now()})
    _write_journal(folder, journal)


def _apply_state(store, journal):
    """Idempotently mirror a completed file transaction into workbench state."""
    intent = journal.get("stateIntent") or {}
    scenes = intent.get("scenes") or []
    item_ids = intent.get("itemIds") or []
    draft_id = intent.get("draftId")
    token = journal["token"]

    def apply(state):
        for item_id in item_ids:
            item = state_module.find_item(state, item_id)
            item["enabledId"] = next(
                (scene["id"] for scene in scenes
                 if scene.get("sourceItemId") == item_id), None)
            if item["status"] != state_module.ENABLED:
                state_module.transition(item, state_module.ENABLED, "启用到正式主页")
        if (state["enabled"]["items"] != scenes
                or not state["enabled"].get("migratedAt")):
            state["enabled"]["items"] = scenes
            state["enabled"]["migratedAt"] = state_module.now()
        existing = next((entry for entry in state["publications"]
                         if entry.get("token") == token), None)
        record = {"token": token, "at": (existing or {}).get("at") or state_module.now(),
                  "count": len(scenes), "itemIds": list(item_ids)}
        publications = []
        replaced = False
        for entry in state["publications"]:
            if entry.get("token") == token:
                if not replaced:
                    publications.append(record)
                    replaced = True
                continue
            publications.append(entry)
        if not replaced:
            publications.append(record)
        state["publications"] = publications
        if draft_id:
            try:
                draft = state_module.find_draft(state, draft_id)
            except ValueError:
                draft = None
            if draft is not None:
                remaining = [entry for entry in draft.get("items", [])
                             if entry["itemId"] not in item_ids]
                scene_ids = [scene["id"] for scene in scenes]
                scene_ids += [entry["sceneId"] for entry in remaining
                              if entry["sceneId"] not in scene_ids]
                status = "ready" if remaining else "enabled"
                fields = {
                    "status": status, "items": remaining, "sceneIds": scene_ids,
                    "addedCount": len(remaining), "baselineCount": len(scenes),
                    "sceneCount": len(scene_ids),
                }
                if any(draft.get(key) != value for key, value in fields.items()):
                    fields["updatedAt"] = state_module.now()
                    if status == "enabled":
                        fields["enabledAt"] = state_module.now()
                    draft.update(fields)
        return {"status": "published", "token": token, "count": len(scenes)}

    return store.mutate(apply)


def _repair_draft_assets(store, journal, workspace):
    intent = journal.get("stateIntent") or {}
    draft_id = intent.get("draftId")
    if not draft_id:
        return None
    try:
        from . import drafts
        state = store.read()
        if not any(draft.get("draftId") == draft_id for draft in state["drafts"]):
            return None
        paths = _paths(workspace)
        return drafts.reduce_after_enable(
            store, draft_id, intent.get("itemIds") or [],
            library=paths["library"], site=paths["site"])
    except (ValueError, OSError) as error:
        return {"warning": str(error)}


def publish_scenes(store, scenes, item_ids=None, name="工作台启用", workspace=None, draft_id=None):
    """Switch the formal site in one recoverable transaction."""
    workspace = workspace or Workspace.default()
    paths = _paths(workspace)
    token = uuid.uuid4().hex
    baseline = snapshot(workspace)
    if baseline["assets"] is None:
        raise PublicationError("缺少可复用的既有天空素材；请先建立站点基线")
    folder, journal = build_staged(workspace, token, scenes)
    journal["stateIntent"] = {
        "scenes": scenes,
        "itemIds": list(item_ids or []),
        "draftId": draft_id,
        "name": name,
    }
    _write_journal(folder, journal)
    if snapshot(workspace) != baseline:
        raise PublicationError(f"生成期间正式站点发生变化，未切换；现场: {folder}", token)
    for key in ("pool", "approved", "tags"):
        if baseline[key] is not None:
            shutil.copyfile(paths[key], folder / f"previous-{key}")
            if _file(folder / f"previous-{key}") != baseline[key]:
                raise PublicationError(f"生成期间正式元数据发生变化，未切换；现场: {folder}", token)
    asset_text = json.dumps({"pid": os.getpid(), "token": token, "operation": KIND}) + "\n"
    journal["assetLockText"] = asset_text
    _write_journal(folder, journal)
    try:
        with _asset_lock(paths, asset_text):
            if snapshot(workspace) != baseline:
                raise PublicationError(f"切换前正式站点再次变化，未切换；现场: {folder}", token)
            _rename(paths["assets"], folder / "previous-assets")
            journal["phase"] = "old_assets_saved"
            _write_journal(folder, journal)
            _rename(folder / "prepared-assets", paths["assets"])
            journal["phase"] = "assets_installed"
            _write_journal(folder, journal)
            _replace_copy(folder / "pending-approved.json", paths["approved"])
            journal["phase"] = "approved_installed"
            _write_journal(folder, journal)
            _replace_copy(folder / "pending-pool.txt", paths["pool"])
            journal["phase"] = "pool_installed"
            _write_journal(folder, journal)
            _replace_copy(folder / "pending-time-tags.txt", paths["tags"])
            journal["phase"] = "tags_installed"
            _write_journal(folder, journal)
            if snapshot(workspace) != journal["desired"]:
                raise ValueError("发布后的站点与已生成结果不一致")
            journal["phase"] = "completed"
            journal.setdefault("events", []).append({"phase": "completed", "at": state_module.now()})
            _write_journal(folder, journal)
    except BaseException as error:
        try:
            _rollback(paths, folder, journal)
        except BaseException as restore_error:
            raise PublicationError(
                f"发布及恢复未完成，副本全部保留；现场: {folder}；恢复错误: {restore_error}",
                token, True) from error
        raise PublicationError(f"发布失败，已恢复旧站点: {error}；现场: {folder}", token) from error

    try:
        return _apply_state(store, journal)
    except BaseException as error:
        raise PublicationError(
            f"正式站点已切换，但工作台状态保存失败；执行恢复可补齐状态。现场: {folder}",
            token, True) from error


def recover(store, token, workspace=None):
    workspace = workspace or Workspace.default()
    paths = _paths(workspace)
    folder = paths["publications"] / token
    journal_path = folder / "journal.json"
    if not journal_path.is_file():
        raise ValueError(f"找不到发布记录: {journal_path}")
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    if (journal.get("schemaVersion") != 1 or journal.get("kind") != KIND
            or journal.get("token") != token
            or journal.get("workspace") != {"library": str(paths["library"]),
                                            "site": str(paths["site"])}):
        raise ValueError("发布记录不属于当前工作目录")
    if journal["phase"] == "completed":
        if snapshot(workspace) != journal["desired"]:
            raise ValueError("已完成发布之后站点发生变化，不用旧记录覆盖")
        lock = paths["assetLock"]
        if lock.exists():
            if lock.read_text(encoding="utf-8") != journal.get("assetLockText"):
                raise PublicationError("发布锁不属于这条记录，拒绝删除", token, True)
            lock.unlink()
        if not journal.get("stateIntent"):
            return {"status": "published", "token": token,
                    "warning": "发布记录缺少 stateIntent，未修复工作台状态"}
        try:
            result = _apply_state(store, journal)
        except BaseException as error:
            raise PublicationError(
                f"正式站点已完成，但工作台状态仍未补齐；现场: {folder}",
                token, True) from error
        repaired = _repair_draft_assets(store, journal, workspace)
        if isinstance(repaired, dict) and repaired.get("warning"):
            result["warning"] = repaired["warning"]
        return result
    current = snapshot(workspace)
    for key in ("pool", "approved", "tags"):
        if current[key] not in (journal["baseline"][key], journal["desired"][key]):
            raise PublicationError(f"恢复拒绝覆盖外来变化: {key}", token, True)
    if current["assets"] not in (journal["baseline"]["assets"], journal["desired"]["assets"], None):
        raise PublicationError("恢复拒绝覆盖外来素材变化", token, True)
    lock = paths["assetLock"]
    if lock.exists():
        if lock.read_text(encoding="utf-8") != journal.get("assetLockText"):
            raise PublicationError("发布锁不属于这条记录，拒绝恢复", token, True)
        lock.unlink()
    asset_text = json.dumps({"pid": os.getpid(), "token": token, "operation": KIND}) + "\n"
    journal["assetLockText"] = asset_text
    _write_journal(folder, journal)
    try:
        with _asset_lock(paths, asset_text):
            _rollback(paths, folder, journal)
    except PublicationError:
        raise
    except BaseException as error:
        raise PublicationError(f"恢复未完成，保留现场: {folder}；{error}", token, True) from error
    return {"status": "rolled_back", "token": token}
