"""Read-only, bounded image triage. Every result is a proposal for human review."""

import hashlib
import heapq
import io
import math
import re
import struct
import warnings
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

from PIL import Image, ImageChops, ImageOps, ImageStat, UnidentifiedImageError


DEFAULT_PARAMETERS = {
    "maxItems": 500, "maxComparisons": 50_000, "maxSimilarCandidates": 100,
    "maxSourceBytes": 100 * 1024 * 1024, "maxDecodedPixels": 50_000_000,
    "sampleSize": 32, "similarHashDistance": 6, "similarMaxRgbMae": 0.06,
    "similarAspectTolerance": 0.05, "monochromeMeanChroma": 0.025,
    "monochromeGrayRange": 8, "monochromeMinGrayFraction": 0.95,
    "lowResolutionMinLongEdge": 1600, "lowResolutionMinShortEdge": 900,
}
INTEGER_LIMITS = {
    "maxItems": (0, 2000), "maxComparisons": (0, 100_000),
    "maxSimilarCandidates": (0, 1000), "maxSourceBytes": (1, 200 * 1024 * 1024),
    "maxDecodedPixels": (1, 100_000_000), "sampleSize": (8, 128),
    "similarHashDistance": (0, 64), "monochromeGrayRange": (0, 255),
    "lowResolutionMinLongEdge": (1, 20_000), "lowResolutionMinShortEdge": (1, 20_000),
}


def _parameters(state):
    settings = state.get("settings", {})
    if not isinstance(settings, dict) or not isinstance(settings.get("analysis", {}), dict):
        raise ValueError("settings.analysis 必须是参数对象")
    overrides = settings.get("analysis", {})
    unknown = set(overrides).difference(DEFAULT_PARAMETERS)
    if unknown:
        raise ValueError("未知分析参数: " + ", ".join(sorted(unknown)))
    parameters = {**DEFAULT_PARAMETERS, **overrides}
    for key, value in parameters.items():
        if key in INTEGER_LIMITS:
            lower, upper = INTEGER_LIMITS[key]
            valid = type(value) is int and lower <= value <= upper
        else:
            valid = type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
        if not valid:
            raise ValueError(f"分析参数超出允许范围: {key}")
    if parameters["lowResolutionMinShortEdge"] > parameters["lowResolutionMinLongEdge"]:
        raise ValueError("短边阈值不能大于长边阈值")
    return parameters


def _identity(value):
    if (not isinstance(value, str) or not value.strip() or value != value.strip()
            or len(value) > 200 or any(ord(char) < 32 for char in value)):
        raise ValueError("素材 id 必须是 1–200 字符的非空文本，不含控制字符或首尾空白")
    return value


def _pixel_hash(image):
    """Hash dimensions and row-major pixels in bounded strips instead of one copy."""
    checksum = hashlib.sha256(struct.pack(">II", *image.size))
    for top in range(0, image.height, 256):
        with image.crop((0, top, image.width, min(top + 256, image.height))) as strip:
            checksum.update(strip.tobytes())
    return checksum.hexdigest()


def _dhash(sample):
    with sample.convert("L") as gray, gray.resize((9, 8), Image.Resampling.BILINEAR) as small:
        pixels = small.tobytes()
    value = 0
    for row in range(8):
        for column in range(8):
            value = (value << 1) | (pixels[row * 9 + column] > pixels[row * 9 + column + 1])
    return value


def _inspect(item, library, parameters):
    record = item.get("source")
    if not isinstance(record, dict):
        raise ValueError("缺少 source 素材记录；不会自动选择替代版本")
    relative, expected_hash, expected_size = record.get("path"), record.get("sha256"), record.get("size")
    if (not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative
            or PurePosixPath(relative).is_absolute() or any(part in {"", ".", ".."} for part in relative.split("/"))):
        raise ValueError("source.path 必须是图库内的相对 POSIX 路径")
    path = (library / relative).resolve()
    if path == library or not path.is_relative_to(library):
        raise ValueError("source.path 已越出指定图库")
    if (not isinstance(expected_hash, str) or not re.fullmatch("[a-f0-9]{64}", expected_hash)
            or not isinstance(expected_size, list) or len(expected_size) != 2
            or any(type(axis) is not int or axis <= 0 for axis in expected_size)):
        raise ValueError("source 的 SHA-256 或尺寸不合法")
    if not path.is_file():
        raise ValueError("source 文件不存在或不是普通文件")
    if path.stat().st_size > parameters["maxSourceBytes"]:
        raise ValueError("source 文件超过分析大小上限")
    with path.open("rb") as stream:
        data = stream.read(parameters["maxSourceBytes"] + 1)
    if len(data) > parameters["maxSourceBytes"]:
        raise ValueError("source 文件超过分析大小上限")
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError("source 的 SHA-256 已变化，旧记录失效")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as header:
            if list(header.size) != expected_size:
                raise ValueError("source 的图片尺寸与记录不符")
            if header.width * header.height > parameters["maxDecodedPixels"]:
                raise ValueError("source 超过分析像素上限")
            if getattr(header, "n_frames", 1) != 1:
                raise ValueError("分析仅支持完整解码的单帧静态图片")
            header.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            with ImageOps.exif_transpose(image) as upright, upright.convert("RGBA") as rgba:
                with rgba.convert("RGB") as rgb, rgba.getchannel("A") as alpha:
                    rgb_hash = _pixel_hash(rgb)
                    alpha_hash = None if alpha.getextrema() == (255, 255) else _pixel_hash(alpha)
                size = list(upright.size)
                with rgba.resize((parameters["sampleSize"],) * 2, Image.Resampling.BILINEAR) as resized:
                    with Image.new("RGBA", resized.size, "white") as white:
                        white.alpha_composite(resized)
                        sample = white.convert("RGB")
    sampled_bytes = sample.tobytes()
    ranges = [max(pixel) - min(pixel) for pixel in zip(sampled_bytes[::3], sampled_bytes[1::3], sampled_bytes[2::3])]
    mean_chroma = sum(ranges) / (len(ranges) * 255)
    gray_fraction = sum(value <= parameters["monochromeGrayRange"] for value in ranges) / len(ranges)
    return {
        "id": item["id"], "path": relative, "sha256": expected_hash, "size": list(expected_size),
        "pixelSize": size, "rgbSha256": rgb_hash, "alphaSha256": alpha_hash,
        "meanChroma": mean_chroma, "grayFraction": gray_fraction,
        "dhash": _dhash(sample), "sample": sample,
    }


def _pixel_key(image):
    return tuple(image["pixelSize"]), image["rgbSha256"], image["alphaSha256"]


def _exact_groups(images):
    grouped = defaultdict(list)
    for image in images:
        grouped[_pixel_key(image)].append(image)
    result = []
    for group in grouped.values():
        if len(group) < 2:
            continue
        file_groups = defaultdict(list)
        for image in group:
            file_groups[image["sha256"]].append(image["id"])
        same_file = len(file_groups) == 1
        result.append({
            "ids": [image["id"] for image in group],
            "type": "file_sha256" if same_file else "rgb_pixels",
            "evidence": {
                "pixelSize": group[0]["pixelSize"], "rgbSha256": group[0]["rgbSha256"],
                "alphaSha256": group[0]["alphaSha256"], "allFilesIdentical": same_file,
                "fileSha256Groups": [{"sha256": checksum, "ids": ids} for checksum, ids in file_groups.items()],
            },
            "recommendation": "文件字节完全相同，请自行选择保留版本。" if same_file else (
                "方向校正后的 RGB 像素及透明度相同，文件编码不同；请自行选择保留版本。"),
        })
    return result


def _similar_pairs(images, parameters):
    comparisons = found = 0
    retained = []
    cap = parameters["maxSimilarCandidates"]
    limit = parameters["maxComparisons"] if cap else 0
    total = len(images) * (len(images) - 1) // 2
    for left_index, left in enumerate(images):
        for right_index in range(left_index + 1, len(images)):
            if comparisons >= limit:
                break
            comparisons += 1
            right = images[right_index]
            if _pixel_key(left) == _pixel_key(right):
                continue
            left_ratio = left["pixelSize"][0] / left["pixelSize"][1]
            right_ratio = right["pixelSize"][0] / right["pixelSize"][1]
            aspect_difference = max(left_ratio, right_ratio) / min(left_ratio, right_ratio) - 1
            distance = (left["dhash"] ^ right["dhash"]).bit_count()
            if aspect_difference > parameters["similarAspectTolerance"] or distance > parameters["similarHashDistance"]:
                continue
            with ImageChops.difference(left["sample"], right["sample"]) as difference:
                mae = sum(ImageStat.Stat(difference).mean) / (3 * 255)
            if mae > parameters["similarMaxRgbMae"]:
                continue
            found += 1
            candidate = {
                "ids": [left["id"], right["id"]],
                "evidence": {"hashAlgorithm": "dhash-64", "hashDistance": distance,
                             "normalizedRgbMae": round(mae, 6), "aspectRatioDifference": round(aspect_difference, 6)},
                "recommendation": "近似重复提名；请对照裁切、文字和清晰度自行选择，不自动删除。",
            }
            # Keep the best bounded number, with input order as a stable tie breaker.
            rank = (-distance, -mae, -aspect_difference, -left_index, -right_index)
            entry = (rank, candidate)
            if len(retained) < cap:
                heapq.heappush(retained, entry)
            elif rank > retained[0][0]:
                heapq.heapreplace(retained, entry)
        if comparisons >= limit:
            break
    return [entry[1] for entry in sorted(retained, reverse=True)], {
        "totalPossiblePairs": total, "comparedPairs": comparisons, "matchingPairs": found,
        "returnedPairs": len(retained), "comparisonLimitReached": comparisons < total,
        "candidateLimitReached": found > cap,
    }


def analyze(state, library):
    """Validate and inspect only listed sources; never modify files or decisions.

    Exact groups use full decoded pixels. Similarity is a bounded pair search on
    thumbnails, and can miss different crops or heavily lettered versions. Errors
    are item-specific; invalid records never enter comparisons through a fallback.
    """
    if not isinstance(state, dict) or not isinstance(state.get("items"), list):
        raise ValueError("state.items 必须是素材数组")
    root = Path(library).resolve()
    if not root.is_dir():
        raise ValueError("指定图库目录不存在")
    parameters = _parameters(state)
    result = {"schemaVersion": 1, "exactDuplicates": [], "similarCandidates": [],
              "monochromeCandidates": [], "lowResolution": [], "errors": [], "parameters": parameters.copy()}
    identities = Counter(item.get("id") for item in state["items"]
                         if isinstance(item, dict) and isinstance(item.get("id"), str))
    images = []
    try:
        for index, item in enumerate(state["items"]):
            identity = item.get("id") if isinstance(item, dict) else None
            try:
                if index >= parameters["maxItems"]:
                    raise ValueError("超出本次 maxItems 上限；此项尚未分析")
                if not isinstance(item, dict):
                    raise ValueError("素材条目必须是对象")
                _identity(identity)
                if identities[identity] != 1:
                    raise ValueError("素材 id 重复，无法唯一关联分析证据")
                image = _inspect(item, root, parameters)
                images.append(image)
            except (ValueError, OSError, TypeError, SyntaxError, UnidentifiedImageError,
                    Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
                result["errors"].append({"ids": [identity] if isinstance(identity, str) else [],
                                         "itemIndex": index,
                                         "code": "analysis_limit" if index >= parameters["maxItems"] else "source_invalid",
                                         "message": str(error)})
                continue
            if (image["meanChroma"] <= parameters["monochromeMeanChroma"]
                    and image["grayFraction"] >= parameters["monochromeMinGrayFraction"]):
                result["monochromeCandidates"].append({
                    "ids": [identity], "evidence": {"meanChroma": round(image["meanChroma"], 6),
                                                       "grayFraction": round(image["grayFraction"], 6)},
                    "recommendation": "黑白或低饱和候选；浅色彩图也可能命中，请人工核对后选择。",
                })
            short, long = sorted(image["size"])
            if short < parameters["lowResolutionMinShortEdge"] or long < parameters["lowResolutionMinLongEdge"]:
                result["lowResolution"].append({
                    "ids": [identity], "evidence": {"size": image["size"], "shortEdge": short, "longEdge": long},
                    "recommendation": "尺寸低于当前提示阈值；请按主页展示需求决定是否查找更大版本或放大。",
                })
        result["exactDuplicates"] = _exact_groups(images)
        result["similarCandidates"], pair_summary = _similar_pairs(images, parameters)
        result["parameters"].update({
            "scope": "仅 state.items[].source；不扫描图库目录，不改选择或原图。",
            "pixelNormalization": "EXIF 方向校正后比较 RGB，非完全不透明时另比 alpha；不转换 ICC 色彩配置。",
            "sampleNormalization": "缩为 sampleSize 方图并在白底合成；黑白与近似指标只作提名。",
            "complexity": "完整解码最多 maxItems 张；近似比较最多 maxComparisons 对，每对只比较小图。",
            "inputItems": len(state["items"]), "analyzedItems": len(images), "similarity": pair_summary,
        })
        return result
    finally:
        for image in images:
            image["sample"].close()
