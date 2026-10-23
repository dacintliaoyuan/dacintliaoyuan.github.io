"""Deterministic local processing with an immutable, resumable version chain."""

from __future__ import annotations

import hashlib
import io
import json
import os
import uuid
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

import cv2

import art_pipeline_processing

from . import state as state_module
from .library import digest


UPSCALE_DEFAULTS = {
    "binary": "D:/apps/upscayl/resources/bin/upscayl-bin.exe",
    "modelDir": "D:/apps/upscayl/resources/models",
    "model": "high-fidelity-4x",
    "scale": 2,
    "tile": 256,
    "timeout": 240,
}


class ProcessingCancelled(RuntimeError):
    pass


class ProcessingError(RuntimeError):
    def __init__(self, message, *, step=None):
        super().__init__(message)
        self.step = step


def _key(step, input_sha, recipe, processor):
    payload = json.dumps({"step": step, "inputSha256": input_sha,
                          "recipe": recipe, "processor": processor},
                         sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def version_id(step, input_sha, recipe, processor):
    return "v-" + _key(step, input_sha, recipe, processor)[:16]


def open_image(library, record):
    with Image.open(Path(library) / record["path"]) as image:
        image.load()
        return image.convert("RGB")


def save_png(library, relative, image):
    library = Path(library).resolve()
    path = (library / relative).resolve()
    if not path.is_relative_to(library) or path == library:
        raise ValueError(f"版本路径越界: {relative}")
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=False, compress_level=6)
    data = buffer.getvalue()
    sha256 = hashlib.sha256(data).hexdigest()
    if path.exists():
        if digest(path) != sha256:
            raise ValueError(f"同名版本文件内容不同，不覆盖: {relative}")
    else:
        temporary = path.with_name(path.name + ".part-" + uuid.uuid4().hex)
        try:
            with temporary.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if path.exists():
                temporary.unlink()
            else:
                os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
    return {"path": path.relative_to(library).as_posix(), "sha256": sha256,
            "size": [image.width, image.height], "bytes": len(data)}


def ensure_version(store, library, item_id, step, image, input_record, recipe, processor,
                   reused=False, output_record=None, evidence=None):
    """Return an existing matching version or persist a new immutable one."""
    version = version_id(step, input_record["sha256"], recipe, processor)
    current = state_module.find_item(store.read(), item_id)
    existing = next((entry for entry in current["versions"] if entry["versionId"] == version), None)
    if existing:
        path = Path(library) / existing["path"]
        if not path.is_file() or digest(path) != existing["sha256"]:
            raise ValueError(f"已有版本文件缺失或已变化: {existing['path']}")
        return existing
    if reused:
        output = output_record or input_record
        record = {
            "versionId": version, "step": step, "path": output["path"],
            "sha256": output["sha256"], "size": list(output["size"]),
            "bytes": output.get("bytes"),
            "recipe": recipe, "processor": processor,
            "inputSha256": input_record["sha256"],
            "parentVersion": input_record.get("versionId"),
            "createdAt": state_module.now(), "reused": True,
        }
        if evidence:
            record["evidence"] = evidence
    else:
        if image is None:
            raise ValueError("新版本缺少图片")
        relative = f"versions/{item_id}/{version}-{step}.png"
        saved = save_png(library, relative, image)
        record = {
            "versionId": version, "step": step, "path": saved["path"],
            "sha256": saved["sha256"], "size": saved["size"],
            "bytes": saved["bytes"], "recipe": recipe, "processor": processor,
            "inputSha256": input_record["sha256"],
            "parentVersion": input_record.get("versionId"),
            "createdAt": state_module.now(), "reused": False,
        }
        if evidence:
            record["evidence"] = evidence

    def append(state):
        target = state_module.find_item(state, item_id)
        found = next((entry for entry in target["versions"] if entry["versionId"] == version), None)
        if found:
            return found
        target["versions"].append(record)
        return record

    return store.mutate(append)


def latest_version(item, step):
    for version in reversed(item["versions"]):
        if version["step"] == step:
            return version
    return None


def base_record(item):
    for version in reversed(item["versions"]):
        if version["step"] == "ai-clean":
            return version
    return {"path": item["original"]["path"], "sha256": item["original"]["sha256"],
            "size": list(item["original"]["size"]), "versionId": None,
            "bytes": item["original"].get("bytes")}


def crop(image, box):
    width, height = image.size
    left = max(0, min(width - 1, round(box[0] * width)))
    top = max(0, min(height - 1, round(box[1] * height)))
    right = max(left + 1, min(width, round(box[2] * width)))
    bottom = max(top + 1, min(height, round(box[3] * height)))
    return image.crop((left, top, right, bottom))


def denoise(image, strength):
    if strength <= 0:
        return image
    array = np.asarray(image)
    h = max(1, round(2 + 8 * strength))
    filtered = cv2.fastNlMeansDenoisingColored(array, None, h, h, 7, 21)
    return Image.fromarray(filtered)


def _white_balance(image):
    array = np.asarray(image).astype(np.float32)
    hsv = cv2.cvtColor(array.astype(np.uint8), cv2.COLOR_RGB2HSV)
    neutral = hsv[..., 1] < 60
    if float(neutral.mean()) < 0.02:
        return image
    means = array[neutral].mean(axis=0)
    if float(means.max() - means.min()) < 18:
        return image
    target = float(means.mean())
    gains = np.clip(target / np.maximum(means, 1), 0.95, 1.05)
    return Image.fromarray(np.clip(array * gains, 0, 255).astype(np.uint8))


def fidelity(image, quality=None):
    corrected = _white_balance(image)
    sharpness = float((quality or {}).get("sharpness") or 0)
    if sharpness >= 0.28:
        return corrected
    return corrected.filter(ImageFilter.UnsharpMask(radius=1.0, percent=40, threshold=3))


def enhanced(image, strength):
    strength = max(0.0, min(1.0, float(strength)))
    result = image
    result = ImageEnhance.Brightness(result).enhance(1 + 0.06 * strength)
    result = ImageEnhance.Contrast(result).enhance(1 + 0.08 * strength)
    result = ImageEnhance.Color(result).enhance(1 + 0.06 * strength)
    result = ImageEnhance.Sharpness(result).enhance(1 + 0.12 * strength)
    return result


def _upscale_settings(settings):
    merged = dict(UPSCALE_DEFAULTS)
    merged.update({key: settings[key] for key in ("binary", "modelDir", "tile", "timeout")
                   if key in settings})
    binary = Path(merged["binary"])
    model_dir = Path(merged["modelDir"])
    files = [binary, model_dir / "high-fidelity-4x.bin", model_dir / "high-fidelity-4x.param"]
    if not all(path.is_file() for path in files):
        missing = [str(path) for path in files if not path.is_file()]
        raise ProcessingError(
            "本机缺少 Upscayl，无法执行放大步骤。请安装 Upscayl 或改用不放大；"
            f"缺少: {', '.join(missing)}", step="upscale")
    return merged


def _check_cancel(cancel_check):
    if cancel_check and cancel_check():
        raise ProcessingCancelled("处理已取消")


def _upscale_artifact(library, record, destination, options):
    """Reuse a verified prior output, or quarantine an unusable one before retrying."""
    path = Path(library) / destination
    if path.exists():
        try:
            with Image.open(path) as image:
                if image.format != "PNG":
                    raise ValueError("已有放大结果不是 PNG")
                image.load()
                size = list(image.size)
            expected = [value * 2 for value in record["size"]]
            if size != expected:
                raise ValueError("已有放大结果尺寸不符")
            return {"path": destination, "sha256": digest(path), "size": size}
        except Exception:
            path.rename(path.with_name(path.name + ".invalid-" + uuid.uuid4().hex))
    return art_pipeline_processing.upscale_image(library, record, destination, options)


def process_item(store, library, item_id, settings, cancel_check=None):
    """Run crop, conditional upscale, denoise, fidelity, and enhanced in order.

    Every completed step is persisted before the next one starts; a failure leaves the
    earlier versions in place and records the failed step on the item.
    """
    library = Path(library).resolve()
    current = state_module.find_item(store.read(), item_id)
    analysis = current.get("analysis") or {}
    base = base_record(current)
    image = open_image(library, base)
    record = base

    borders = analysis.get("borders") or {}
    border_allowed = (borders.get("confidence", 0) >= 0.75
                      or borders.get("confirmed") is True)
    if (settings.get("trimBorders", True) and borders.get("detected") and border_allowed
            and borders.get("box") != [0.0, 0.0, 1.0, 1.0]):
        _check_cancel(cancel_check)
        image = crop(image, borders["box"])
        record = ensure_version(store, library, item_id, "crop", image, record,
                               {"box": borders["box"]}, "local-crop",
                               evidence={"detectedBox": borders.get("box")})

    upscale = analysis.get("upscale") or {}
    if upscale.get("needed") and settings.get("upscale", "auto") != "never":
        _check_cancel(cancel_check)
        options = _upscale_settings(settings)
        destination = f"versions/{item_id}/{version_id('upscale', record['sha256'], {'scale': 2}, 'upscayl-high-fidelity-2x')}-upscale.png"
        try:
            artifact = _upscale_artifact(
                library, {"path": record["path"], "sha256": record["sha256"],
                          "size": record["size"]}, destination, options)
        except art_pipeline_processing.ProcessingError as error:
            raise ProcessingError(f"放大失败: {error}", step="upscale") from error
        except ValueError as error:
            raise ProcessingError(f"放大不可用: {error}", step="upscale") from error
        record = ensure_version(
            store, library, item_id, "upscale", None,
            {"path": artifact["path"], "sha256": artifact["sha256"], "size": artifact["size"],
             "bytes": None},
            {"scale": 2, "model": options["model"]}, "upscayl-high-fidelity-2x",
            reused=True, output_record=artifact,
            evidence={"log": artifact.get("log"), "receipt": artifact.get("receipt")})
        image = open_image(library, record)

    strength = max(0.0, min(1.0, float(settings.get("denoise", 0.0))))
    if strength > 0:
        _check_cancel(cancel_check)
        image = denoise(image, strength)
        record = ensure_version(store, library, item_id, "denoise", image, record,
                                {"strength": round(strength, 3)}, "local-denoise")
        image = open_image(library, record)

    _check_cancel(cancel_check)
    fidelity_record = None
    if record["versionId"] is None or record["step"] in ("ai-clean", "crop", "upscale", "denoise"):
        corrected = fidelity(image, analysis.get("quality"))
        recipe = {"autoWhiteBalance": "neutral-pixels-only", "unsharp": "only-when-soft"}
        if corrected.tobytes() == image.tobytes():
            fidelity_record = ensure_version(store, library, item_id, "fidelity", None, record,
                                             recipe, "local-fidelity", reused=True)
        else:
            fidelity_record = ensure_version(store, library, item_id, "fidelity", corrected, record,
                                             recipe, "local-fidelity")
        record = fidelity_record
        image = open_image(library, record)
    if fidelity_record is None:
        raise ValueError("保真版步骤没有生成版本")

    _check_cancel(cancel_check)
    color = max(0.0, min(1.0, float(settings.get("color", 0.0))))
    enhanced_image = enhanced(image, color)
    enhanced_record = ensure_version(store, library, item_id, "enhanced", enhanced_image, record,
                                     {"strength": round(color, 3)}, "local-enhanced")

    def mark_current(state):
        target = state_module.find_item(state, item_id)
        target["currentVersions"] = {
            "fidelity": fidelity_record["versionId"],
            "enhanced": enhanced_record["versionId"],
            "at": state_module.now(),
        }
        target["processingRound"] = int(target.get("processingRound") or 0) + 1
        return target["currentVersions"]

    store.mutate(mark_current)
    return [version["versionId"] for version in state_module.find_item(store.read(), item_id)["versions"]]


def thumbnail(library, relative, target):
    """Generate and cache a small WebP preview for a version or original."""
    library = Path(library).resolve()
    source = (library / relative).resolve()
    if not source.is_relative_to(library) or source == library:
        raise ValueError(f"缩略图路径越界: {relative}")
    key = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:24]
    destination = library / "thumbs" / f"{key}.webp"
    if destination.exists():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image.load()
        thumb = image.convert("RGB")
        thumb.thumbnail((target, target), Image.Resampling.LANCZOS)
        temporary = destination.with_name(destination.name + ".part-" + uuid.uuid4().hex)
        try:
            thumb.save(temporary, "WEBP", quality=82, method=4)
            if destination.exists():
                temporary.unlink()
            else:
                os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
    return destination
