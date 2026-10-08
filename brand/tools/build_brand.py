"""Generate every logo asset from one source of truth.

    python -I brand/tools/build_brand.py PATH/TO/bricolage-grotesque-latin-800-normal.woff

Edit the constants here, re-run, and all SVGs in brand/logo/ are regenerated (the wordmark is outlined, so none of the
outputs need a font installed).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from outline_wordmark import outline

BLUE, BLUE_HI = "#0B63E5", "#3D8BFF"
ORANGE, EMBER = "#FF8A1F", "#B34700"
NAVY, PAPER, WHITE = "#0A1F44", "#F5F7FA", "#FFFFFF"

# 64x64 grid. Two page-shaped wings rise from a shared spine like a cape in flight (the right one flicks higher, giving
# the mark motion); the spark leans into it and is the lit-up student.
WING_L = "M30.4 56C24.8 48.6 17 44.8 8 45.6V24C17.2 23.2 25.8 26.4 30.4 33.4Z"
WING_R = "M33.6 56C39.8 47.2 49.6 41.6 62 42.4V12.6C50 13.8 39.8 21 33.6 32.2Z"
SPARK = (30.6, 15.2, 7.4)  # cx, cy, r


def mark(pages: str, spark: str, extra: str = "") -> str:
    cx, cy, r = SPARK
    return f'{extra}<path fill="{pages}" d="{WING_L}"/><path fill="{pages}" d="{WING_R}"/><circle cx="{cx}" cy="{cy}" r="{r}" fill="{spark}"/>'


def svg(w: float, h: float, body: str, title: str, vb: str | None = None) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb or f"0 0 {w} {h}"}" role="img" aria-labelledby="t">'
        f'<title id="t">{title}</title>{body}</svg>\n'
    )


def squircle(fill: str, size: int = 64) -> str:
    return f'<rect width="{size}" height="{size}" rx="{size * 0.2237:.2f}" fill="{fill}"/>'


def main(font: str) -> None:
    out = Path(__file__).resolve().parent.parent / "logo"
    out.mkdir(exist_ok=True)
    wm = outline(font, "Super Teacher", tracking=-0.018)
    ww, wd = wm["width"], wm["d"]

    files: dict[str, str] = {}
    files["mark.svg"] = svg(64, 64, mark(BLUE, ORANGE), "Super Teacher")
    files["mark-navy.svg"] = svg(64, 64, mark(NAVY, ORANGE), "Super Teacher")
    files["mark-mono-navy.svg"] = svg(64, 64, mark(NAVY, NAVY), "Super Teacher")
    files["mark-mono-white.svg"] = svg(64, 64, mark(WHITE, WHITE), "Super Teacher")
    files["mark-reverse.svg"] = svg(64, 64, mark(WHITE, ORANGE), "Super Teacher")
    # App icon: blue squircle, white pages, orange spark. Pages are inset so the squircle mask never clips them.
    inner = f'<g transform="translate(9.6 9.6) scale(.7)">{mark(WHITE, ORANGE)}</g>'
    files["app-icon.svg"] = svg(
        64,
        64,
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{BLUE_HI}"/><stop offset="1" stop-color="{BLUE}"/></linearGradient></defs>{squircle("url(#g)")}{inner}',
        "Super Teacher",
    )
    files["app-icon-light.svg"] = svg(
        64,
        64,
        f'{squircle(WHITE)}<rect x=".5" y=".5" width="63" height="63" rx="14" fill="none" stroke="#0A1F44" stroke-opacity=".12"/>{inner.replace(WHITE, BLUE, 2)}',
        "Super Teacher",
    )
    # Full-bleed square (no rounded corners) for platforms that apply their own mask: apple-touch-icon, maskable icons.
    files["app-icon-square.svg"] = svg(
        64,
        64,
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{BLUE_HI}"/><stop offset="1" stop-color="{BLUE}"/></linearGradient></defs><rect width="64" height="64" fill="url(#g)"/><g transform="translate(11.2 11.2) scale(.65)">{mark(WHITE, ORANGE)}</g>',
        "Super Teacher",
    )
    # Favicon: bolder geometry for 16px, no gradient.
    files["favicon.svg"] = svg(
        64, 64, f'{squircle(BLUE)}<g transform="translate(7 8) scale(.78)">{mark(WHITE, ORANGE)}</g>', "Super Teacher"
    )

    # Horizontal lockup: mark + outlined wordmark. Wordmark scaled so its cap height is 26% of the mark's height.
    cap = 19.0
    s = cap / 100
    wx = 64 + 12
    wy = 33 - cap / 2 + 3
    wm_w = ww * s
    H = 64

    def horizontal(pages, spark, ink):
        body = f'{mark(pages, spark)}<path transform="translate({wx} {wy:.2f}) scale({s})" fill="{ink}" d="{wd}"/>'
        return svg(wx + wm_w, H, body, "Super Teacher", vb=f"0 0 {wx + wm_w + 2:.1f} {H}")

    files["lockup-horizontal.svg"] = horizontal(BLUE, ORANGE, NAVY)
    files["lockup-horizontal-reverse.svg"] = horizontal(WHITE, ORANGE, WHITE)
    files["lockup-horizontal-mono.svg"] = horizontal(NAVY, NAVY, NAVY)

    # Stacked lockup: mark above, wordmark centred below.
    cap2 = 15.0
    s2 = cap2 / 100
    w2 = ww * s2
    W = max(64, w2)

    def stacked(pages, spark, ink):
        body = (
            f'<g transform="translate({(W - 64) / 2:.2f} 0)">{mark(pages, spark)}</g>'
            f'<path transform="translate({(W - w2) / 2:.2f} {64 + 10}) scale({s2})" fill="{ink}" d="{wd}"/>'
        )
        return svg(W, 64 + 10 + cap2 + 6, body, "Super Teacher", vb=f"0 0 {W:.1f} {64 + 10 + cap2 + 6:.1f}")

    files["lockup-stacked.svg"] = stacked(BLUE, ORANGE, NAVY)
    files["lockup-stacked-reverse.svg"] = stacked(WHITE, ORANGE, WHITE)

    files["wordmark.svg"] = svg(ww, 100, f'<path fill="{NAVY}" d="{wd}"/>', "Super Teacher", vb=f"0 -22 {ww} 140")
    for name, text in files.items():
        (out / name).write_text(text)
    print("wrote", len(files), "files to", out)


if __name__ == "__main__":
    main(sys.argv[1])
