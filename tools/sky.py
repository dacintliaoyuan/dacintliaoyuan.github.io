"""Cloud layers for the opening's sky, generated from the Pexels photos in the blue-sky reference folder.

Each photo is "un-skied" (a smooth clear-sky field is estimated from the blue pixels, every pixel is
measured along the sky->white axis to get a cloud density) and the cloud is repainted between a cool
blue-grey underside and white, so it keeps its volume on the pale Liz-palette sky.

Pexels photos are free to use; the blue-sky author's own processed renders are not used.
"""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

SRC = Path(__file__).resolve().parents[1] / ".local" / "materials" / "collected" / "references" / "blue sky" / "素材"
SHADOW = np.array([176, 200, 220], np.float32) / 255
LIGHT = np.ones(3, np.float32)

# layer -> photo, crop box (shares of width/height), output width, mirror, shading 0..1, density gain
LAYERS = {
    "far": ("pexels-roman-odintsov-8355744.jpg", (0.0, 0.0, 1.0, 0.62), 2400, False, 0.0, 1.8),
    "mid": ("pexels-ebeen-746148.jpg", (0.36, 0.22, 1.0, 1.0), 1700, False, 1.0, 1.0),
    "tower": ("pexels-liuuu-_61-2383408-33709201.jpg", (0.0, 0.30, 1.0, 0.86), 1500, True, 1.0, 1.0),
    "near": ("pexels-liuuu-_61-2383408-33709201.jpg", (0.0, 0.80, 1.0, 1.0), 2400, False, 0.6, 1.2),
}


def load(name, box, width, mirror=False):
    image = Image.open(SRC / name).convert("RGB")
    w, h = image.size
    image = image.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
    image = image.resize((width, round(width * image.height / image.width)), Image.LANCZOS)
    if mirror:
        image = image.transpose(Image.FLIP_LEFT_RIGHT)
    return np.asarray(image, np.float32) / 255


def sky_field(rgb):
    """Smooth estimate of the clear-sky colour behind every pixel (multi-scale normalized convolution)."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    saturation = rgb.max(axis=2) - rgb.min(axis=2)
    # Thin cirrus is blue-dominant too; clear sky is told apart by its low red channel.
    sky = ((b > r + 0.10) & (b >= g) & (r < 0.42) & (rgb.min(axis=2) < 0.78) & (saturation > 0.18)).astype(np.float32)
    size = max(rgb.shape[:2])
    field = np.zeros_like(rgb)
    filled = np.zeros(rgb.shape[:2], bool)
    for share in (0.02, 0.06, 0.15, 0.4):
        sigma = share * size
        weight = cv2.GaussianBlur(sky, (0, 0), sigma)
        estimate = np.dstack([cv2.GaussianBlur(rgb[..., c] * sky, (0, 0), sigma) for c in range(3)])
        estimate /= np.maximum(weight, 1e-6)[..., None]
        take = (weight > 0.08) & ~filled
        field[take] = estimate[take]
        filled |= take
    field[~filled] = np.median(rgb[sky > 0], axis=0) if sky.any() else 0.5
    return field


def density(rgb, gain=1.0):
    sky = sky_field(rgb)
    towards_white = LIGHT - sky
    t = ((rgb - sky) * towards_white).sum(axis=2) / np.maximum((towards_white ** 2).sum(axis=2), 1e-4)
    return cv2.GaussianBlur(np.clip(gain * (t - 0.10) / 0.55, 0, 1) ** 0.9, (0, 0), 0.8)


def cloud_layer(rgb, shading, gain):
    alpha = density(rgb, gain)
    luminance = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    inside = alpha > 0.3
    low, high = np.percentile(luminance[inside], [4, 99]) if inside.any() else (0.4, 1.0)
    shade = np.clip((luminance - low) / max(high - low, 1e-3), 0, 1) ** 0.85
    shade = 1 - shading * (1 - shade)
    return np.dstack([SHADOW + (LIGHT - SHADOW) * shade[..., None], alpha])


def feather(rgba, share=0.08):
    """Fade alpha towards every crop edge so a layer never ends in a straight line."""
    height, width = rgba.shape[:2]
    ramp = lambda n: np.clip(np.minimum(np.arange(n), np.arange(n)[::-1]) / max(1, share * n), 0, 1)
    rgba[..., 3] *= np.outer(ramp(height), ramp(width)) ** 1.5
    return rgba


def build(out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, (photo, box, width, mirror, shading, gain) in LAYERS.items():
        rgba = feather(cloud_layer(load(photo, box, width, mirror), shading, gain))
        image = Image.fromarray((rgba * 255).clip(0, 255).astype(np.uint8), "RGBA")
        image.save(out_dir / f"{name}.webp", quality=82, method=6)
        written[name] = {"file": f"sky/{name}.webp", "w": image.width, "h": image.height}
    return written
