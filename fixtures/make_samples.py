"""產生範例影像到 sample_images/(供 app 預設載入與 e2e)。固定種子、可重現。
跑法:python fixtures/make_samples.py"""
import os
import numpy as np
from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_images")
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(42)


def rgb_defects(i):
    w, h = 1200, 900
    img = Image.new("RGB", (w, h), (15, 18, 28))
    d = ImageDraw.Draw(img)
    for x in range(0, w, 150):
        d.line([(x, 0), (x, h)], fill=(40, 44, 60))
    for y in range(0, h, 150):
        d.line([(0, y), (w, y)], fill=(40, 44, 60))
    for _ in range(3 + i):
        cx, cy = int(rng.integers(120, w - 120)), int(rng.integers(120, h - 120))
        r = int(rng.integers(8, 30))
        col = (0, 200, 0) if rng.random() > 0.5 else (210, 90, 0)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    d.text((10, 10), f"lot42 frame {i:03d}", fill=(180, 180, 200))
    img.save(os.path.join(OUT, f"lot42_frame_{i:03d}.png"))


def gray16(i):
    w, h = 1000, 1000
    base = rng.normal(20000, 1500, (h, w)).clip(0, 65535).astype(np.uint16)
    for _ in range(2):
        cy, cx = int(rng.integers(60, h - 60)), int(rng.integers(60, w - 60))
        base[cy - 15:cy + 15, cx - 15:cx + 15] = 60000
    Image.fromarray(base).save(os.path.join(OUT, f"wafer16_{i:03d}.tif"))


if __name__ == "__main__":
    for i in range(5):
        rgb_defects(i)
    for i in range(3):
        gray16(i)
    print("wrote samples to", OUT, "->", sorted(os.listdir(OUT)))
