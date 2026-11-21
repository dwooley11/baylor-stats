"""Build the home-screen icon (Baylor logo on green) during deploy.
Usage: python scripts/make_icon.py <logo.png> <out_dir>"""
import sys
from pathlib import Path
from PIL import Image

GREEN = (21, 71, 52, 255)  # #154734
src, out = Path(sys.argv[1]), Path(sys.argv[2])
logo = Image.open(src).convert("RGBA")
logo = logo.crop(logo.getbbox())  # trim transparent edges

def icon(size, pad):
    bg = Image.new("RGBA", (size, size), GREEN)
    box = int(size * (1 - 2 * pad))
    l = logo.copy(); l.thumbnail((box, box), Image.LANCZOS)
    bg.alpha_composite(l, ((size - l.width) // 2, (size - l.height) // 2))
    return bg.convert("RGB")

icon(180, .16).save(out / "apple-touch-icon.png")
icon(512, .16).save(out / "icon-512.png")
icon(64, .08).save(out / "favicon.png")
