from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter


SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def _square_master(source: Image.Image, size: int = 1024) -> Image.Image:
    image = source.convert("RGBA")
    alpha = image.getchannel("A")
    bounds = alpha.getbbox()
    if bounds is None:
        raise ValueError("Logo tidak memiliki piksel terlihat")
    cropped = image.crop(bounds)
    padding = max(24, round(size * 0.035))
    available = size - padding * 2
    scale = min(available / cropped.width, available / cropped.height)
    resized = cropped.resize(
        (round(cropped.width * scale), round(cropped.height * scale)),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(
        resized,
        ((size - resized.width) // 2, (size - resized.height) // 2),
    )
    return canvas


def _small_icon(master: Image.Image, size: int) -> Image.Image:
    icon = master.resize((size, size), Image.Resampling.LANCZOS)
    if size <= 48:
        rgb = ImageEnhance.Contrast(icon.convert("RGB")).enhance(1.08)
        rgb = rgb.filter(ImageFilter.UnsharpMask(radius=0.7, percent=130, threshold=2))
        rgb.putalpha(icon.getchannel("A"))
        return rgb
    return icon


def main() -> int:
    project = Path(__file__).resolve().parents[1]
    assets = project / "src" / "emss" / "assets"
    source = assets / "emss-logo-v2.png"
    if not source.is_file():
        print(f"Sumber logo tidak ditemukan: {source}", file=sys.stderr)
        return 2
    with Image.open(source) as raw:
        master = _square_master(raw)
    master.save(assets / "emss-logo.png", optimize=True)
    _small_icon(master, 256).save(assets / "emss-tray.png", optimize=True)
    frames = [_small_icon(master, size) for size in SIZES]
    frames[-1].save(
        assets / "emss.ico",
        format="ICO",
        append_images=frames[:-1],
        sizes=[(size, size) for size in SIZES],
    )
    print("Ikon dibuat:", ", ".join(("emss-logo.png", "emss-tray.png", "emss.ico")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
