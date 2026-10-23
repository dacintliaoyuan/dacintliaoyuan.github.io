"""Deterministic local image operations; GPT edits are supplied, never generated here."""

import json
import math
import os
import shutil
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from PIL import Image

from prepare_scenes import digest, image_record, local_path


MODEL = "high-fidelity-4x"


class ProcessingError(RuntimeError):
    """A failed inference with durable, task-local diagnostic paths."""

    def __init__(self, message, *, log_path=None, receipt_path=None, returncode=None):
        super().__init__(message)
        self.log_path = log_path
        self.receipt_path = receipt_path
        self.returncode = returncode


def _root(library):
    root = Path(library).resolve()
    if not root.is_dir():
        raise ValueError(f"图库目录不存在: {root}")
    return root


def _inside(root, path):
    return local_path(root, str(path))


def inspect_image(library, path):
    """Return a canonical artifact after decoding the complete static image."""
    root = _root(library)
    path = _inside(root, path)
    before = digest(path)
    with Image.open(path) as image:
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError(f"素材必须为单帧静态图片: {path}")
        image.verify()
    with Image.open(path) as image:
        image.load()
    record = image_record(root, path)
    if record["sha256"] != before:
        raise ValueError(f"读取期间图片已变化: {record['path']}")
    return record


def _artifact(root, record):
    if not isinstance(record, dict):
        raise ValueError("素材记录必须为对象")
    try:
        path, expected_hash, size = record["path"], record["sha256"], record["size"]
    except KeyError as error:
        raise ValueError(f"素材记录缺少字段: {error.args[0]}") from error
    if (not isinstance(path, str) or not isinstance(expected_hash, str)
            or len(expected_hash) != 64 or any(c not in "0123456789abcdef" for c in expected_hash)
            or not isinstance(size, list) or len(size) != 2
            or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in size)):
        raise ValueError("素材记录的路径、SHA256 或尺寸不合法")
    source = _inside(root, path)
    if source.relative_to(root).as_posix() != path:
        raise ValueError("素材记录路径必须为图库内的相对 POSIX 路径")
    actual = inspect_image(root, source)
    if any(actual[key] != record[key] for key in ("path", "sha256", "size")):
        raise ValueError(f"素材内容或尺寸已变化: {path}")
    return source


def _unchanged(path, expected_hash):
    if digest(path) != expected_hash:
        raise ValueError(f"处理期间输入已变化: {path.name}")


def _destination(root, destination, *, png=False):
    destination = _inside(root, destination)
    if os.path.lexists(destination):
        raise FileExistsError(f"输出已存在，不覆盖: {destination}")
    if png and destination.suffix.lower() != ".png":
        raise ValueError("裁剪、局部合成和放大结果必须保存为 PNG")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Re-resolve after making parents, including any existing directory links.
    return _inside(root, destination)


@contextmanager
def _work_directory(root, destination, *, native=False):
    # Upscayl's Windows binary crashes beyond MAX_PATH even when Python can
    # access the file. Inference gets its own short directory in this library.
    parent = root if native else destination.parent
    work = parent / f".{destination.stem}-work-{uuid.uuid4().hex}"
    _inside(root, work)
    if native and os.name == "nt" and len(str(work / "high-fidelity.partial.png")) >= 240:
        raise ValueError("图库根路径过长，无法给本机Upscayl提供短临时路径；请使用较短的图库路径")
    work.mkdir()
    try:
        yield work
    finally:
        # Only this freshly created, private directory is eligible for cleanup.
        _inside(root, work)
        shutil.rmtree(work)


def _publish(root, temporary, destination):
    _inside(root, temporary)
    _inside(root, destination)
    # Same-filesystem hard linking is atomic and refuses an existing destination
    # on both Windows and POSIX; rename alone can overwrite on POSIX.
    os.link(temporary, destination)


def _result(record, destination, root, **metadata):
    return {**record, "path": destination.relative_to(root).as_posix(), **metadata}


def crop_image(library, source, bounds, destination):
    """Crop exact integer source pixels without overwriting a prior output."""
    root = _root(library)
    source_path = _artifact(root, source)
    if (not isinstance(bounds, (list, tuple)) or len(bounds) != 4
            or any(isinstance(v, bool) or not isinstance(v, int) for v in bounds)):
        raise ValueError("裁剪范围必须为四个整数 [left, top, right, bottom]")
    left, top, right, bottom = bounds
    width, height = source["size"]
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError("裁剪范围超出源图或为空")
    destination = _destination(root, destination, png=True)
    with _work_directory(root, destination) as work:
        temporary = work / "cropped.png"
        with Image.open(source_path) as image:
            image.load()
            image.crop(tuple(bounds)).save(temporary, format="PNG")
        candidate = inspect_image(root, temporary)
        _unchanged(source_path, source["sha256"])
        _publish(root, temporary, destination)
    return _result(candidate, destination, root, method="pixel-crop",
                   inputSha256=source["sha256"], bounds=list(bounds))


def composite_clean(library, source, edited, mask, destination):
    """Import a supplied edit, or composite only a same-size L-mask region."""
    root = _root(library)
    source_path = _artifact(root, source)
    edited_path = _inside(root, edited)
    edited_record = inspect_image(root, edited_path)
    mask_path = _artifact(root, mask) if mask is not None else None
    if mask_path is not None:
        if mask["size"] != source["size"] or edited_record["size"] != source["size"]:
            raise ValueError("遮罩、编辑图和源图必须同尺寸；请先人工核对对齐")
        with Image.open(mask_path) as image:
            if image.mode != "L":
                raise ValueError("局部合成遮罩必须为 L 灰度图")
            image.load()
            alpha = image.copy()
        # A mask must retain at least one exact source pixel and edit another.
        minimum, maximum = alpha.getextrema()
        if maximum == 0 or minimum > 0:
            raise ValueError("遮罩不能为空或覆盖整张图")
    destination = _destination(root, destination, png=mask_path is not None)
    with _work_directory(root, destination) as work:
        temporary = work / "clean.png"
        if mask_path is None:
            shutil.copyfile(edited_path, temporary)
        else:
            with Image.open(source_path) as original, Image.open(edited_path) as replacement:
                original.load()
                replacement.load()
                # RGB/RGBA preserve source channel values; other image modes
                # need an explicit conversion decision rather than silent loss.
                if original.mode not in ("RGB", "RGBA", "L"):
                    raise ValueError("局部合成源图仅支持 RGB、RGBA 或 L 模式")
                converted = replacement.convert(original.mode)
                Image.composite(converted, original, alpha).save(temporary, format="PNG")
        candidate = inspect_image(root, temporary)
        _unchanged(source_path, source["sha256"])
        _unchanged(edited_path, edited_record["sha256"])
        if mask_path is not None:
            _unchanged(mask_path, mask["sha256"])
        _publish(root, temporary, destination)
    metadata = {"method": "gpt-import" if mask_path is None else "gpt-masked-alpha",
                "inputSha256": source["sha256"], "editedSha256": edited_record["sha256"]}
    if mask_path is not None:
        metadata["maskSha256"] = mask["sha256"]
    return _result(candidate, destination, root, **metadata)


def _upscale_settings(settings):
    if not isinstance(settings, dict):
        raise ValueError("Upscayl 设置必须为对象")
    if any(not isinstance(key, str) for key in settings):
        raise ValueError("Upscayl 设置键必须为文本")
    unknown = set(settings) - {"binary", "modelDir", "model", "scale", "tile", "timeout"}
    if unknown:
        raise ValueError(f"未知 Upscayl 设置: {', '.join(sorted(unknown))}")
    scale = settings.get("scale", 2)
    if (settings.get("model", MODEL) != MODEL or isinstance(scale, bool)
            or not isinstance(scale, int) or scale != 2):
        raise ValueError("当前流程只采用 High Fidelity 模型与 2 倍放大")
    tile, timeout = settings.get("tile", 256), settings.get("timeout", 240)
    if isinstance(tile, bool) or not isinstance(tile, int) or tile <= 0:
        raise ValueError("tile 必须为正整数")
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout <= 0):
        raise ValueError("timeout 必须为有限正数")
    try:
        binary = Path(settings["binary"]).resolve()
        model_directory = Path(settings["modelDir"]).resolve()
    except (KeyError, TypeError) as error:
        raise ValueError("必须指定 Upscayl binary 和 modelDir") from error
    files = [binary, *(model_directory / f"{MODEL}.{extension}" for extension in ("bin", "param"))]
    for path in files:
        if not path.is_file():
            raise ValueError(f"缺少 Upscayl 本机文件: {path}")
    return {"binary": str(binary), "modelDir": str(model_directory), "model": MODEL,
            "scale": 2, "tile": tile, "timeout": timeout}, files


def _receipt(path, value):
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def upscale_image(library, source, destination, settings):
    """Run the configured local Upscayl binary with durable inference evidence."""
    root = _root(library)
    source_path = _artifact(root, source)
    settings, tool_files = _upscale_settings(settings)
    destination = _destination(root, destination, png=True)
    tool_hashes = [digest(path) for path in tool_files]
    token = uuid.uuid4().hex
    log_path = destination.parent / f"{destination.stem}-upscayl-{token}.log"
    receipt_path = log_path.with_suffix(".json")
    details = {"method": "upscayl-high-fidelity-2x", "inputSha256": source["sha256"],
               "binarySha256": tool_hashes[0],
               "modelFiles": [{"path": str(path), "sha256": value}
                              for path, value in zip(tool_files[1:], tool_hashes[1:])],
               "settings": settings, "exitCode": None,
               "log": log_path.relative_to(root).as_posix(),
               "receipt": receipt_path.relative_to(root).as_posix()}
    started = time.monotonic()
    with _work_directory(root, destination, native=True) as work:
        temporary = work / "high-fidelity.partial.png"
        with Image.open(source_path) as image:
            source_format = image.format
        suffix = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp", "BMP": ".bmp"}.get(source_format)
        if suffix:
            inference_source = work / ("input" + suffix)
            shutil.copyfile(source_path, inference_source)
            _unchanged(inference_source, source["sha256"])
        else:
            inference_source = work / "input.png"
            with Image.open(source_path) as image:
                image.load()
                image.save(inference_source, format="PNG")
        _unchanged(source_path, source["sha256"])
        details["inferenceInputSha256"] = digest(inference_source)
        command = [settings["binary"], "-i", str(inference_source), "-o", str(temporary),
                   "-m", settings["modelDir"], "-n", MODEL, "-z", "4", "-s", "2",
                   "-t", str(settings["tile"]), "-j", "1:1:1", "-f", "png"]
        details["command"] = command
        _receipt(receipt_path, {**details, "status": "running"})
        try:
            with log_path.open("xb") as log:
                log.write((json.dumps(details, ensure_ascii=False) + "\n").encode("utf-8"))
                log.flush()
                # subprocess.run kills and waits for its child on timeout or
                # cancellation; stdout/stderr handles are closed by this scope.
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                        timeout=settings["timeout"], check=False,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            details["exitCode"] = result.returncode
            if result.returncode != 0:
                raise ProcessingError(f"Upscayl 退出码 {result.returncode}", returncode=result.returncode)
            candidate = inspect_image(root, temporary)
            with Image.open(temporary) as image:
                if image.format != "PNG":
                    raise ValueError("Upscayl 输出必须为实际 PNG 文件")
            expected = [size * 2 for size in source["size"]]
            if candidate["size"] != expected:
                raise ValueError(f"Upscayl 输出尺寸错误: {candidate['size']}，预期 {expected}")
            _unchanged(source_path, source["sha256"])
            _unchanged(inference_source, details["inferenceInputSha256"])
            for path, value in zip(tool_files, tool_hashes):
                _unchanged(path, value)
            _publish(root, temporary, destination)
            details["seconds"] = round(time.monotonic() - started, 3)
            artifact = _result(candidate, destination, root, **details)
            _receipt(receipt_path, {**details, "status": "completed", "output": artifact})
            return artifact
        except BaseException as error:
            details["seconds"] = round(time.monotonic() - started, 3)
            status = "cancelled" if isinstance(error, (KeyboardInterrupt, SystemExit)) else "failed"
            failure = {**details, "status": status, "errorType": type(error).__name__, "error": str(error)}
            _receipt(receipt_path, failure)
            with log_path.open("ab") as log:
                log.write(("\n" + json.dumps(failure, ensure_ascii=False) + "\n").encode("utf-8"))
            if status == "cancelled":
                raise
            raise ProcessingError(f"放大未完成: {error}；日志: {details['log']}",
                                  log_path=log_path, receipt_path=receipt_path,
                                  returncode=details["exitCode"]) from error
