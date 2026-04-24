"""Build a black-on-white logo PNG from the source artwork (e.g. gold on dark)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image


def ensure_black_logo(source: Path, target: Path, lum_threshold: int = 80) -> None:
    if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
        return
    im = Image.open(source).convert("RGB")
    w, h = im.size
    out = Image.new("RGB", (w, h), (255, 255, 255))
    src = im.load()
    dst = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b = src[x, y]
            lum = (r + g + b) // 3
            if lum > lum_threshold:
                dst[x, y] = (0, 0, 0)
            else:
                dst[x, y] = (255, 255, 255)
    target.parent.mkdir(parents=True, exist_ok=True)
    out.save(target, format="PNG")
