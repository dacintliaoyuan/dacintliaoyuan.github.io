"""Publish explicitly approved artwork through a recoverable, local-only transaction."""

import copy
import hashlib
import io
import json
import os
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path

from PIL import Image

import build_assets
import prepare_scenes


KIND = "art-pipeline-publication"
# Earlier encoding contracts of the sharp layer (build_assets): a site built under one of them is
# recognised and rebuilt, where other sharp layers that do not match are refused as changes made
# outside the pipeline. 2160 px at q90, no full-size layer, until 2026-10-21.
SUPERSEDED_NEAR = [{"maxHeight": 2160, "quality": 90}]


class PublicationError(RuntimeError):
    def __init__(self, message, journal_path=None, recovery_required=False):
        super().__init__(message)
        self.journal_path = journal_path
        self.recovery_required = recovery_required


def _api():
    # The CLI imports this adapter only after constructing its queue API.
    import art_pipeline
    return art_pipeline


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def _bounded(path, root):
    root = Path(root).resolve()
    path = Path(path).absolute()
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError(f"发布路径越界: {path}")
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise ValueError(f"发布路径不允许符号链接或目录联接: {current}")
    return resolved


def _paths(workspace):
    library, home, directory = map(lambda p: Path(p).resolve(),
                                   (workspace.library, workspace.home, workspace.directory))
    _bounded(directory, library)
    return {"library": library, "home": home, "directory": directory,
            "publications": _bounded(directory / "publications", directory),
            "pool": _bounded(home / "site" / "config" / "pool.txt", home),
            "tags": _bounded(home / "site" / "config" / "time-tags.txt", home),
            "approved": _bounded(library / "scenes-approved.json", library),
            "assets": _bounded(home / "site/assets", home),
            "assetLock": _bounded(home / "site/.assets-build.lock", home),
            "libraryLock": _bounded(library / ".scenes-manual-edit.lock", library)}


def _file(path):
    if not path.exists():
        return None
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"预期普通文件: {path}")
    return {"sha256": prepare_scenes.digest(path), "bytes": path.stat().st_size}


def _tree(path, root):
    _bounded(path, root)
    if not path.exists():
        return None
    if not path.is_dir():
        raise ValueError(f"预期素材目录: {path}")
    entries = []
    for child in sorted(path.rglob("*")):
        _bounded(child, root)
        if child.is_file():
            entries.append({"path": child.relative_to(path).as_posix(), "type": "file", **_file(child)})
        elif child.is_dir():
            entries.append({"path": child.relative_to(path).as_posix(), "type": "directory"})
        else:
            raise ValueError(f"不支持的发布目录成员: {child}")
    return {"fingerprint": _hash(entries), "files": entries}


def _snapshot(paths):
    return {"pool": _file(paths["pool"]), "approved": _file(paths["approved"]),
            "assets": _tree(paths["assets"], paths["home"])}


def _queue_owner(workspace):
    lock = _bounded(Path(workspace.directory) / "queue.lock", Path(workspace.directory))
    owner = _api().read(lock)
    if owner.get("pid") != os.getpid() or not isinstance(owner.get("token"), str) or not owner["token"]:
        raise ValueError("发布适配器必须由当前进程持有匹配的 queue.lock")
    return {"pid": owner["pid"], "queueToken": owner["token"]}


def _scenes(workspace, state):
    api = _api()
    selected = [item for item in state["items"] if item["decision"]["status"] == "selected"]
    if not selected:
        raise ValueError("没有已选素材，不清空主页背景池")
    scenes, seen = [], set()
    for item in selected:
        if item["id"] in seen or not api.approved(item):
            raise ValueError(f"已选素材尚未按当前方案及结果验收: {item['id']}")
        seen.add(item["id"])
        artifact = api.best_artifact(item)
        api.verify_artifact(workspace.library, item["source"])
        api.verify_artifact(workspace.library, artifact)
        approval = item["approval"]
        if approval.get("reviewer") != "user" or not approval.get("note"):
            raise ValueError(f"缺少实际用户验收信息: {item['id']}")
        adopted_version = next((key for key in ("adopted", "enhanced", "cropped", "clean")
                                if item.get("variants", {}).get(key) == artifact), "original")
        adopted_version = item.get("adoptedVersion") or adopted_version
        scene = {key: item[key] for key in ("id", "title", "artist", "official", "link")}
        scene.update(focusMode="whole-artwork", adoptedVersion=adopted_version,
                     master={key: artifact[key] for key in ("path", "sha256", "size")},
                     box=copy.deepcopy(item["recipe"]["box"]), cx=item["recipe"]["cx"])
        scene["review"] = copy.deepcopy(approval)
        scene["review"]["contentSha256"] = prepare_scenes.digest_record(scene)
        build_assets.validate_approved_artwork(workspace.library, scene)
        scenes.append(scene)
    return selected, scenes


def _read_manifest(assets):
    manifest = _api().read(assets / "manifest.json")
    script = (assets / "manifest.js").read_text(encoding="utf-8").strip()
    prefix = "window.HOME_MANIFEST = "
    if not script.startswith(prefix) or not script.endswith(";"):
        raise ValueError("主页 manifest.js 格式不支持")
    if json.loads(script[len(prefix):-1]) != manifest:
        raise ValueError("主页 JSON 与浏览器清单不一致")
    return manifest


def _encoded_as(actual, rgb, expected, quality, method):
    """Whether an image read from the site (actual, its pixels rgb) is, pixel for pixel, expected as
    encoded to WebP at that quality and method."""
    if actual.format != "WEBP" or actual.size != expected.size:
        return False
    encoded = io.BytesIO()
    expected.save(encoded, format="WEBP", quality=quality, method=method)
    encoded.seek(0)
    with Image.open(encoded) as reference:
        reference.load()
        return rgb.tobytes() == reference.convert("RGB").tobytes()


def _checked_near(library, assets, scene, rendered):
    """True where the scene's sharp layers follow the current contract, False where they follow one it
    replaced (SUPERSEDED_NEAR: to be rebuilt); anything else is refused."""
    near = _scene_image_path(assets, rendered["near"])
    with Image.open(library / scene["master"]["path"]) as source, Image.open(near) as actual:
        master = source.convert("RGB")
        actual.load()
        rgb = actual.convert("RGB")
        full = "full" in rendered or "nearH" in rendered
        # Older accepted builds used a native-size lossless layer. Accept it
        # without rewriting, alongside the current screen-size WebP contract.
        if rgb.size == master.size and rgb.tobytes() == master.tobytes():
            if full:
                raise ValueError(f"主页清晰层已是原尺寸，却另有原尺寸层: {scene['id']}")
            return True
        cap, quality = build_assets.NEAR_MAX_HEIGHT, build_assets.NEAR_QUALITY
        if _encoded_as(actual, rgb, build_assets.shrunk(master, cap / master.height), quality, 6):
            if full != (master.height > cap) or (full and (rendered.get("nearH") != cap or "full" not in rendered)):
                raise ValueError(f"主页原尺寸清晰层与采用稿不对应: {scene['id']}")
            if full:
                with Image.open(_scene_image_path(assets, rendered["full"])) as layer:
                    layer.load()
                    if not _encoded_as(layer, layer.convert("RGB"), master, quality, build_assets.FULL_METHOD):
                        raise ValueError(f"主页原尺寸清晰层像素与当前编码契约不对应: {scene['id']}")
            return True
        for old in [] if full else SUPERSEDED_NEAR:
            if _encoded_as(actual, rgb, build_assets.shrunk(master, old["maxHeight"] / master.height), old["quality"], 6):
                return False
        raise ValueError(f"主页清晰层尺寸、格式或像素与采用稿不对应: {scene['id']}")


def _scene_image_path(assets, relative):
    if not isinstance(relative, str) or not relative.startswith("scenes/"):
        raise ValueError("主页插画派生图必须位于 assets/scenes 内")
    path = _bounded(assets / relative, assets)
    if path.relative_to(assets).as_posix() != relative:
        raise ValueError("主页插画路径必须是标准相对 POSIX 路径")
    return path


def _matches(workspace, paths, scenes):
    if not all(paths[key].exists() for key in ("pool", "approved", "assets")):
        return False
    pool = build_assets.read_pool(paths["pool"])
    ids = [scene["id"] for scene in scenes]
    if pool != ids:
        return False
    old = {scene["id"]: scene for scene in build_assets.checked_scenes(pool, paths["library"])}
    manifest = _read_manifest(paths["assets"])
    if [scene.get("id") for scene in manifest["scenes"]] != ids:
        return False
    # (the pictures' times of day are the homepage's own, in time-tags.txt beside the pool)
    tags = build_assets.read_time_tags(paths["tags"])
    if any(rendered.get("time") != tags.get(scene_id) for scene_id, rendered in zip(ids, manifest["scenes"])):
        return False
    for scene, rendered in zip(scenes, manifest["scenes"]):
        previous = old.get(scene["id"])
        if previous is None:
            return False
        build_assets.validate_approved_artwork(workspace.library, previous)
        if any(previous.get(key) != scene[key] for key in
               ("master", "box", "cx", "title", "artist", "official", "link", "focusMode")):
            return False
        if (rendered.get("masterSha256") != scene["master"]["sha256"]
                or [rendered.get("w"), rendered.get("h")] != scene["master"]["size"]
                or any(rendered.get(key) != scene[key] for key in ("box", "cx", "title", "artist", "official", "link"))):
            return False
        for key in ("near", "far", "thumb") + (("full",) if "full" in rendered else ()):
            image_path = _scene_image_path(paths["assets"], rendered[key])
            with Image.open(image_path) as image:
                image.load()
        if not _checked_near(paths["library"], paths["assets"], scene, rendered):
            return False
    build_assets.existing_sky_builder(paths["assets"])
    return True


def _integrated(selected, journal=None):
    api = _api()
    for item in selected:
        item["integrated"] = {"status": "integrated", "artifactSha256": api.best_artifact(item)["sha256"],
                              "recipeKey": api.pipeline_key(item), "at": api.now()}
        if journal is not None:
            item["integrated"]["journal"] = str(journal)


def _step(journal_path, journal, phase, **extra):
    journal.update(phase=phase, **extra)
    journal.setdefault("events", []).append({"phase": phase, "at": _api().now()})
    _api().save(journal_path, journal)


def _rename(source, destination, source_root, destination_root):
    source, destination = _bounded(source, source_root), _bounded(destination, destination_root)
    if os.path.lexists(destination):
        raise FileExistsError(f"切换目标意外出现，不覆盖: {destination}")
    source.rename(destination)


def _replace_copy(source, destination, source_root, destination_root):
    source, destination = _bounded(source, source_root), _bounded(destination, destination_root)
    temporary = destination.with_name(destination.name + ".publication-" + uuid.uuid4().hex)
    _bounded(temporary, destination_root)
    try:
        with source.open("rb") as reader, temporary.open("xb") as writer:
            shutil.copyfileobj(reader, writer)
        if _file(source) != _file(temporary):
            raise ValueError("发布元数据复制校验失败")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            _bounded(temporary, destination_root).unlink()


@contextmanager
def _asset_lock(paths, text):
    lock = paths["assetLock"]
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(text)
    try:
        yield
    finally:
        if lock.read_text(encoding="utf-8") != text:
            raise PublicationError(f"素材共享锁已变化，请保留现场: {lock}", recovery_required=True)
        lock.unlink()


def _layout(paths, folder, journal):
    current = _snapshot(paths)
    baseline, desired = journal["baseline"], journal["desired"]
    backup = _tree(folder / "previous-assets", paths["directory"])
    for key in ("pool", "approved"):
        if current[key] not in (baseline[key], desired[key]):
            raise ValueError(f"恢复拒绝覆盖外来变化: {key}")
        previous = folder / f"previous-{key}"
        if baseline[key] is not None and _file(previous) != baseline[key]:
            raise ValueError(f"缺少可核对的旧元数据副本: {key}")
    if current["assets"] not in (baseline["assets"], desired["assets"], None):
        raise ValueError("恢复拒绝覆盖外来素材变化")
    if current["assets"] != baseline["assets"] and backup != baseline["assets"]:
        raise ValueError("缺少可核对的旧素材副本")
    if backup is not None and backup != baseline["assets"]:
        raise ValueError("旧素材副本已经变化")
    return current


def _rollback(paths, folder, journal_path, journal):
    current = _layout(paths, folder, journal)
    baseline = journal["baseline"]
    # Restore files before the directory. Each replacement retains its backup;
    # a failed recovery therefore remains recognizable on the next attempt.
    for key in ("approved", "pool"):
        if current[key] == baseline[key]:
            continue
        target_root = paths["library"] if key == "approved" else paths["home"]
        if baseline[key] is None:
            if paths[key].exists():
                _bounded(paths[key], target_root).unlink()
        else:
            _replace_copy(folder / f"previous-{key}", paths[key], paths["directory"], target_root)
    if current["assets"] != baseline["assets"]:
        if paths["assets"].exists():
            failed = folder / ("interrupted-assets-" + uuid.uuid4().hex)
            _rename(paths["assets"], failed, paths["home"], paths["directory"])
        _rename(folder / "previous-assets", paths["assets"], paths["directory"], paths["home"])
    if _snapshot(paths) != baseline:
        raise PublicationError("恢复后的站点与旧基线不一致", journal_path, True)
    _step(journal_path, journal, "rolled_back")


def publish(workspace, state):
    """Update the local site, then mutate state; the caller persists state itself."""
    paths = _paths(workspace)
    owner = _queue_owner(workspace)
    selected, scenes = _scenes(workspace, state)
    baseline = _snapshot(paths)
    if _matches(workspace, paths, scenes):
        if _scenes(workspace, state)[1] != scenes:
            raise ValueError("核验期间处理方案发生变化，未修改网站")
        if _snapshot(paths) != baseline:
            raise ValueError("核验期间主页基线发生变化，未修改网站")
        _integrated(selected)
        return {"status": "unchanged", "count": len(selected)}
    if baseline["assets"] is None:
        raise ValueError("缺少可复用的既有天空素材；请先建立站点基线")
    token = uuid.uuid4().hex
    folder = paths["publications"] / token
    _bounded(folder, paths["directory"])
    folder.mkdir(parents=True)
    journal_path = folder / "journal.json"
    operation = f"art-pipeline-publish:{token}"
    library_text = f"pid={os.getpid()} operation={operation}\n"
    asset_text = json.dumps({"pid": owner["pid"], "token": token, "operation": KIND}) + "\n"
    journal = {"schemaVersion": 1, "kind": KIND, "token": token, "owner": owner,
               "workspace": {key: str(paths[key]) for key in ("library", "home", "directory")},
               "count": len(selected), "baseline": baseline,
               "libraryLockText": library_text, "assetLockText": asset_text,
               "buildLibraryLockText": f"pid={os.getpid()} operation=build-assets\n",
               "intent": [{"id": item["id"], "recipeKey": _api().pipeline_key(item),
                           "artifactSha256": _api().best_artifact(item)["sha256"]} for item in selected]}
    _step(journal_path, journal, "preparing")
    try:
        pending_approved = folder / "pending-approved.json"
        pending_pool = folder / "pending-pool.txt"
        _api().save(pending_approved, {"schemaVersion": 1, "scenes": scenes})
        pending_pool.write_text("\n".join(scene["id"] for scene in scenes) + "\n", encoding="utf-8")
        staged = folder / "prepared-assets"
        build_assets.rebuild(library=paths["library"], assets=staged, pool_path=pending_pool,
                             approved_path=pending_approved, tags_path=paths["tags"],
                             sky_builder=build_assets.existing_sky_builder(paths["assets"]))
        desired = {"pool": _file(pending_pool), "approved": _file(pending_approved),
                   "assets": _tree(staged, paths["directory"])}
        journal["desired"] = desired
        for key in ("pool", "approved"):
            if baseline[key] is not None:
                shutil.copyfile(paths[key], folder / f"previous-{key}")
                if _file(folder / f"previous-{key}") != baseline[key]:
                    raise ValueError("生成期间正式元数据发生变化，未切换网站")
        _step(journal_path, journal, "prepared")
    except BaseException as error:
        _step(journal_path, journal, "aborted", error=str(error))
        raise PublicationError(f"准备失败，正式网站未切换: {error}；现场: {journal_path}", journal_path) from error
    try:
        with prepare_scenes.library_edit(paths["library"], operation), _asset_lock(paths, asset_text):
            if _scenes(workspace, state)[1] != scenes:
                _step(journal_path, journal, "aborted", error="当前处理方案已变化")
                raise ValueError("生成期间处理方案发生变化，未切换网站")
            if _snapshot(paths) != baseline:
                _step(journal_path, journal, "aborted", error="正式输入或素材发生并发变化")
                raise ValueError("生成期间主页基线发生并发变化，未切换网站")
            try:
                _step(journal_path, journal, "switching")
                _rename(paths["assets"], folder / "previous-assets", paths["home"], paths["directory"])
                _step(journal_path, journal, "old_assets_saved")
                _rename(staged, paths["assets"], paths["directory"], paths["home"])
                _step(journal_path, journal, "assets_installed")
                _replace_copy(pending_approved, paths["approved"], paths["directory"], paths["library"])
                _step(journal_path, journal, "approved_installed")
                _replace_copy(pending_pool, paths["pool"], paths["directory"], paths["home"])
                _step(journal_path, journal, "pool_installed")
                if _snapshot(paths) != desired:
                    raise ValueError("发布后的站点与已生成结果不一致")
                _step(journal_path, journal, "completed")
            except BaseException as error:
                try:
                    _rollback(paths, folder, journal_path, journal)
                except BaseException as restore_error:
                    raise PublicationError(f"发布及恢复未完成，副本全部保留；现场: {journal_path}；恢复错误: {restore_error}",
                                           journal_path, True) from error
                raise PublicationError(f"发布失败，已恢复旧网站: {error}；记录: {journal_path}", journal_path) from error
    except PublicationError as error:
        if error.journal_path is None:
            raise PublicationError(f"{error}；现场: {journal_path}", journal_path, True) from error
        raise
    except BaseException as error:
        outcome = ("站点已切换，收尾失败" if journal.get("phase") == "completed" else
                   "站点已恢复旧基线，收尾失败" if journal.get("phase") == "rolled_back" else "发布未切换")
        raise PublicationError(f"{outcome}: {error}；现场: {journal_path}", journal_path,
                               journal.get("phase") == "completed") from error
    _integrated(selected, journal_path)
    return {"status": "published", "count": len(selected), "journal": str(journal_path)}


def recover(workspace, journal_path):
    """Restore a recognized interrupted transaction; never infer stale locks by age."""
    paths = _paths(workspace)
    owner = _queue_owner(workspace)
    journal_path = _bounded(journal_path, paths["publications"])
    folder = journal_path.parent
    if (journal_path.name != "journal.json" or folder.parent != paths["publications"]
            or len(folder.name) != 32 or any(c not in "0123456789abcdef" for c in folder.name)):
        raise ValueError("只接受本流水线私有 publications/<uuid>/journal.json")
    journal = _api().read(journal_path)
    if (journal.get("schemaVersion") != 1 or journal.get("kind") != KIND or journal.get("token") != folder.name
            or journal.get("workspace") != {key: str(paths[key]) for key in ("library", "home", "directory")}):
        raise ValueError("发布恢复记录不属于当前工作目录")
    old_owner = journal.get("owner", {})
    if _api().process_alive(old_owner.get("pid")):
        raise ValueError("发布持有进程仍活跃，拒绝恢复或删除锁")
    phase = journal.get("phase")
    expected_locks = {}
    for key, expected_key in (("libraryLock", "libraryLockText"), ("assetLock", "assetLockText")):
        if not paths[key].exists():
            continue
        actual = paths[key].read_text(encoding="utf-8")
        allowed = [journal.get(expected_key)]
        if key == "libraryLock" and phase == "preparing":
            allowed.append(journal.get("buildLibraryLockText"))
        if actual not in allowed:
            raise ValueError(f"共享锁不匹配，拒绝恢复: {paths[key]}")
        expected_locks[key] = actual
    if phase in ("preparing", "aborted") and "desired" not in journal:
        if _snapshot(paths) != journal["baseline"]:
            raise ValueError("准备阶段现场已有外来变化，请人工核对 journal")
        for key, text in expected_locks.items():
            if paths[key].read_text(encoding="utf-8") != text:
                raise ValueError("恢复前共享锁再次变化")
            paths[key].unlink()
        return {"status": "unchanged", "journal": str(journal_path), "count": journal["count"]}
    if phase == "completed":
        if _snapshot(paths) != journal["desired"]:
            raise ValueError("已完成发布之后站点发生变化，不用旧 journal 覆盖")
        for key, text in expected_locks.items():
            if paths[key].read_text(encoding="utf-8") != text:
                raise ValueError("恢复前共享锁再次变化")
            paths[key].unlink()
        return {"status": "published", "journal": str(journal_path), "count": journal["count"]}
    _layout(paths, folder, journal)
    for key, text in expected_locks.items():
        if paths[key].read_text(encoding="utf-8") != text:
            raise ValueError("恢复前共享锁再次变化")
        paths[key].unlink()
    operation = f"art-pipeline-publish:{folder.name}"
    library_text = f"pid={os.getpid()} operation={operation}\n"
    asset_text = json.dumps({"pid": owner["pid"], "token": folder.name, "operation": KIND}) + "\n"
    journal.update(owner=owner, libraryLockText=library_text, assetLockText=asset_text)
    _step(journal_path, journal, "recovering")
    try:
        with prepare_scenes.library_edit(paths["library"], operation), _asset_lock(paths, asset_text):
            _rollback(paths, folder, journal_path, journal)
    except BaseException as error:
        raise PublicationError(f"恢复未完成，保留 journal 和全部副本: {journal_path}；{error}", journal_path, True) from error
    return {"status": "rolled_back", "journal": str(journal_path), "count": journal["count"]}
