"""Migrate the 54 enabled masters read-only, verify a draft, and list old data for deletion."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

from PIL import Image

from . import state as state_module
from . import drafts, processing
from .library import digest


OLD_LIBRARY = state_module.ROOT / ".local" / "output" / "adashima-art"
OLD_APPROVED = OLD_LIBRARY / "scenes-approved.json"
FORMAL_MANIFEST = state_module.ROOT / "site" / "assets" / "manifest.json"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _copy_verified(source, destination, sha256):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if digest(destination) != sha256:
            raise ValueError(f"目标母版已存在且内容不同: {destination}")
        return
    temporary = destination.with_name(destination.name + ".part-" + uuid.uuid4().hex)
    try:
        with Path(source).open("rb") as reader, temporary.open("xb") as writer:
            shutil.copyfileobj(reader, writer)
            writer.flush()
            os.fsync(writer.fileno())
        if digest(temporary) != sha256:
            raise ValueError(f"母版复制校验失败: {source}")
        if destination.exists():
            if digest(destination) != sha256:
                raise ValueError(f"目标母版已存在且内容不同: {destination}")
            temporary.unlink()
        else:
            os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _scene_with_new_master(scene, relative, record):
    updated = json.loads(json.dumps(scene))
    updated["master"] = {"path": relative, "sha256": record["sha256"],
                          "size": list(record["size"])}
    content = {key: value for key, value in updated.items() if key != "review"}
    updated["review"] = {
        **updated.get("review", {}),
        "contentSha256": hashlib.sha256(
            json.dumps(content, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
    }
    return updated


def migrate_enabled(store, approved_path=None, tags_path=None, draft_name="54 张迁移核对",
                    library=None, old_library=None, formal_manifest=None, site=None):
    library = Path(library or state_module.LIBRARY).resolve()
    old_library = Path(old_library or OLD_LIBRARY).resolve()
    site = Path(site or state_module.ROOT / "site").resolve()
    approved_path = Path(approved_path or old_library / "scenes-approved.json")
    tags_path = Path(tags_path or state_module.ROOT / "site" / "config" / "time-tags.txt")
    formal_manifest_path = Path(formal_manifest or site / "assets" / "manifest.json")
    approved = _load_json(approved_path)
    if (not isinstance(approved, dict) or approved.get("schemaVersion") != 1
            or not isinstance(approved.get("scenes"), list) or len(approved["scenes"]) != 54):
        raise ValueError("旧采用清单不是预期的 54 张")
    from build_assets import read_time_tags
    tags = read_time_tags(tags_path)
    enabled_dir = library / "enabled"
    if enabled_dir.exists() and any(enabled_dir.iterdir()):
        raise ValueError("新图库 enabled/ 已有内容；迁移不覆盖已有母版")
    enabled_dir.mkdir(parents=True, exist_ok=True)
    scenes, checks, copied_bytes = [], [], 0
    for scene in approved["scenes"]:
        old_path = Path(scene["master"]["path"])
        source = (old_library / old_path).resolve()
        if not source.is_file():
            raise ValueError(f"缺少旧母版: {old_path}")
        actual_sha = digest(source)
        with Image.open(source) as image:
            image.load()
            size = list(image.size)
        if actual_sha != scene["master"]["sha256"] or size != scene["master"]["size"]:
            raise ValueError(f"旧母版 SHA-256 或尺寸不一致: {old_path}")
        extension = source.suffix.lower() or ".png"
        relative = f"enabled/masters/{actual_sha[:2]}/{actual_sha}{extension}"
        destination = library / relative
        _copy_verified(source, destination, actual_sha)
        copied_bytes += source.stat().st_size
        updated = _scene_with_new_master(scene, relative, {"sha256": actual_sha, "size": size})
        if scene["id"] in tags:
            updated["time"] = tags[scene["id"]]
            content = {key: value for key, value in updated.items() if key != "review"}
            updated["review"]["contentSha256"] = hashlib.sha256(
                json.dumps(content, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        scenes.append(updated)
        checks.append({"id": scene["id"], "oldPath": old_path.as_posix(),
                       "newPath": relative, "sha256": actual_sha, "size": size,
                       "time": updated.get("time")})
    enabled = {"schemaVersion": 1, "createdAt": state_module.now(), "items": scenes}
    (enabled_dir / "enabled.json").write_text(
        json.dumps(enabled, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for scene in scenes:
        processing.thumbnail(library, scene["master"]["path"], 320)

    formal_manifest = _load_json(formal_manifest_path)
    formal_before = digest(formal_manifest_path)
    draft_id = "draft-migrate-" + state_module.now().replace(":", "").replace("-", "")[:15]
    draft_dir = library / "drafts" / draft_id
    draft_dir.mkdir(parents=True, exist_ok=False)
    drafts._write_draft_files(draft_dir, scenes)
    manifest = drafts.build_draft_assets(draft_dir, scenes, library=library, site=site)
    drafts.verify_manifest(draft_dir, scenes, formal_manifest)
    metadata = {
        "schemaVersion": drafts.DRAFT_SCHEMA,
        "draftId": draft_id,
        "name": draft_name,
        "createdAt": state_module.now(),
        "status": "ready",
        "sceneCount": len(scenes),
        "baselineCount": len(scenes),
        "addedCount": 0,
        "items": [],
        "sceneIds": [scene["id"] for scene in scenes],
        "manifestScenes": len(manifest.get("scenes") or []),
        "migration": True,
    }
    (draft_dir / "draft.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def apply(state):
        state["enabled"] = {"items": scenes, "migratedAt": state_module.now()}
        state["drafts"].append({**metadata, "previewUrl": f"/preview/{draft_id}/",
                                 "assetsPath": f"drafts/{draft_id}/assets"})
        return {"enabled": len(scenes), "draftId": draft_id}

    store.mutate(apply)
    report = {
        "schemaVersion": 1,
        "createdAt": state_module.now(),
        "count": len(scenes),
        "copiedBytes": copied_bytes,
        "checks": checks,
        "draftId": draft_id,
        "draftSceneCount": len(manifest.get("scenes") or []),
        "formalManifestUnchanged": digest(formal_manifest_path) == formal_before,
    }
    report_path = library / "migration-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _collect_strings(value, output):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ("command", "log", "receipt", "modelFiles"):
                continue
            _collect_strings(child, output)
    elif isinstance(value, list):
        for child in value:
            _collect_strings(child, output)
    elif isinstance(value, str):
        output.add(value)


def _existing_under(root, value):
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        return None
    if "://" in value or "\n" in value or "\r" in value:
        return None
    try:
        path = (root / value).resolve()
    except (OSError, ValueError):
        return None
    if path.is_file() and path.is_relative_to(root.resolve()):
        return path
    return None


def _files_under(path):
    path = Path(path)
    if not path.exists():
        return []
    return [child.resolve() for child in path.rglob("*") if child.is_file()]


def _group(path):
    parts = path.parts
    if "adashima-art" in parts:
        index = parts.index("adashima-art")
        return "/".join(parts[index:index + 2])
    return path.parent.name


def build_deletion_manifest(store, pipeline_path=None, approved_path=None, extra_paths=None,
                            library=None, old_library=None, root=None):
    library = Path(library or state_module.LIBRARY).resolve()
    old_library = Path(old_library or OLD_LIBRARY).resolve()
    root = Path(root or state_module.ROOT).resolve()
    pipeline_path = Path(pipeline_path or old_library / "art-pipeline" / "pipeline.json")
    approved_path = Path(approved_path or old_library / "scenes-approved.json")
    pipeline = _load_json(pipeline_path)
    selected = [item for item in pipeline["items"] if item["decision"]["status"] == "selected"]
    excluded = [item for item in pipeline["items"] if item["decision"]["status"] != "selected"]
    if len(selected) != 54:
        raise ValueError(f"旧流水线已选数量不是 54: {len(selected)}")

    keep = set()
    for keep_root in (library, root / "site" / "assets", root / ".local" / "output" / "homepage-images"):
        keep.update(_files_under(keep_root))
    for path in (root / "site").glob("assets-previous-*"):
        keep.update(_files_under(path))
    for path in (root / "site" / "config" / "pool.txt", root / "site" / "config" / "time-tags.txt",
                 approved_path, old_library / "scenes-manual.json",
                 pipeline_path, old_library / "art-pipeline" / "analysis.json"):
        if Path(path).is_file():
            keep.add(Path(path).resolve())
    for path in (old_library / "art-pipeline" / "publications",
                 old_library / "art-pipeline" / "reports",
                 old_library / "art-pipeline" / "report-archives",
                 old_library / "manual-scenes",
                 old_library / "official-restoration-20261015" / "records",
                 old_library / "official-restoration-20261015" / "qa",
                 old_library / "official-restoration-20261015" / "deliverables"):
        keep.update(_files_under(path))

    selected_refs = set()
    selected_keys = set()
    for item in selected:
        strings = set()
        _collect_strings(item, strings)
        for value in strings:
            path = _existing_under(old_library, value)
            if path:
                selected_refs.add(path)
                keep.add(path)
        selected_keys.add(item.get("pipelineKey"))
    keep.update(selected_refs)

    candidates = {}
    excluded_by_path = {}
    for item in excluded:
        strings = set()
        _collect_strings(item, strings)
        for value in strings:
            path = _existing_under(old_library, value)
            if path and path not in keep:
                candidates[path] = "旧记录引用"
                excluded_by_path.setdefault(path, set()).add(item["id"])

    selected_numbers = {str(item["number"]) for item in selected}
    for kind in ("images", "inputs"):
        item_root = old_library / "official-restoration-20261015" / kind
        if not item_root.is_dir():
            continue
        for child in item_root.iterdir():
            if not child.is_dir() or child.name in selected_numbers:
                continue
            for path in _files_under(child):
                if path not in keep:
                    candidates[path] = "只为未启用旧记录存在的目录"

    cache = old_library / "art-pipeline" / "cache"
    if cache.is_dir():
        for child in cache.iterdir():
            if not child.is_dir() or child.name in selected_keys:
                continue
            files = _files_under(child)
            if any(path in keep for path in files):
                continue
            for path in files:
                candidates[path] = "旧流水线缓存，未被 54 张已启用母版引用"

    explicit = extra_paths or [
        root / "docs" / "research" / "personal-homepage-art-sources-20261013.md",
        root / "docs" / "research" / "personal-homepage-official-originals-20261014.md",
        root / ".local" / "output" / "homepage-gallery-migration-20261016",
        root / ".local" / "output" / "homepage-image-sizes-20261016",
        root / ".local" / "output" / "personal-files-removal-backup-20261022",
        root / ".local" / "output" / "art-pipeline-implementation-20261016",
    ]
    for path in explicit:
        path = Path(path).resolve()
        if path.is_file():
            if path not in keep:
                candidates[path] = "用户已确认的独立清理项"
        elif path.is_dir():
            for child in _files_under(path):
                if child not in keep:
                    candidates[child] = "用户已确认的独立清理项"

    approved = _load_json(approved_path)
    approved_scenes = approved.get("scenes") if isinstance(approved, dict) else []
    approved_scenes = approved_scenes if isinstance(approved_scenes, list) else []
    entries = []
    for path, reason in sorted(candidates.items(), key=lambda pair: str(pair[0])):
        if path in keep:
            continue
        stat = path.stat()
        entry = {
            "path": path.relative_to(root).as_posix(),
            "absolute": str(path),
            "type": "file",
            "bytes": stat.st_size,
            "reason": reason,
            "references": sorted(excluded_by_path.get(path, [])),
        }
        if path.suffix.lower() in IMAGE_SUFFIXES:
            entry["sha256"] = digest(path)
        entries.append(entry)
    groups = {}
    for entry in entries:
        key = "/".join(Path(entry["path"]).parts[:2])
        group = groups.setdefault(key, {"path": key, "files": 0, "bytes": 0})
        group["files"] += 1
        group["bytes"] += entry["bytes"]
    manifest = {
        "schemaVersion": 1,
        "createdAt": state_module.now(),
        "status": "awaiting-user-confirmation",
        "entries": entries,
        "groups": sorted(groups.values(), key=lambda group: group["path"]),
        "totals": {"files": len(entries), "bytes": sum(entry["bytes"] for entry in entries)},
        "kept": {
            "enabledMasters": len(approved_scenes),
            "enabledBytes": sum((old_library / scene["master"]["path"]).stat().st_size
                                for scene in approved_scenes
                                if scene.get("master", {}).get("path")
                                and (old_library / scene["master"]["path"]).is_file()),
            "newLibraryFiles": len(_files_under(library)),
            "siteAssetFiles": len(_files_under(root / "site" / "assets")),
            "oldPipelineRecords": len(excluded),
        },
        "note": "仅生成清单，未删除任何文件。等待用户再次确认后才可执行删除。",
    }
    path = library / "deletion-manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path = library / "migration-report.json"
    report_checks = (_load_json(report_path).get("checks", [])
                     if report_path.is_file() else [])
    keep_list = {
        "schemaVersion": 1,
        "createdAt": state_module.now(),
        "note": "这 54 张旧母版仍被正式主页使用，迁移只复制、不移动；新图库母版已逐张校验。",
        "items": [
            {
                "id": scene["id"],
                "oldPath": scene["master"]["path"],
                "newPath": next((entry["newPath"] for entry in report_checks
                                  if entry["id"] == scene["id"]), None),
                "sha256": scene["master"]["sha256"],
                "size": scene["master"]["size"],
                "time": scene.get("time"),
            }
            for scene in approved_scenes
        ],
        "newLibrary": {"path": str(library), "files": len(_files_under(library))},
        "formalSiteAssets": {"path": str(root / "site" / "assets"),
                             "files": len(_files_under(root / "site" / "assets"))},
    }
    (library / "keep-list.json").write_text(
        json.dumps(keep_list, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = [f"# 待确认删除清单（{manifest['createdAt']}）", "",
                f"共 {manifest['totals']['files']} 个文件，"
                f"{manifest['totals']['bytes']} 字节。", "",
                "| 目录 | 文件数 | 字节数 |", "|---|---:|---:|"]
    markdown += [f"| `{group['path']}` | {group['files']} | {group['bytes']} |"
                 for group in manifest["groups"]]
    markdown += ["", "**未删除任何文件。** 需要用户再次确认后才执行。"]
    (library / "deletion-manifest.md").write_text(
        "\n".join(markdown) + "\n", encoding="utf-8")
    return manifest
