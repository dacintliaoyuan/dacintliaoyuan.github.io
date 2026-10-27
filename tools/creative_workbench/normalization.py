"""Deterministic delivery normalization: keep the original, scale proportionally, pad transparently."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

from PIL import Image, ImageChops

from . import (
    CreativeError,
    digest_bytes,
    now,
    write_bytes_atomic,
    write_json_atomic,
)

SCHEMA_VERSION = 1
RESAMPLING = {"lanczos": Image.Resampling.LANCZOS, "nearest": Image.Resampling.NEAREST}


def decode(data, label="图片", require_png=False):
    """Decode one image; the original may be any format the tool wrote, the delivery is PNG."""
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = (probe.format or "").upper()
            if require_png and fmt != "PNG":
                raise CreativeError(f"{label}不是实际 PNG")
            if getattr(probe, "n_frames", 1) != 1:
                raise CreativeError(f"{label}必须是单帧图片")
            probe.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            return image.convert("RGBA"), fmt
    except CreativeError:
        raise
    except Exception as error:
        raise CreativeError(f"{label}无法完整解码: {error}") from error


def encode(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _target(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise CreativeError("目标尺寸必须是两个正整数")
    result = []
    for part in value:
        if isinstance(part, bool) or not isinstance(part, int) or part <= 0:
            raise CreativeError("目标尺寸必须是两个正整数")
        result.append(part)
    return result


def _fit(image, target_w, target_h, resampling):
    width, height = image.size
    if width == target_w and height == target_h:
        return image.copy(), 1.0, [0, 0, 0, 0], [width, height], "none"
    scale = min(target_w / width, target_h / height)
    scaled_w = max(1, min(target_w, round(width * scale)))
    scaled_h = max(1, min(target_h, round(height * scale)))
    resized = image.resize((scaled_w, scaled_h), RESAMPLING[resampling])
    canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    left = (target_w - scaled_w) // 2
    top = (target_h - scaled_h) // 2
    canvas.alpha_composite(resized, (left, top))
    return (canvas, round(min(scaled_w / width, scaled_h / height), 6),
            [left, top, target_w - scaled_w - left, target_h - scaled_h - top],
            [scaled_w, scaled_h], resampling)


def normalize(original_bytes, target_size, require_alpha=True, resampling="lanczos",
              source_bytes=None, mask_bytes=None):
    """Return the delivery PNG and a record; never stretch, crop, or overwrite the original."""
    if resampling not in RESAMPLING:
        raise CreativeError("缩放方式只能是 lanczos 或 nearest")
    generated, generated_format = decode(original_bytes, "生成原图")
    extra = {}
    image = generated
    if source_bytes is not None or mask_bytes is not None:
        if source_bytes is None or mask_bytes is None:
            raise CreativeError("局部修补需要同时提供输入原图和修改区遮罩")
        source_image, source_format = decode(source_bytes, "输入原图")
        mask_image, _ = decode(mask_bytes, "修改区遮罩")
        if source_image.size != mask_image.size:
            raise CreativeError("输入原图和遮罩必须同尺寸")
        aligned, alignment_scale, alignment_padding, aligned_size, alignment_method = _fit(
            generated, source_image.width, source_image.height, resampling)
        binary = mask_image.convert("L").point(lambda value: 255 if value > 0 else 0)
        image = Image.composite(aligned, source_image, binary)
        outside = Image.composite(source_image, image, binary)
        if ImageChops.difference(outside, source_image).getbbox() is not None:
            raise CreativeError("遮罩外像素发生变化；请重新合成")
        extra = {
            "sourceSha256": digest_bytes(source_bytes),
            "sourceSize": list(source_image.size),
            "sourceFormat": source_format,
            "maskSha256": digest_bytes(mask_bytes),
            "maskSize": list(mask_image.size),
            "alignedSize": aligned_size,
            "alignmentScale": alignment_scale,
            "alignmentPadding": alignment_padding,
            "alignmentResampling": alignment_method,
            "outsideUnchanged": True,
        }
    target_w, target_h = _target(target_size)
    delivery, scale, padding, scaled_size, method = _fit(
        image, target_w, target_h, resampling)
    alpha = image.getchannel("A")
    has_alpha = alpha.getextrema()[0] < 255
    if require_alpha and not has_alpha:
        raise CreativeError("生成原图缺少透明像素；透明补边不能替代图案本身的透明背景")
    payload = encode(delivery)
    record = {
        "schemaVersion": SCHEMA_VERSION,
        "originalSha256": digest_bytes(original_bytes),
        "originalSize": [generated.width, generated.height],
        "originalFormat": generated_format,
        "deliverySha256": digest_bytes(payload),
        "deliverySize": [target_w, target_h],
        "deliveryFormat": "PNG",
        "scaledSize": scaled_size,
        "scale": scale,
        "padding": padding,
        "cropped": False,
        "stretch": False,
        "resampling": method,
        "hasAlpha": has_alpha,
        "createdAt": now(),
        **extra,
    }
    return {"bytes": payload, "record": record}


def composite_region(original_bytes, generated_bytes, mask_bytes, require_alpha=True):
    """Composite only inside the mask; outside pixels must stay exactly the original."""
    original, original_format = decode(original_bytes, "原图")
    generated, _ = decode(generated_bytes, "生成图")
    mask, _ = decode(mask_bytes, "区域遮罩")
    if original.size != generated.size or original.size != mask.size:
        raise CreativeError("原图、生成图和区域遮罩必须同尺寸")
    binary = mask.convert("L").point(lambda value: 255 if value > 0 else 0)
    result = Image.composite(generated, original, binary)
    outside = Image.composite(original, result, binary)
    if ImageChops.difference(outside, original).getbbox() is not None:
        raise CreativeError("区域外像素发生变化；请重新合成")
    alpha = result.getchannel("A")
    has_alpha = alpha.getextrema()[0] < 255
    if require_alpha and not has_alpha:
        raise CreativeError("合成结果缺少透明像素")
    payload = encode(result)
    record = {
        "schemaVersion": SCHEMA_VERSION,
        "originalSha256": digest_bytes(original_bytes),
        "originalSize": list(original.size),
        "originalFormat": original_format,
        "generatedSha256": digest_bytes(generated_bytes),
        "maskSha256": digest_bytes(mask_bytes),
        "deliverySha256": digest_bytes(payload),
        "deliverySize": list(result.size),
        "deliveryFormat": "PNG",
        "outsideUnchanged": True,
        "hasAlpha": has_alpha,
        "createdAt": now(),
    }
    return {"bytes": payload, "record": record}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="把生成原图整理成交付尺寸：等比缩放、透明补边，不拉伸、不裁切、不覆盖原图。")
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--source", type=Path,
                        help="局部修补的输入原图；必须与 --mask 同时提供")
    parser.add_argument("--mask", type=Path,
                        help="局部修补的修改区遮罩；必须与 --source 同时提供")
    parser.add_argument("--size", required=True, help="交付尺寸，例如 350x512")
    parser.add_argument("--resampling", choices=("lanczos", "nearest"), default="lanczos")
    parser.add_argument("--no-alpha", action="store_true")
    parser.add_argument("--record", type=Path)
    args = parser.parse_args(argv)
    original = args.original.resolve()
    result = args.result.resolve()
    source = args.source.resolve() if args.source else None
    mask = args.mask.resolve() if args.mask else None
    record_path = args.record.resolve() if args.record else None
    if (source is None) != (mask is None):
        raise CreativeError("--source 和 --mask 必须同时提供")
    if original == result:
        raise CreativeError("交付图不能覆盖生成原图")
    for label, path in (("输入原图", source), ("修改区遮罩", mask)):
        if path and path == original:
            raise CreativeError(f"{label}不能与生成原图同路径")
        if path and path == result:
            raise CreativeError(f"{label}不能与交付图同路径")
    if record_path and record_path in (original, result, source, mask):
        raise CreativeError("规格记录不能覆盖生成原图、交付图、输入原图或遮罩")
    if not original.is_file():
        raise CreativeError(f"找不到生成原图: {original}")
    for label, path in (("输入原图", source), ("修改区遮罩", mask)):
        if path and not path.is_file():
            raise CreativeError(f"找不到{label}: {path}")
    try:
        width, height = [int(part) for part in args.size.lower().replace("×", "x").split("x")]
    except ValueError as error:
        raise CreativeError("--size 必须是 WxH") from error
    outcome = normalize(
        original.read_bytes(), [width, height],
        require_alpha=not args.no_alpha, resampling=args.resampling,
        source_bytes=source.read_bytes() if source else None,
        mask_bytes=mask.read_bytes() if mask else None)
    write_bytes_atomic(result, outcome["bytes"])
    record = outcome["record"]
    record["originalPath"] = str(original)
    record["deliveryPath"] = str(result)
    if source:
        record["sourcePath"] = str(source)
    if mask:
        record["maskPath"] = str(mask)
    if record_path:
        write_json_atomic(record_path, record)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
