"""Generate site/assets/ (scene focus images, cloud layers, manifest) for the homepage.

Sources stay on this machine and out of Git:
- the illustrations listed in site/config/pool.txt: reviewed masks in scenes-manual.json, or approved complete
  artworks in scenes-approved.json (a whole-picture focus pull, without segmentation);
- the Pexels sky photos in the blue-sky reference folder (see sky.py).
Each picture's time of day comes from site/config/time-tags.txt beside the pool (in Git).
Masked scenes use character/background focus layers. Approved complete artworks use a whole-picture
focus pull; their sharp layer is scaled to the screen (NEAR_MAX_HEIGHT) as high-quality lossy WebP
(one taller than that is also kept at its adopted size, for screens that show it with more pixels),
and the adopted masters stay untouched.
Run:  python tools/build_assets.py
"""

import json
import argparse
import shutil
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter

import sky
import prepare_scenes

HOME = Path(__file__).resolve().parents[1]
LIBRARY = HOME / ".local" / "output" / "homepage-images"
if not (LIBRARY / "scenes-approved.json").exists():
    LIBRARY = HOME / ".local" / "output" / "adashima-art"
ASSETS = HOME / "site" / "assets"
MAX_WIDTH = {"portrait": 1800, "landscape": 2400}
# Approved artworks: the page shows a picture whole, so at most a screen's height of it. Lossless
# layers at the adopted size (up to 4096 px, 9 MB) held up the focus pull while the browser uploaded
# them; at a 4K screen's height they look the same there and weigh well under 1 MB. A picture taller
# than that also gets its sharp layer at the adopted size ("full", with "nearH" in the manifest), which
# the page takes only where a screen shows it with more pixels (a 5K screen, a tablet held upright).
# Both are q95 (the user's choice, 2026-10-21); the full one with a faster method, which at that size
# costs some 7% more bytes and saves some 40% of the time (9 s against 15 s on the biggest master).
NEAR_MAX_HEIGHT = 2160
NEAR_QUALITY = 95
FULL_METHOD = 4
FAR_MAX_SIDE = 1280  # the far layer is blurred, so it needs few pixels
FAR_BLUR = 0.0045   # blur radius of the out-of-focus characters, as a share of the image width
NEAR_BLUR = 0.0035  # blur radius of the softened background after the focus pull
# The times of day a picture can be tagged with in time-tags.txt, as the manifest gives them ("time";
# a picture without one fits any time).
TIMES = {"白天": "day", "黄昏": "dusk", "夜晚": "night"}


def read_pool(path=None):
    lines = (path or HOME / "site" / "config" / "pool.txt").read_text(encoding="utf-8").splitlines()
    pool = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
    if not pool or len(pool) != len(set(pool)):
        raise ValueError("主角池不能为空或含重复 id")
    return [prepare_scenes.valid_id(value) for value in pool]


def read_time_tags(path=None):
    """The pictures' times of day, {id: 'day' | 'dusk' | 'night'}: time-tags.txt, a line to a picture
    (its id, a tab, 白天, 黄昏 or 夜晚; # starts a note). No file, no tags; ids not in the pool are
    left for the pool to take up again."""
    path = path or HOME / "site" / "config" / "time-tags.txt"
    if not path.exists():
        return {}
    tags = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.strip().split("\t")
        if len(parts) != 2 or parts[1] not in TIMES:
            raise ValueError(f"时段标签第 {number} 行格式错误（应为 id、Tab、白天／黄昏／夜晚）: {line}")
        scene_id = prepare_scenes.valid_id(parts[0])
        if scene_id in tags:
            raise ValueError(f"时段标签含重复 id: {scene_id}")
        tags[scene_id] = TIMES[parts[1]]
    return tags


def frame_depth(profile):
    """How deep a light frame reaches in from one edge (0 when the artwork starts at the edge).

    Some artists post with a white or pale margin, sometimes with bits of the artwork overlapping
    it, so the frame is recognised by brightness alone and must end within 6% of the picture."""
    if profile[0] < 215:
        return 0
    for index in range(round(0.06 * len(profile))):
        if profile[index] < 200:
            return index
    return 0


def trim_border(rgb, mask):
    gray = rgb.mean(axis=2)
    rows, cols = gray.mean(axis=1), gray.mean(axis=0)
    top, bottom = frame_depth(rows), frame_depth(rows[::-1])
    left, right = frame_depth(cols), frame_depth(cols[::-1])
    if not any((top, bottom, left, right)):
        return rgb, mask
    inset = max(2, round(0.004 * rgb.shape[1]))   # also drop the soft inner edge of the frame
    top, bottom, left, right = (depth + inset if depth else 0 for depth in (top, bottom, left, right))
    height, width = gray.shape
    return rgb[top:height - bottom, left:width - right], mask[top:height - bottom, left:width - right]


def focus_images(rgb, mask):
    image = rgb.astype(np.float32)
    width = rgb.shape[1]
    blur = lambda x, share: cv2.GaussianBlur(x, (0, 0), share * width)
    # Far focus: the characters (plus a margin their blur spreads into) are soft, the rest stays sharp.
    spread = cv2.dilate((mask > 0.3).astype(np.float32), np.ones((9, 9), np.uint8))
    region = np.clip(blur(spread, FAR_BLUR * 1.5) * 1.6, 0, 1)[..., None]
    far = image * (1 - region) + blur(image, FAR_BLUR) * region
    # Near focus: the background is blurred without the characters' colours bleeding into it
    # (normalized convolution over the background only), then the sharp characters go back on top.
    background = (1 - mask)[..., None]
    weight = blur(background[..., 0], NEAR_BLUR)[..., None]
    soft = np.where(weight > 1e-3, blur(image * background, NEAR_BLUR) / np.maximum(weight, 1e-3),
                    blur(image, NEAR_BLUR))
    near = image * mask[..., None] + soft * background
    to_image = lambda x: Image.fromarray(x.clip(0, 255).astype(np.uint8))
    return to_image(far), to_image(near)


def checked_scenes(pool, library, approved_path=None):
    if approved_path is not None:
        approved_path = prepare_scenes.local_path(library, str(approved_path))
        if not approved_path.is_file():
            raise ValueError("指定采用清单不存在")
    else:
        approved_path = library / "scenes-approved.json"
    approved = {}
    if approved_path.exists():
        data = json.loads(approved_path.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or data.get("schemaVersion") != 1
                or not isinstance(data.get("scenes"), list)
                or not all(isinstance(item, dict) for item in data["scenes"])):
            raise ValueError("已验收整图清单格式错误")
        for item in data["scenes"]:
            scene_id = prepare_scenes.valid_id(item["id"])
            if scene_id in approved:
                raise ValueError(f"已验收整图清单包含重复 id: {scene_id}")
            approved[scene_id] = item
    manual_ids = [scene_id for scene_id in pool if scene_id not in approved]
    candidates = {}
    if manual_ids:
        candidates = {item["id"]: item for item in prepare_scenes.load_manifest(library)["scenes"]}
    candidates.update(approved)
    missing = [scene_id for scene_id in pool if scene_id not in candidates]
    if missing:
        raise ValueError(f"主角池缺少人工素材: {missing}")
    items = [candidates[scene_id] for scene_id in pool]
    for item in items:
        if item["id"] in approved:
            validate_approved_artwork(library, item)
        else:
            prepare_scenes.validate_item(library, item, approved=True)
    return items


def validate_approved_artwork(library, item):
    """Bind the user's adoption to exact pixels and framing, without claiming a reviewed mask."""
    if item.get("focusMode") != "whole-artwork":
        raise ValueError("已验收整图只接受 whole-artwork 对焦模式")
    review = item.get("review", {})
    if (not isinstance(review, dict) or review.get("status") != "approved" or not review.get("reviewer") or not review.get("note")
            or review.get("contentSha256") != prepare_scenes.digest_record(item)):
        raise ValueError(f"整图未验收或验收后内容已变化: {item['id']}")
    prepare_scenes.verify_record(library, item["master"])
    box, cx = item["box"], item["cx"]
    if (not isinstance(box, list) or len(box) != 4
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in box)
            or not 0 <= box[0] < box[2] <= 1 or not 0 <= box[1] < box[3] <= 1
            or not isinstance(cx, (int, float)) or isinstance(cx, bool) or not box[0] <= cx <= box[2]):
        raise ValueError(f"整图取景范围错误: {item['id']}")


def shrunk(image, factor):
    """The image scaled by factor, never enlarged."""
    if factor >= 1:
        return image
    size = (max(1, round(image.width * factor)), max(1, round(image.height * factor)))
    return image.resize(size, Image.Resampling.LANCZOS)


def build_approved_artwork(item, library, target, number):
    """Keep the adopted framing and size it for the screen; only the temporary far-focus layer is soft.

    w and h stay the adopted size: the page reads them as the picture's proportions."""
    with Image.open(library / item["master"]["path"]) as image:
        master = image.convert("RGB")
    width, height = master.size
    stem = f"s{number:02d}-{item['master']['sha256'][:12]}"
    names = {"far": f"{stem}-far.webp", "near": f"{stem}-near.webp", "thumb": f"{stem}-thumb.webp"}
    shrunk(master, NEAR_MAX_HEIGHT / height).save(target / names["near"], quality=NEAR_QUALITY, method=6)
    full = height > NEAR_MAX_HEIGHT
    if full:
        names["full"] = f"{stem}-full.webp"
        master.save(target / names["full"], quality=NEAR_QUALITY, method=FULL_METHOD)
    far = shrunk(master, FAR_MAX_SIDE / max(width, height))
    far.filter(ImageFilter.GaussianBlur(FAR_BLUR * far.width)).save(
        target / names["far"], quality=82, method=6)
    thumb = master.copy()
    thumb.thumbnail((480, 640), Image.Resampling.LANCZOS)
    thumb.save(target / names["thumb"], quality=85, method=6)
    rgb = np.asarray(master)
    band = rgb[:max(2, round(0.06 * height))].reshape(-1, 3).astype(np.float32)
    luminance = band @ np.array([0.299, 0.587, 0.114], np.float32)
    top = np.median(band[luminance >= np.percentile(luminance, 50)], axis=0)
    return {
        **{key: f"scenes/{name}" for key, name in names.items()},
        "id": item["id"], "title": item.get("title", ""), "w": width, "h": height,
        **({"nearH": NEAR_MAX_HEIGHT} if full else {}),
        "box": item["box"], "cx": item["cx"], "focusMode": "whole-artwork",
        "top": "#" + "".join(f"{round(v):02x}" for v in top),
        "official": item.get("official"), "artist": item.get("artist", ""), "link": item.get("link", ""),
        "masterSha256": item["master"]["sha256"], "adoptedVersion": item["adoptedVersion"],
    }


def build_scenes(items, library, assets, tags=None):
    target = assets / "scenes"
    target.mkdir(parents=True)
    scenes = []
    for number, item in enumerate(items, start=1):
        if item.get("focusMode") == "whole-artwork":
            scenes.append(build_approved_artwork(item, library, target, number))
            continue
        with Image.open(library / item["src"]) as image:
            rgb = np.asarray(image.convert("RGB"))
        with Image.open(library / item["mask"]) as image:
            mask = np.asarray(image.convert("L"), np.float32) / 255
        rgb, mask = trim_border(rgb, mask)
        height, width = mask.shape
        limit = MAX_WIDTH["portrait" if height >= width else "landscape"]
        if width > limit:
            size = (limit, round(height * limit / width))
            rgb = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
            mask = cv2.resize(mask, size, interpolation=cv2.INTER_AREA)
            height, width = mask.shape
        far, near = focus_images(rgb, mask)
        names = {"far": f"s{number:02d}-far.webp", "near": f"s{number:02d}-near.webp"}
        far.save(target / names["far"], quality=80, method=6)
        near.save(target / names["near"], quality=82, method=6)
        ys, xs = np.nonzero(mask > 0.5)
        if not len(xs):
            raise ValueError(f"裁切后人物遮罩为空: {item['id']}")
        # Sky colour at the top edge: the brighter half of the top band, so trees or a dark corner
        # reaching into the band do not grey it.
        band = rgb[: max(2, round(0.06 * height))].reshape(-1, 3).astype(np.float32)
        luminance = band @ np.array([0.299, 0.587, 0.114], np.float32)
        top = np.median(band[luminance >= np.percentile(luminance, 50)], axis=0)
        scenes.append({
            "far": f"scenes/{names['far']}", "near": f"scenes/{names['near']}", "w": width, "h": height,
            # the two characters' box and horizontal centre of mass, as shares of the picture
            "box": [round(xs.min() / width, 4), round(ys.min() / height, 4),
                    round(xs.max() / width, 4), round(ys.max() / height, 4)],
            "cx": round(float(xs.mean()) / width, 4),
            "top": "#" + "".join(f"{round(v):02x}" for v in top),   # sky colour at the picture's top edge
            "official": item["official"], "artist": item["artist"], "link": item["link"],
        })
    for item, scene in zip(items, scenes):
        if item["id"] in (tags or {}):
            scene["time"] = tags[item["id"]]
    return scenes


def managed_directory(path, parent):
    resolved = path.resolve()
    if resolved.parent != parent.resolve() or path.is_symlink():
        raise ValueError(f"素材目录必须是指定站点目录的直接子目录: {path}")
    return resolved


def existing_sky_builder(assets):
    """Explicitly reuse checked cloud layers when only the illustration pool is being replaced."""
    root = assets.resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    layers = manifest["sky"]
    if not isinstance(layers, dict) or not layers:
        raise ValueError("没有可复用的既有云层")
    records = {}
    for name, layer in layers.items():
        source = prepare_scenes.local_path(root, layer["file"])
        record = prepare_scenes.image_record(root, source)
        if (record["size"] != [layer["w"], layer["h"]] or not record["path"].startswith("sky/")
                or layer["file"] != record["path"]):
            raise ValueError(f"既有云层尺寸或路径错误: {name}")
        records[name] = record

    def copy_layers(target):
        target.mkdir()
        for name, record in records.items():
            source = prepare_scenes.verify_record(root, record)
            destination = target.parent / layers[name]["file"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            if prepare_scenes.digest(destination) != record["sha256"]:
                raise ValueError(f"云层复制校验失败: {name}")
        return layers

    return copy_layers


def rebuild(library=LIBRARY, assets=ASSETS, pool_path=None, sky_builder=None, approved_path=None, tags_path=None):
    # Share the editor lock through generation and publication.
    with prepare_scenes.library_edit(library, "build-assets"):
        return _rebuild(library, assets, pool_path, sky_builder, approved_path, tags_path)


def _rebuild(library, assets, pool_path, sky_builder, approved_path=None, tags_path=None):
    """Validate, generate alongside current assets, then switch with recoverable backup."""
    library = library.resolve()
    assets = assets.absolute()
    parent = assets.parent.resolve()
    managed_directory(assets, parent)
    items = checked_scenes(read_pool(pool_path), library, approved_path)
    tags = read_time_tags(tags_path)
    parent.mkdir(parents=True, exist_ok=True)
    # Exclusive lock stops two rebuilds from renaming each other's outputs. Stale locks fail closed.
    lock = parent / f".{assets.name}-build.lock"
    try:
        lock_handle = lock.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise ValueError(f"已有重建或待核对的中断现场: {lock}") from error
    staging = None
    backup = None
    try:
        with lock_handle:
            lock_handle.write("素材重建进行中；中断后请先核对 staging/backup 目录再处理锁。\n")
        staging = Path(tempfile.mkdtemp(prefix=f".{assets.name}-staging-", dir=parent))
        managed_directory(staging, parent)
        manifest = {
            "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
            "scenes": build_scenes(items, library, staging, tags),
            "sky": (sky_builder or sky.build)(staging / "sky"),
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        (staging / "manifest.js").write_text(
            f"window.HOME_MANIFEST = {json.dumps(manifest, ensure_ascii=False)};\n", encoding="utf-8")
        # Recheck inputs after expensive generation and before publishing the prepared directory.
        current = checked_scenes(read_pool(pool_path), library, approved_path)
        if current != items or read_time_tags(tags_path) != tags:
            raise ValueError("生成期间人工素材、主角池或时段标签发生变化，请重新运行")
        if assets.exists():
            backup = parent / f"{assets.name}-previous-{uuid.uuid4().hex}"
            managed_directory(assets, parent)
            managed_directory(backup, parent)
            assets.rename(backup)
        try:
            managed_directory(staging, parent)
            staging.rename(assets)
            staging = None
        except BaseException as publish_error:
            if backup is not None and not assets.exists():
                managed_directory(backup, parent)
                try:
                    backup.rename(assets)
                except OSError as restore_error:
                    raise RuntimeError(f"切换及自动恢复失败。旧素材仍在 {backup}；恢复错误: {restore_error}") from publish_error
            raise
        return manifest, backup
    finally:
        if staging is not None and staging.exists():
            managed_directory(staging, parent)
            shutil.rmtree(staging)
        lock.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description="从已验收整图或已审核人工素材安全重建主页 assets")
    parser.add_argument("--library", type=Path, default=LIBRARY)
    parser.add_argument("--reuse-sky", action="store_true", help="复用并校验当前站点云层，只重建背景插画")
    args = parser.parse_args(argv)
    try:
        sky_builder = existing_sky_builder(ASSETS) if args.reuse_sky else None
        manifest, backup = rebuild(library=args.library, sky_builder=sky_builder)
        print(f"[assets] {len(manifest['scenes'])} scenes, {len(manifest['sky'])} cloud layers")
        if backup:
            print(f"前一份素材已保留，可恢复: {backup}")
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, cv2.error) as error:
        print(f"素材重建失败，旧素材未删除（可能在备份目录）: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
