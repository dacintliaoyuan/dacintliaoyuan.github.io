"""Conservative image analysis: borders, text risk, quality, and time-of-day suggestion."""

from __future__ import annotations

import numpy as np
from PIL import Image

import cv2


MIN_LONG_EDGE = 3000


def _frame_depth(profile):
    if profile[0] < 215:
        return 0
    for index in range(round(0.06 * len(profile))):
        if profile[index] < 200:
            return index
    return 0


def _border_box(rgb):
    gray = rgb.mean(axis=2)
    rows, cols = gray.mean(axis=1), gray.mean(axis=0)
    top, bottom = _frame_depth(rows), _frame_depth(rows[::-1])
    left, right = _frame_depth(cols), _frame_depth(cols[::-1])
    depths = {"top": top, "bottom": bottom, "left": left, "right": right}
    height, width = gray.shape
    # A pale illustration can look like a frame. Only trust a quiet, uniform band.
    std = {}
    if top:
        std["top"] = _edge_band(gray, top, "top")
    if bottom:
        std["bottom"] = _edge_band(gray, bottom, "bottom")
    if left:
        std["left"] = _edge_band(gray, left, "left")
    if right:
        std["right"] = _edge_band(gray, right, "right")
    trusted = {name: depth for name, depth in depths.items()
               if depth and std.get(name, 99) < 12}
    if not trusted:
        return {"detected": False, "pixels": [0, 0, 0, 0],
                "box": [0.0, 0.0, 1.0, 1.0], "confidence": 0.0,
                "auto": False, "edges": depths}
    inset = max(2, round(0.004 * width))
    left = trusted.get("left", 0)
    right = trusted.get("right", 0)
    top = trusted.get("top", 0)
    bottom = trusted.get("bottom", 0)
    left = left + inset if left else 0
    right = right + inset if right else 0
    top = top + inset if top else 0
    bottom = bottom + inset if bottom else 0
    if left + right >= width * 0.2 or top + bottom >= height * 0.2:
        return {"detected": False, "pixels": [0, 0, 0, 0],
                "box": [0.0, 0.0, 1.0, 1.0], "confidence": 0.0,
                "auto": False, "edges": depths}
    pixels = [left, top, width - right, height - bottom]
    box = [round(left / width, 4), round(top / height, 4),
           round((width - right) / width, 4), round((height - bottom) / height, 4)]
    confidence = 0.9 if all(value < 8 for value in std.values()) else 0.6
    return {"detected": True, "pixels": pixels, "box": box,
            "confidence": confidence, "auto": confidence >= 0.75, "edges": depths}


def _edge_band(gray, depth, side):
    if side == "top":
        band = gray[:depth]
    elif side == "bottom":
        band = gray[-depth:]
    elif side == "left":
        band = gray[:, :depth]
    else:
        band = gray[:, -depth:]
    return float(np.std(band))


def _text_regions(rgb):
    height, width = rgb.shape[:2]
    scale = min(1.0, 1000 / max(width, height))
    small = cv2.resize(rgb, (max(1, round(width * scale)), max(1, round(height * scale))),
                        interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    height, width = small.shape[:2]
    candidates = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if h < max(5, round(0.012 * height)) or h > 0.12 * height:
            continue
        if w < 2 or w / h < 0.2:
            continue
        area = cv2.contourArea(contour)
        if area <= 0 or area / (w * h) > 0.7:
            continue
        density = np.count_nonzero(edges[y:y + h, x:x + w]) / max(1, w * h)
        if not 0.05 <= density <= 0.6:
            continue
        if x <= 1 or y <= 1 or x + w >= width - 2 or y + h >= height - 2:
            continue
        candidates.append({"x": x / width, "y": y / height,
                            "w": w / width, "h": h / height,
                            "density": round(float(density), 3)})
    rows = {}
    for region in candidates:
        key = round((region["y"] + region["h"] / 2) / 0.025)
        rows.setdefault(key, []).append(region)
    groups = []
    for row in rows.values():
        if len(row) < 2:
            continue
        heights = [region["h"] for region in row]
        if np.std(heights) / max(np.mean(heights), 1e-6) > 0.55:
            continue
        line_width = max(region["x"] + region["w"] for region in row) - min(region["x"] for region in row)
        if line_width < 0.08:
            continue
        groups.append(sorted(row, key=lambda region: region["x"]))
    components = sum(len(group) for group in groups)
    if len(groups) >= 2 and components >= 4:
        confidence = min(1.0, 0.55 + components * 0.02)
    elif groups and components >= 2:
        confidence = 0.42
    elif groups and components == 1 and groups[0][0]["w"] > 0.15:
        confidence = 0.4
    else:
        confidence = 0.0
    regions = [region for group in groups for region in group]
    signature = any(region["y"] + region["h"] / 2 > 0.86 and region["w"] < 0.3 for region in regions)
    return {"confidence": round(confidence, 3), "groups": len(groups),
            "components": components, "regions": regions[:12],
            "signatureRisk": signature}


def _time_suggestion(rgb):
    array = rgb.astype(np.float32) / 255.0
    value = float(array.max(axis=2).mean())
    red, green, blue = (float(array[..., index].mean()) for index in range(3))
    warmth = red - blue
    if value < 0.3:
        return {"suggestion": "night", "confidence": 0.7,
                "reason": "画面整体偏暗"}
    if value < 0.62 and warmth > 0.06:
        return {"suggestion": "dusk", "confidence": 0.6,
                "reason": "画面偏暖、亮度中等"}
    if value > 0.52 and blue >= red * 0.9:
        return {"suggestion": "day", "confidence": 0.65,
                "reason": "画面明亮、偏冷色"}
    return {"suggestion": "any", "confidence": 0.45,
            "reason": "看不出明确时段"}


def _quality(rgb):
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    median = cv2.medianBlur(gray, 3)
    noise = float(np.median(np.abs(gray.astype(np.int16) - median.astype(np.int16))) / 255)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    means = rgb.reshape(-1, 3).mean(axis=0)
    return {
        "sharpness": round(min(1.0, sharpness / 900), 3),
        "noise": round(min(1.0, noise * 8), 3),
        "brightness": round(float(means.mean() / 255), 3),
        "saturation": round(float(hsv[..., 1].mean() / 255), 3),
        "colorCast": round(float((means.max() - means.min()) / 255), 3),
    }


def uncertainty_list(analysis):
    borders = analysis.get("borders") or {}
    text = analysis.get("text") or {}
    time = analysis.get("time") or {}
    uncertainties = []
    if borders.get("detected") and not borders.get("auto", False) and not borders.get("confirmed"):
        uncertainties.append({
            "kind": "borders", "confidence": borders.get("confidence"),
            "reason": "边缘区域不够统一；裁切前需要确认，避免裁到画面。",
        })
    if text.get("needed") and text.get("needsConfirmation"):
        uncertainties.append({
            "kind": "text", "confidence": text.get("confidence"),
            "reason": "文字判断不确定；先确认再生成 AI 去字任务。",
        })
    if text.get("signatureRisk"):
        uncertainties.append({
            "kind": "signature", "confidence": 0.5,
            "reason": "底部疑似签名；默认保留，确认后才处理。",
        })
    if time.get("confidence", 1) < 0.5:
        uncertainties.append({
            "kind": "time", "confidence": time.get("confidence"),
            "reason": "时段判断不可靠；可以手动纠正。",
        })
    return uncertainties


def analyze(path):
    with Image.open(path) as image:
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError("只分析单帧静态图片")
        rgb = np.asarray(image.convert("RGB"))
        width, height = image.size
    borders = _border_box(rgb)
    text = _text_regions(rgb)
    quality = _quality(rgb)
    time = _time_suggestion(rgb)
    text_data = {
        **text,
        "needed": text["confidence"] >= 0.35,
        "needsConfirmation": 0.35 <= text["confidence"] < 0.7,
    }
    result = {
        "width": width,
        "height": height,
        "borders": borders,
        "text": text_data,
        "quality": quality,
        "time": time,
        "upscale": {
            "needed": max(width, height) < MIN_LONG_EDGE,
            "reason": (f"长边 {max(width, height)} 小于 {MIN_LONG_EDGE}，"
                       "可按需本机放大") if max(width, height) < MIN_LONG_EDGE else "尺寸足够",
        },
        "contract": {
            "textNeeded": 0.35,
            "textConfirmationBelow": 0.7,
            "borderAuto": 0.75,
            "signatureRiskNeedsConfirmation": True,
            "note": "这些是启发式判断；不确定项必须让用户或 AI 复核，不当作可靠置信度。",
        },
    }
    result["uncertainties"] = uncertainty_list(result)
    return result
