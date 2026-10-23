"""Draft scenes, isolated draft assets, and the 54-picture read-only baseline."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import uuid
from pathlib import Path

from . import state as state_module
from .library import digest
from .processing import latest_version

import build_assets
import prepare_scenes


SITE = state_module.ROOT / "site"
DRAFT_SCHEMA = 1


def _scene_id(item, existing):
    base = "scene-" + item["original"]["sha256"][:16]
    candidate = base
    index = 2
    while candidate in existing:
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _review(scene):
    content = {key: value for key, value in scene.items() if key != "review"}
    return {
        "status": "approved",
        "reviewer": "user",
        "note": "用户在工作台采用",
        "contentSha256": hashlib.sha256(
            json.dumps(content, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
        "at": state_module.now(),
    }


def _valid_scene(scene):
    return (isinstance(scene, dict) and isinstance(scene.get("id"), str)
            and isinstance(scene.get("master"), dict)
            and isinstance(scene["master"].get("path"), str)
            and isinstance(scene["master"].get("sha256"), str)
            and isinstance(scene["master"].get("size"), list)
            and isinstance(scene.get("box"), list) and len(scene["box"]) == 4
            and isinstance(scene.get("cx"), (int, float)))


def scene_from_item(item, version, existing_ids):
    choice = item.get("timeChoice")
    if choice in ("day", "dusk", "night"):
        time = choice
    elif choice == "any":
        time = None
    else:
        time = item.get("time") or (item.get("timeSuggestion") or {}).get("suggestion")
        if time not in ("day", "dusk", "night"):
            time = None
    scene = {
        "id": _scene_id(item, existing_ids),
        "title": Path(item.get("filename") or item["id"]).stem[:60] or item["id"],
        "artist": "",
        "official": None,
        "link": "",
        "focusMode": "whole-artwork",
        "adoptedVersion": version["step"],
        "master": {"path": version["path"], "sha256": version["sha256"],
                   "size": list(version["size"])},
        "box": [0.0, 0.0, 1.0, 1.0],
        "cx": 0.5,
        "sourceName": item.get("filename") or "",
        "sourceItemId": item["id"],
    }
    if time:
        scene["time"] = time
    scene["review"] = _review(scene)
    return scene


def baseline_scenes(state):
    return [copy.deepcopy(scene) for scene in state["enabled"]["items"]]


def _write_draft_files(draft_dir, scenes):
    approved = {"schemaVersion": 1, "scenes": scenes}
    (draft_dir / "approved.json").write_text(
        json.dumps(approved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (draft_dir / "pool.txt").write_text(
        "\n".join(scene["id"] for scene in scenes) + "\n", encoding="utf-8")
    labels = {"day": "白天", "dusk": "黄昏", "night": "夜晚"}
    tags = [f"{scene['id']}\t{labels[scene['time']]}" for scene in scenes
            if scene.get("time") in labels]
    (draft_dir / "time-tags.txt").write_text(
        "# 草稿时段标签\n" + "\n".join(tags) + ("\n" if tags else ""), encoding="utf-8")
    return approved


def build_draft_assets(draft_dir, scenes, library=None, site=None):
    draft_dir = Path(draft_dir)
    library = Path(library or state_module.LIBRARY).resolve()
    site = Path(site or state_module.ROOT / "site").resolve()
    _write_draft_files(draft_dir, scenes)
    assets = draft_dir / "assets"
    build_assets.rebuild(
        library=library,
        assets=assets,
        pool_path=draft_dir / "pool.txt",
        approved_path=draft_dir.resolve().relative_to(library) / "approved.json",
        tags_path=draft_dir / "time-tags.txt",
        sky_builder=build_assets.existing_sky_builder(site / "assets"))
    return json.loads((assets / "manifest.json").read_text(encoding="utf-8"))


def verify_manifest(draft_dir, expected_scenes, formal_manifest=None):
    manifest = json.loads((Path(draft_dir) / "assets" / "manifest.json").read_text(encoding="utf-8"))
    rendered = manifest.get("scenes") or []
    if len(rendered) != len(expected_scenes):
        raise ValueError(f"草稿 manifest 数量 {len(rendered)} 与预期 {len(expected_scenes)} 不一致")
    for scene, item in zip(rendered, expected_scenes):
        if scene.get("masterSha256") != item["master"]["sha256"]:
            raise ValueError(f"草稿 manifest 母版哈希不一致: {item.get('id')}")
        if [scene.get("w"), scene.get("h")] != list(item["master"]["size"]):
            raise ValueError(f"草稿 manifest 尺寸不一致: {item.get('id')}")
        for key in ("id", "box", "cx", "focusMode"):
            if scene.get(key) != item.get(key):
                raise ValueError(f"草稿 manifest 字段不一致: {item.get('id')} / {key}")
        if scene.get("time") != item.get("time"):
            raise ValueError(f"草稿 manifest 时段不一致: {item.get('id')}")
        if any(scene.get(key) != item.get(key) for key in ("title", "artist", "official", "link")):
            raise ValueError(f"草稿 manifest 资料字段不一致: {item.get('id')}")
    if formal_manifest is not None:
        formal = formal_manifest.get("scenes") or []
        if [scene.get("id") for scene in rendered] != [scene.get("id") for scene in formal]:
            raise ValueError("草稿 ID 顺序与正式主页不一致")
        for scene, official in zip(rendered, formal):
            if any(scene.get(key) != official.get(key) for key in
                   ("masterSha256", "w", "h", "box", "cx", "time", "title", "artist", "official", "link")):
                raise ValueError(f"草稿场景与正式主页不一致: {scene.get('id')}")
    return manifest


def create_draft(store, name, item_ids, library=None, site=None):
    library = Path(library or state_module.LIBRARY).resolve()
    site = Path(site or state_module.ROOT / "site").resolve()
    state = store.read()
    selected = [state_module.find_item(state, item_id) for item_id in item_ids]
    if not selected:
        raise ValueError("草稿至少需要一张已采用图片")
    for item in selected:
        if item["status"] != state_module.ADOPTED:
            raise ValueError(f"{item['id']} 尚未采用，不能入库")
        if not item.get("adoptedVersion"):
            raise ValueError(f"{item['id']} 缺少采用版本")
    draft_id = "draft-" + state_module.now().replace(":", "").replace("-", "")[:15] + "-" + uuid.uuid4().hex[:6]
    draft_dir = library / "drafts" / draft_id
    draft_dir.mkdir(parents=True, exist_ok=False)
    scenes = baseline_scenes(state)
    existing = {scene["id"] for scene in scenes}
    masters = {scene["master"]["sha256"] for scene in scenes}
    items = []
    for item in selected:
        version = next((entry for entry in item["versions"]
                        if entry["versionId"] == item["adoptedVersion"]), None)
        if version is None:
            raise ValueError(f"{item['id']} 的采用版本不存在")
        if version["sha256"] in masters:
            raise ValueError(f"{item['id']} 与已启用图片内容相同")
        scene = scene_from_item(item, version, existing)
        existing.add(scene["id"])
        masters.add(version["sha256"])
        scenes.append(scene)
        items.append({"itemId": item["id"], "sceneId": scene["id"], "versionId": version["versionId"]})
    manifest = build_draft_assets(draft_dir, scenes, library=library, site=site)
    metadata = {
        "schemaVersion": DRAFT_SCHEMA,
        "draftId": draft_id,
        "name": name or "未命名草稿",
        "createdAt": state_module.now(),
        "status": "ready",
        "sceneCount": len(scenes),
        "baselineCount": len(state["enabled"]["items"]),
        "addedCount": len(items),
        "items": items,
        "sceneIds": [scene["id"] for scene in scenes],
        "manifestScenes": len(manifest.get("scenes") or []),
    }
    (draft_dir / "draft.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def add(state):
        for item in selected:
            target = state_module.find_item(state, item["id"])
            target["draftId"] = draft_id
            state_module.transition(target, state_module.DRAFT, "加入草稿")
        state["drafts"].append({
            **metadata,
            "previewUrl": f"/preview/{draft_id}/",
            "assetsPath": f"drafts/{draft_id}/assets",
        })
        return metadata

    return store.mutate(add)


def cancel_items(store, draft_id, item_ids, library=None, site=None):
    library = Path(library or state_module.LIBRARY).resolve()
    site = Path(site or state_module.ROOT / "site").resolve()
    state = store.read()
    draft = state_module.find_draft(state, draft_id)
    if draft["status"] not in ("ready", "partial"):
        raise ValueError(f"草稿当前状态不能取消图片: {draft['status']}")
    mapping = {entry["itemId"]: entry for entry in draft["items"]}
    unknown = [item_id for item_id in item_ids if item_id not in mapping]
    if unknown:
        raise ValueError(f"草稿中没有这些图片: {', '.join(unknown)}")
    scenes = [copy.deepcopy(scene) for scene in baseline_scenes(state)]
    draft_scenes = {
        scene["id"]: scene for scene in
        json.loads((library / "drafts" / draft_id / "approved.json")
                    .read_text(encoding="utf-8"))["scenes"]
    }
    remaining = []
    for entry in draft["items"]:
        if entry["itemId"] in item_ids:
            continue
        scene = draft_scenes.get(entry["sceneId"])
        if scene is None:
            raise ValueError(f"草稿场景缺失: {entry['sceneId']}")
        scenes.append(copy.deepcopy(scene))
        remaining.append(entry)
    manifest = build_draft_assets(library / "drafts" / draft_id, scenes, library=library, site=site)
    metadata = {
        **draft,
        "status": "ready" if remaining else "partial",
        "items": remaining,
        "sceneIds": [scene["id"] for scene in scenes],
        "sceneCount": len(scenes),
        "addedCount": len(remaining),
        "manifestScenes": len(manifest.get("scenes") or []),
        "updatedAt": state_module.now(),
    }
    (library / "drafts" / draft_id / "draft.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def apply(state):
        target = state_module.find_draft(state, draft_id)
        target.update(metadata)
        for item_id in item_ids:
            item = state_module.find_item(state, item_id)
            item["draftId"] = None
            state_module.transition(item, state_module.ADOPTED, "从草稿取消")
        return metadata

    return store.mutate(apply)


def reduce_after_enable(store, draft_id, enabled_item_ids, library=None, site=None):
    """Keep only the not-yet-enabled pictures in a draft after a partial enable."""
    library = Path(library or state_module.LIBRARY).resolve()
    site = Path(site or state_module.ROOT / "site").resolve()
    state = store.read()
    draft = state_module.find_draft(state, draft_id)
    remaining = [entry for entry in draft.get("items", [])
                 if entry["itemId"] not in enabled_item_ids]
    baseline = [copy.deepcopy(scene) for scene in state["enabled"]["items"]]
    if not remaining:
        fields = {
            "status": "enabled",
            "items": [],
            "sceneIds": [scene["id"] for scene in baseline],
            "sceneCount": len(baseline),
            "baselineCount": len(baseline),
            "addedCount": 0,
        }
        changed = any(draft.get(key) != value for key, value in fields.items())
        if changed:
            fields["enabledAt"] = state_module.now()
            fields["updatedAt"] = state_module.now()
        metadata = {**draft, **fields}
        (library / "drafts" / draft_id / "draft.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not changed:
            return draft

        def close(state):
            target = state_module.find_draft(state, draft_id)
            target.update(metadata)
            return metadata

        return store.mutate(close)
    draft_scenes = {
        scene["id"]: scene for scene in
        json.loads((library / "drafts" / draft_id / "approved.json")
                    .read_text(encoding="utf-8"))["scenes"]
    }
    scenes = [copy.deepcopy(scene) for scene in baseline]
    existing = {scene["id"] for scene in scenes}
    for entry in remaining:
        scene = draft_scenes.get(entry["sceneId"])
        if scene is None:
            raise ValueError(f"草稿场景缺失: {entry['sceneId']}")
        if scene["id"] not in existing:
            scenes.append(copy.deepcopy(scene))
            existing.add(scene["id"])
    manifest = build_draft_assets(library / "drafts" / draft_id, scenes, library=library, site=site)
    fields = {
        "status": "ready",
        "items": remaining,
        "sceneIds": [scene["id"] for scene in scenes],
        "sceneCount": len(scenes),
        "baselineCount": len(baseline),
        "addedCount": len(remaining),
        "manifestScenes": len(manifest.get("scenes") or []),
    }
    changed = any(draft.get(key) != value for key, value in fields.items())
    if changed:
        fields["updatedAt"] = state_module.now()
    metadata = {**draft, **fields}
    (library / "drafts" / draft_id / "draft.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not changed:
        return draft

    def apply(state):
        target = state_module.find_draft(state, draft_id)
        target.update(metadata)
        for entry in remaining:
            item = state_module.find_item(state, entry["itemId"])
            item["draftId"] = draft_id
            if item["status"] != state_module.DRAFT:
                state_module.transition(item, state_module.DRAFT, "部分启用后留在草稿")
        return metadata

    return store.mutate(apply)


def draft_manifest(draft_id, library=None):
    library = Path(library or state_module.LIBRARY).resolve()
    path = library / "drafts" / draft_id / "assets" / "manifest.json"
    if not path.is_file():
        raise ValueError(f"草稿素材清单不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))
