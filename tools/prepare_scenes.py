"""Prepare explicitly handmade masks and review records. No automatic segmentation."""

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import uuid
from datetime import datetime
from functools import wraps
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
from PIL import Image, ImageDraw

LIBRARY = Path(__file__).resolve().parents[1] / ".local" / "output" / "adashima-art"
MANIFEST = "scenes-manual.json"
UPSCAYL = Path("D:/apps/upscayl/resources/bin/upscayl-bin.exe")
MODELS = Path("D:/apps/upscayl/resources/models")
UPSCAYL_MODEL = "high-fidelity-4x"


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


@contextmanager
def library_edit(root, operation):
    lock = root.resolve() / ".scenes-manual-edit.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise ValueError(f"人工素材清单正在修改或存在待核对中断: {lock}") from error
    try:
        with handle:
            handle.write(f"pid={os.getpid()} operation={operation}\n")
        yield
    finally:
        lock.unlink()


def exclusive_edit(operation):
    @wraps(operation)
    def locked(root, *args, **kwargs):
        with library_edit(root, operation.__name__):
            return operation(root.resolve(), *args, **kwargs)
    return locked


def local_path(root, value):
    """Reject escape paths (including resolved links), not just '..' spellings."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("文件路径不能为空")
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError(f"路径必须在指定图库内: {value}")
    return path


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def image_record(root, path):
    with Image.open(path) as image:
        size = list(image.size)
    return {"path": path.relative_to(root).as_posix(), "sha256": digest(path), "size": size}


def verify_record(root, record):
    path = local_path(root, record["path"])
    actual = image_record(root, path)
    if actual != record:
        raise ValueError(f"输入或审核产物已变化，需重新制作并审核: {record['path']}")
    return path


def atomic_json(path, value):
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def valid_id(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200 or any(ord(c) < 32 for c in value):
        raise ValueError("场景 id 必须是 1–200 字符的非空文本")
    # Library IDs use 'provider:artwork'; filenames are independently hashed.
    if any(c in value for c in ("/", "\\")) or value in (".", ".."):
        raise ValueError(f"不合法的场景 id: {value}")
    return value


def checked_mask(path, size):
    with Image.open(path) as image:
        if image.mode not in ("L", "1") or image.size != tuple(size):
            raise ValueError(f"遮罩必须为同尺寸的单通道灰度图: {path}")
        mask = image.convert("L").copy()
    values = np.asarray(mask)
    if not np.any(values > 127) or np.all(values > 127):
        raise ValueError(f"遮罩为空或覆盖整张图: {path}")
    return mask


def polygon_mask(polygons, size):
    if not isinstance(polygons, list) or not polygons:
        raise ValueError("polygons 必须包含人工绘制的多边形")
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for polygon in polygons:
        if not isinstance(polygon, dict) or polygon.get("operation", "add") not in ("add", "subtract"):
            raise ValueError("多边形 operation 仅支持 add/subtract")
        points = polygon.get("points", [])
        if not isinstance(points, list) or len(points) < 3:
            raise ValueError("每个多边形至少需要三个点")
        for point in points:
            if (not isinstance(point, list) or len(point) != 2
                    or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in point)
                    or not (0 <= point[0] < size[0] and 0 <= point[1] < size[1])):
                raise ValueError("多边形点必须位于原图像素范围内")
        draw.polygon([tuple(p) for p in points], fill=255 if polygon.get("operation", "add") == "add" else 0)
    values = np.asarray(mask)
    if not np.any(values > 127) or np.all(values > 127):
        raise ValueError("多边形遮罩为空或覆盖整张图")
    return mask


def overlay(rgb, mask, path):
    pixels = np.asarray(rgb, np.float32)
    alpha = np.asarray(mask, np.float32)[..., None] / 255 * 0.5
    tinted = pixels * (1 - alpha) + np.array([255, 70, 130], np.float32) * alpha
    # Full-size output allows real edge inspection, not just a thumbnail.
    Image.fromarray(tinted.astype(np.uint8)).save(path)


def validate_item(root, item, approved=False):
    valid_id(item["id"])
    if item.get("maskMethod") not in ("handmade-mask", "handmade-polygons"):
        raise ValueError("只接受显式人工遮罩，不接受旧自动分割结果")
    if item.get("producerSha256") != digest(Path(__file__).resolve()):
        raise ValueError("人工制图脚本已变更，需重新准备并审核")
    paths = {name: verify_record(root, item["files"][name]) for name in ("original", "source", "mask", "qa")}
    if (item.get("src") != item["files"]["source"]["path"] or item.get("mask") != item["files"]["mask"]["path"]
            or item.get("qa") != item["files"]["qa"]["path"]
            or [item.get("w"), item.get("h")] != item["files"]["source"]["size"]):
        raise ValueError("素材路径或尺寸与哈希记录不一致")
    if "maskInput" in item["files"]:
        verify_record(root, item["files"]["maskInput"])
    checked_mask(paths["mask"], item["files"]["source"]["size"])
    if approved:
        review = item.get("review", {})
        if review.get("status") != "approved" or not review.get("reviewer") or not review.get("note"):
            raise ValueError(f"场景尚未人工审核: {item['id']}")
        expected = digest_record(item)
        if review.get("contentSha256") != expected:
            raise ValueError(f"审核后元数据发生变化: {item['id']}")
        if item["upscale"]["used"] and not review.get("upscaleCompared"):
            raise ValueError("放大图尚未完成原图对照")
    return paths


def digest_record(item):
    content = {key: value for key, value in item.items() if key != "review"}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def load_manifest(root):
    path = root / MANIFEST
    if not path.is_file():
        raise ValueError("缺少 scenes-manual.json；请先制作人工遮罩，不会回退到旧 scenes.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("schemaVersion") != 1
            or not isinstance(data.get("scenes"), list) or not data["scenes"]
            or not all(isinstance(item, dict) for item in data["scenes"])):
        raise ValueError("人工素材清单格式错误或没有场景")
    ids = [valid_id(item["id"]) for item in data["scenes"]]
    if len(ids) != len(set(ids)):
        raise ValueError("人工素材清单包含重复 id")
    return data


@exclusive_edit
def prepare(root, input_path, upscale_ids=(), upscale_reason="", scale=2):
    root = root.resolve()
    producer_hash = digest(Path(__file__).resolve())
    input_path = local_path(root, str(input_path))
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    items = payload.get("scenes") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items or not all(isinstance(item, dict) for item in items):
        raise ValueError("输入 scenes 不能为空")
    ids = [valid_id(item["id"]) for item in items]
    if len(ids) != len(set(ids)) or not set(upscale_ids).issubset(ids):
        raise ValueError("id 重复或按需放大 id 不在输入中")
    if upscale_ids and not upscale_reason.strip():
        raise ValueError("按需放大必须记录尺寸不足的原因")
    validated = []
    for item in items:
        original = local_path(root, item["original"])
        if any(original.is_relative_to(root / name) for name in ("scenes", "manual-scenes", "cutouts", "cutouts2")):
            raise ValueError("original 必须来自原图库，不能使用旧处理结果")
        original_record = image_record(root, original)
        with Image.open(original) as image:
            rgb = image.convert("RGB")
        if not isinstance(item.get("official"), bool) or not all(isinstance(item.get(k), str) and item[k].strip() for k in ("artist", "link")):
            raise ValueError("artist/link/official 必须显式提供")
        link = urlparse(item["link"])
        if link.scheme not in ("https", "http") or not link.netloc:
            raise ValueError("作品来源链接必须是完整 HTTP(S) 地址")
        if ("mask" in item) == ("polygons" in item):
            raise ValueError("必须且只能提供 mask 或 polygons")
        mask_input = None
        mask_input_record = None
        if "mask" in item:
            mask_input = local_path(root, item["mask"])
            if not mask_input.is_relative_to(root / "manual-input") or item.get("maskOrigin") != "handmade-from-original":
                raise ValueError("人工遮罩必须位于 manual-input/ 并声明 maskOrigin=handmade-from-original")
            mask_input_record = image_record(root, mask_input)
            mask = checked_mask(mask_input, rgb.size)
        else:
            mask = polygon_mask(item["polygons"], rgb.size)
        validated.append((item, original, original_record, rgb, mask, mask_input_record))
    # Unique output batches never overwrite a prior mask or review image.
    batch = root / "manual-scenes" / uuid.uuid4().hex
    batch.mkdir(parents=True)
    scenes = []
    for item, original, original_record, rgb, mask, mask_input_record in validated:
        prefix = hashlib.sha256(item["id"].encode("utf-8")).hexdigest()[:16]
        source = original
        used = item["id"] in upscale_ids
        if used:
            for required in (UPSCAYL, MODELS / f"{UPSCAYL_MODEL}.bin", MODELS / f"{UPSCAYL_MODEL}.param"):
                if not required.is_file():
                    raise ValueError(f"缺少 Upscayl 本机文件: {required}")
            source_png = batch / f"{prefix}-upscale-input.png"
            rgb.save(source_png)
            source = batch / f"{prefix}-x{scale}.png"
            subprocess.run([str(UPSCAYL), "-i", str(source_png), "-o", str(source), "-n", UPSCAYL_MODEL,
                            "-m", str(MODELS), "-z", "4", "-s", str(scale), "-f", "png"], check=True,
                           capture_output=True, text=True, timeout=600)
            with Image.open(source) as image:
                rgb = image.convert("RGB")
            expected_size = tuple(v * scale for v in original_record["size"])
            if rgb.size != expected_size:
                raise ValueError("Upscayl 输出尺寸与请求倍率不符")
            mask = mask.resize(rgb.size, Image.Resampling.LANCZOS)
        mask_path = batch / f"{prefix}-mask.png"
        qa_path = batch / f"{prefix}-qa.png"
        mask.save(mask_path)
        overlay(rgb, mask, qa_path)
        files = {"original": original_record, "source": image_record(root, source),
                 "mask": image_record(root, mask_path), "qa": image_record(root, qa_path)}
        if mask_input_record:
            files["maskInput"] = mask_input_record
        scene = {"id": item["id"], "src": files["source"]["path"], "mask": files["mask"]["path"],
                 "qa": files["qa"]["path"], "w": rgb.width, "h": rgb.height,
                 "artist": item["artist"], "link": item["link"], "official": item["official"],
                 "maskMethod": "handmade-mask" if mask_input_record else "handmade-polygons",
                 "producerSha256": producer_hash,
                 "files": files, "upscale": {"used": used, "scale": scale if used else 1,
                                             "reason": upscale_reason if used else "",
                                             "model": UPSCAYL_MODEL if used else None},
                 "review": {"status": "pending"}}
        if "polygons" in item:
            scene["polygons"] = item["polygons"]
        validate_item(root, scene)
        scenes.append(scene)
    # Preserve the prior manifest and all prior batches for recovery.
    destination = root / MANIFEST
    if destination.exists():
        (batch / "previous-scenes-manual.json").write_bytes(destination.read_bytes())
    for scene in scenes:
        validate_item(root, scene)
    atomic_json(destination, {"schemaVersion": 1, "prepared": now(), "scenes": scenes})
    return scenes


@exclusive_edit
def approve(root, scene_id, reviewer, note, upscale_compared=False):
    if not reviewer.strip() or not note.strip():
        raise ValueError("人工审核必须填写 reviewer 和 note")
    data = load_manifest(root)
    matches = [item for item in data["scenes"] if item["id"] == scene_id]
    if not matches:
        raise ValueError(f"没有场景: {scene_id}")
    item = matches[0]
    validate_item(root, item)
    if item["upscale"]["used"] and not upscale_compared:
        raise ValueError("请完成原图/放大图对照后明确传入 --upscale-compared")
    item["review"] = {"status": "approved", "reviewer": reviewer, "note": note, "at": now(),
                      "contentSha256": digest_record(item), "upscaleCompared": upscale_compared}
    atomic_json(root / MANIFEST, data)


def main(argv=None):
    parser = argparse.ArgumentParser(description="人工背景遮罩准备与 QA；不运行自动分割")
    parser.add_argument("--library", type=Path, default=LIBRARY)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("prepare", help="从原图及人工输入输出遮罩和检查图")
    create.add_argument("--input", required=True, type=Path)
    create.add_argument("--upscale-id", action="append", default=[])
    create.add_argument("--upscale-reason", default="")
    create.add_argument("--scale", type=int, choices=(2, 4), default=2)
    review = commands.add_parser("approve", help="检查 QA 后明确记录审核结果")
    review.add_argument("--id", required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--note", required=True)
    review.add_argument("--upscale-compared", action="store_true")
    commands.add_parser("validate", help="检查所有人工素材及审核状态")
    args = parser.parse_args(argv)
    root = args.library.resolve()
    try:
        if args.command == "prepare":
            scenes = prepare(root, args.input, args.upscale_id, args.upscale_reason, args.scale)
            print(f"已准备 {len(scenes)} 张素材。请检查每张 qa 文件后逐张 approve；尚未审核。")
        elif args.command == "approve":
            approve(root, args.id, args.reviewer, args.note, args.upscale_compared)
            print(f"已记录人工审核: {args.id}")
        else:
            for item in load_manifest(root)["scenes"]:
                validate_item(root, item, approved=True)
            print("人工素材及审核记录有效。")
        return 0
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        print(f"素材处理失败: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
