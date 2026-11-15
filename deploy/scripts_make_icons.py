"""Generate original Unjobless PWA icons (gradient tile + 'U' arc mark). Run: uv run python deploy/scripts_make_icons.py"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "apps" / "web" / "public" / "icons"
TOP, BOTTOM = (167, 139, 250), (109, 40, 217)


def gradient(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            px[x, y] = tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3))
    return img


def icon(size: int, *, maskable: bool) -> Image.Image:
    bg = gradient(size)
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    if maskable:
        d.rectangle([0, 0, size, size], fill=255)
    else:
        d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.24), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(bg, (0, 0), mask)
    draw = ImageDraw.Draw(out)
    scale = 0.62 if maskable else 0.78  # keep the mark inside the maskable safe zone
    s = size * scale
    ox, oy = (size - s) / 2, (size - s) / 2
    w = max(2, int(s * 0.12))
    left, right, top = ox + s * 0.22, ox + s * 0.78, oy + s * 0.18
    bottom = oy + s * 0.62
    draw.line([(left, top), (left, bottom - (right - left) / 2)], fill="white", width=w)
    draw.line([(right, top), (right, bottom - (right - left) / 2)], fill="white", width=w)
    draw.arc([left, bottom - (right - left), right, bottom], start=0, end=180, fill="white", width=w)
    for x in (left, right):
        r = w / 2
        draw.ellipse([x - r, top - r, x + r, top + r], fill="white")
    r = s * 0.06
    cx, cy = ox + s / 2, oy + s * 0.84
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill="white")
    return out


for size in (192, 512):
    icon(size, maskable=False).save(OUT / f"icon-{size}.png")
    icon(size, maskable=True).save(OUT / f"maskable-{size}.png")
icon(180, maskable=True).convert("RGB").save(OUT / "apple-touch-icon.png")
print("icons written to", OUT)
