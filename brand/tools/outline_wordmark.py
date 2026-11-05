"""Outline wordmark text to SVG path data so the logo never depends on an installed font.

    python -I brand/tools/outline_wordmark.py FONT.woff "Super Teacher" 800 --tracking -0.02

Font: Bricolage Grotesque (SIL Open Font License 1.1), obtained from the @fontsource/bricolage-grotesque package.
Prints JSON: {"d": path data in a y-down box with cap-height 100, "width": advance width, "height": 100}.
"""

import argparse
import json

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont


def outline(font_path: str, text: str, tracking: float = 0.0) -> dict:
    font = TTFont(font_path)
    gs, cmap, hmtx = font.getGlyphSet(), font.getBestCmap(), font["hmtx"]
    upm = font["head"].unitsPerEm
    cap = getattr(font["OS/2"], "sCapHeight", 0) or upm * 0.7
    scale = 100 / cap  # cap height -> 100 units
    pen = SVGPathPen(gs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
    x = 0.0
    for ch in text:
        name = cmap[ord(ch)]
        t = (scale, 0, 0, -scale, x * scale, 100)  # flip y; baseline at y=100
        gs[name].draw(TransformPen(pen, t))
        x += hmtx[name][0] + tracking * upm
    x -= tracking * upm
    return {"d": pen.getCommands(), "width": round(x * scale, 2), "height": 100}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("font")
    ap.add_argument("text")
    ap.add_argument("weight", nargs="?")
    ap.add_argument("--tracking", type=float, default=0.0)
    a = ap.parse_args()
    print(json.dumps(outline(a.font, a.text, a.tracking)))
