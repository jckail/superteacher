"""Build brand/brand-guide.html from tokens.json. Contrast figures are computed here, never typed by hand.

python -I brand/tools/build_guide.py
"""

import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
tokens = json.loads((root / "tokens.json").read_text())
C = {k: v["hex"] for k, v in tokens["color"].items()}


def lum(h: str) -> float:
    h = h.lstrip("#")
    ch = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(ch[0]) + 0.7152 * f(ch[1]) + 0.0722 * f(ch[2])


def ratio(a: str, b: str) -> float:
    hi, lo = sorted([lum(a), lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def rgb(h: str) -> str:
    h = h.lstrip("#")
    return ", ".join(str(int(h[i : i + 2], 16)) for i in (0, 2, 4))


def swatch(key: str) -> str:
    t = tokens["color"][key]
    fg = (
        "#fff"
        if ratio(t["hex"], "#ffffff") >= ratio(t["hex"], "#0a1f44") and ratio(t["hex"], "#ffffff") >= 3
        else "#0a1f44"
    )
    label = key.replace("-", " ").title()
    return (
        f'<div class="sw"><div class="chip" style="background:{t["hex"]};color:{fg}"><b>{label}</b><span>{t["hex"].upper()}</span></div>'
        f"<p>{t['role']}</p><small>RGB {rgb(t['hex'])}</small></div>"
    )


PAIRS = [
    ("Cape Blue", "White", C["cape-blue"], "#ffffff", "Primary button label, links on white"),
    ("Cape Blue", "Mist", C["cape-blue"], C["mist"], "Links on the app canvas"),
    ("Cape Blue", "Mist Blue", C["cape-blue"], C["mist-blue"], "Selected state text"),
    ("Midnight", "White", C["midnight"], "#ffffff", "Wordmark, marketing headings"),
    ("White", "Midnight", "#ffffff", C["midnight"], "Reverse wordmark"),
    ("Ink", "Mist", C["ink"], C["mist"], "Interface text"),
    ("Graphite", "White", C["graphite"], "#ffffff", "Secondary text"),
    ("Midnight", "Spark Orange", C["midnight"], C["spark-orange"], "Text on an orange fill"),
    ("White", "Spark Orange", "#ffffff", C["spark-orange"], "Never. White on orange fails"),
    ("Ember", "White", C["ember"], "#ffffff", "Orange used as text"),
    ("Ember", "Glow", C["ember"], C["glow"], "Orange tint with orange text"),
    ("Spark Orange", "Midnight", C["spark-orange"], C["midnight"], "Spark on dark brand surfaces"),
]
rows = ""
for fg, bg, fh, bh, use in PAIRS:
    r = ratio(fh, bh)
    ok = "AA" if r >= 4.5 else ("Large text only" if r >= 3 else "Fails")
    cls = "ok" if r >= 4.5 else ("warn" if r >= 3 else "bad")
    rows += (
        f'<tr><td><span class="pair" style="background:{bh};color:{fh}">Aa</span></td><td>{fg} on {bg}</td>'
        f'<td class="num">{r:.2f}:1</td><td><span class="tag {cls}">{ok}</span></td><td>{use}</td></tr>'
    )

SCALE = [
    ("Large title", "34 / 700", "-0.026em", "Page titles"),
    ("Title", "20 / 600", "-0.02em", "Sheets, section heads"),
    ("Headline", "17 / 600", "-0.016em", "Card titles, names"),
    ("Body", "15 / 400", "-0.011em", "Everything else"),
    ("Subhead", "13 / 500", "0", "Labels, helper text"),
    ("Caption", "12 / 400", "0", "Fine print, timestamps"),
]
scale_rows = "".join(
    f'<tr><td style="font-size:{s.split(" / ")[0]}px;font-weight:{s.split(" / ")[1]};letter-spacing:{ls}">{n}</td><td class="num">{s}px</td><td class="num">{ls}</td><td>{u}</td></tr>'
    for n, s, ls, u in SCALE
)

html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Super Teacher brand guide</title>
<link rel="stylesheet" href="tokens.css">
<link rel="icon" href="logo/favicon.svg">
<style>
*{{box-sizing:border-box}}body{{margin:0;background:var(--mist);color:var(--ink);font:16px/1.55 var(--font-ui);-webkit-font-smoothing:antialiased}}
main{{max-width:1080px;margin:0 auto;padding:56px 24px 120px}}h1,h2,h3{{font-family:var(--font-display);font-weight:800;color:var(--midnight);margin:0;letter-spacing:-.03em;line-height:1.05}}
h1{{font-size:clamp(40px,7vw,76px);max-width:14ch}}h2{{font-size:34px;margin:84px 0 8px}}h3{{font-size:20px;font-weight:700;letter-spacing:-.02em;margin:32px 0 10px}}
p{{margin:8px 0;max-width:68ch}}.lede{{font-size:20px;color:var(--graphite);max-width:52ch;margin-top:20px}}a{{color:var(--cape-blue)}}
.hero{{display:grid;gap:28px;padding:8px 0 16px}}.hero img{{height:64px;width:auto;justify-self:start}}
.tile{{border-radius:20px;padding:36px;display:grid;place-items:center;min-height:200px;background:#fff;box-shadow:0 0 0 .5px rgb(0 0 0 / .08)}}.tile.dark{{background:var(--midnight)}}.tile.blue{{background:var(--cape-blue)}}.tile.orange{{background:var(--spark-orange)}}
.g2{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:20px}}.g3{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-top:20px}}
.tile img{{max-width:100%}}.cap{{font-size:13px;color:var(--graphite);margin-top:8px}}
.sw .chip{{border-radius:16px;padding:18px;height:112px;display:flex;flex-direction:column;justify-content:space-between;box-shadow:inset 0 0 0 .5px rgb(0 0 0 / .1)}}.sw b{{font-size:16px}}.sw span{{font-variant-numeric:tabular-nums;font-size:14px}}.sw p{{font-size:14px;margin:10px 0 2px}}.sw small{{color:var(--graphite)}}
table{{width:100%;border-collapse:collapse;margin-top:16px;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 0 0 .5px rgb(0 0 0 / .08)}}th{{text-align:left;font-size:13px;font-weight:500;color:var(--graphite);padding:10px 14px;border-bottom:.5px solid rgb(60 60 67 / .2)}}td{{padding:11px 14px;border-bottom:.5px solid rgb(60 60 67 / .12);vertical-align:middle}}tr:last-child td{{border:0}}.num{{font-variant-numeric:tabular-nums}}
.pair{{display:inline-grid;place-items:center;width:44px;height:30px;border-radius:8px;font-weight:700;box-shadow:inset 0 0 0 .5px rgb(0 0 0 / .15)}}.tag{{font-size:12px;font-weight:600;padding:2px 10px;border-radius:99px}}.tag.ok{{background:#e4f4e8;color:var(--go)}}.tag.warn{{background:var(--glow);color:var(--ember)}}.tag.bad{{background:#fde7e5;color:var(--alert)}}
.bar{{display:flex;height:44px;border-radius:12px;overflow:hidden;margin-top:16px;font-size:13px;font-weight:600}}.bar div{{display:grid;place-items:center}}
.ban{{border-radius:20px;background:#fff;padding:28px;box-shadow:0 0 0 .5px rgb(0 0 0 / .08);margin-top:16px}}.spec{{font-family:var(--font-display);font-weight:800;color:var(--midnight);font-size:clamp(34px,6vw,64px);line-height:1.04;letter-spacing:-.035em}}
.btns{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:14px}}.b{{border:0;border-radius:10px;padding:8px 16px;font:600 15px var(--font-ui);background:rgb(120 120 128 / .12);color:var(--ink)}}.b.p{{background:var(--cape-blue);color:#fff}}.b.d{{color:var(--alert)}}
.cp{{display:inline-flex;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:600}}.seg{{display:inline-flex;gap:2px;padding:2px;background:rgb(120 120 128 / .12);border-radius:9px}}.seg i{{font-style:normal;padding:5px 14px;border-radius:7px;font-size:14px;font-weight:500}}.seg i.on{{background:#fff;box-shadow:0 2px 6px rgb(0 0 0 / .14);font-weight:600}}
.nav{{display:inline-flex;align-items:center;gap:10px;padding:7px 12px;border-radius:8px;font-weight:500}}.nav.on{{background:var(--glow);color:var(--ember)}}
.dd{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}}.dd>div{{border-radius:16px;padding:20px;background:#fff;box-shadow:0 0 0 .5px rgb(0 0 0 / .08)}}.dd .no{{border-top:4px solid var(--alert)}}.dd .yes{{border-top:4px solid var(--go)}}.dd b{{display:block;font-size:13px;margin-bottom:6px;color:var(--graphite);font-weight:600}}
.mis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-top:16px}}.mis .tile{{min-height:150px;padding:20px}}.mis img{{height:64px}}.x{{position:relative}}.x::after{{content:"✕";position:absolute;top:10px;right:14px;color:var(--alert);font-weight:700}}
ul{{padding-left:20px;max-width:68ch}}li{{margin:4px 0}}code{{background:rgb(120 120 128 / .12);padding:1px 6px;border-radius:6px;font-size:.9em}}
@media (max-width:700px){{.dd,.g2{{grid-template-columns:1fr}}}}
</style></head><body><main>

<header class="hero"><img src="logo/lockup-horizontal.svg" alt="Super Teacher">
<h1>Know who needs you today.</h1>
<p class="lede">The brand behind Super Teacher: a calm, capable interface in <b>Cape Blue</b>, with one spark of <b>orange</b> where the product thinks alongside you.</p></header>

<h2>Idea</h2>
<p>Teachers already do the hard part. We notice the quiet student, the slipping grade, the week of absences, and point them out before they become problems. The brand is built from that: a <b>book</b> for the craft, a <b>cape</b> for the quiet heroics, and a <b>spark</b> for the student who is seen.</p>

<h2>Logo</h2>
<p>Two pages rise from a shared spine like a cape in flight. The right page flicks higher, so the mark always has motion. The orange spark leans into it.</p>
<div class="g2"><div class="tile"><img src="logo/lockup-horizontal.svg" height="72" alt=""></div><div class="tile dark"><img src="logo/lockup-horizontal-reverse.svg" height="72" alt=""></div>
<div class="tile"><img src="logo/lockup-stacked.svg" height="150" alt=""></div><div class="tile dark"><img src="logo/lockup-stacked-reverse.svg" height="150" alt=""></div></div>
<h3>Mark and app icon</h3>
<div class="g3"><div class="tile"><img src="logo/mark.svg" height="120" alt=""></div><div class="tile" style="background:var(--mist)"><img src="logo/app-icon.svg" height="120" alt=""></div><div class="tile"><img src="logo/app-icon-light.svg" height="120" alt=""></div>
<div class="tile blue"><img src="logo/mark-reverse.svg" height="120" alt=""></div><div class="tile orange"><img src="logo/mark-mono-navy.svg" height="120" alt=""></div><div class="tile"><img src="logo/mark-mono-navy.svg" height="120" alt=""></div></div>
<p class="cap">Full color, app icon (blue and light), reverse on Cape Blue, one-color on Spark Orange, one-color on white.</p>
<h3>Space and size</h3>
<ul><li><b>Clear space:</b> keep at least the diameter of the spark free on every side.</li><li><b>Minimum size:</b> mark 16 px (use <code>favicon.svg</code> below 32 px), horizontal lockup 120 px wide, stacked lockup 96 px wide.</li><li><b>Pick by background:</b> full color on white or Mist, reverse on Midnight or Cape Blue, one-color navy or white for single-ink printing.</li></ul>
<h3>Don't</h3>
<div class="mis"><div class="tile x"><img src="logo/mark.svg" style="transform:scaleX(1.6)" alt=""><p class="cap">Stretch or squash</p></div><div class="tile x"><img src="logo/mark.svg" style="transform:rotate(-18deg)" alt=""><p class="cap">Rotate or tilt</p></div><div class="tile x" style="background:var(--spark-orange)"><img src="logo/mark.svg" alt=""><p class="cap" style="color:var(--midnight)">Blue on orange</p></div><div class="tile x"><img src="logo/mark.svg" style="filter:hue-rotate(120deg)" alt=""><p class="cap">Recolor outside the palette</p></div></div>

<h2>Color</h2>
<p>Blue does the work; orange is the spark. Roughly <b>80% neutrals, 15% Cape Blue, 5% Spark Orange</b>. Use orange for the logo, AI moments and at most one highlight per screen. It never signals status.</p>
<div class="bar"><div style="flex:80;background:#fff;color:var(--graphite);box-shadow:inset 0 0 0 .5px rgb(0 0 0 / .1)">Neutrals 80%</div><div style="flex:15;background:var(--cape-blue);color:#fff">Blue 15%</div><div style="flex:5;background:var(--spark-orange);color:var(--midnight)"></div></div>
<h3>Brand</h3><div class="g3">{"".join(swatch(k) for k in ["cape-blue", "deep-cape", "sky", "mist-blue", "spark-orange", "ember", "glow", "midnight"])}</div>
<h3>Interface neutrals</h3><div class="g3">{"".join(swatch(k) for k in ["ink", "graphite", "mist"])}</div>
<h3>Status (functional only)</h3><div class="g3">{"".join(swatch(k) for k in ["go", "caution", "alert"])}</div>
<p class="cap">Status colors are separate from the brand on purpose: a student's risk is never blue or orange. Dark mode: Cape Blue text becomes <code>{tokens["dark"]["cape-blue-text"]}</code>, orange text <code>{tokens["dark"]["spark-orange-text"]}</code>, canvas <code>{tokens["dark"]["canvas"]}</code>.</p>
<h3>Approved pairings</h3>
<table><thead><tr><th></th><th>Pair</th><th>Contrast</th><th>WCAG</th><th>Use</th></tr></thead><tbody>{rows}</tbody></table>
<p class="cap">Text needs 4.5:1. Graphics and large text need 3:1. Spark Orange passes only with dark text, so label orange fills in Midnight.</p>

<h2>Type</h2>
<div class="ban"><div class="spec">Know who needs you today.</div><p class="cap"><b>Bricolage Grotesque</b> ExtraBold 800 · display, headlines, the wordmark. SIL Open Font License; files in <code>brand/fonts</code>. Tight tracking (-0.03em) at large sizes.</p></div>
<div class="ban"><div style="font:600 28px/1.2 var(--font-ui);letter-spacing:-.02em">Ava Cohen is 4 points below her usual work.</div><p class="cap"><b>SF Pro</b> (system UI) · all product text. No webfont is loaded, so the app is fast and feels native on every device: <code>{tokens["type"]["interface"]["stack"]}</code></p></div>
<table><thead><tr><th>Style</th><th>Size / weight</th><th>Tracking</th><th>Use</th></tr></thead><tbody>{scale_rows}</tbody></table>
<p class="cap">Sentence case everywhere. No all-caps labels. Numbers use tabular figures.</p>

<h2>In the product</h2>
<div class="ban"><div class="btns"><span class="b p">Save changes</span><span class="b">Cancel</span><span class="b d">Remove student</span>
<span class="seg"><i class="on">All</i><i>At risk</i><i>Watch</i></span><span class="cp" style="background:#fde7e5;color:var(--alert)">At risk</span><span class="cp" style="background:#fff1d6;color:var(--caution)">Watch</span><span class="cp" style="background:#e4f4e8;color:var(--go)">On track</span><span class="nav on">✦ Ask AI</span></div>
<div style="display:flex;gap:28px;align-items:center;margin-top:24px;flex-wrap:wrap"><svg width="120" height="120" viewBox="0 0 168 168"><g transform="rotate(-90 84 84)" fill="none" stroke-width="16" stroke-linecap="round"><circle cx="84" cy="84" r="74" stroke="rgb(120 120 128 / .16)"/><circle cx="84" cy="84" r="74" stroke="#0b63e5" stroke-dasharray="465" stroke-dashoffset="19"/><circle cx="84" cy="84" r="54" stroke="rgb(120 120 128 / .16)"/><circle cx="84" cy="84" r="54" stroke="#e56b00" stroke-dasharray="339" stroke-dashoffset="27"/><circle cx="84" cy="84" r="34" stroke="rgb(120 120 128 / .16)"/><circle cx="84" cy="84" r="34" stroke="#2a8af6" stroke-dasharray="214" stroke-dashoffset="36"/></g></svg>
<p style="max-width:44ch">The activity rings on Today use the full palette: blue for showing up, orange for work handed in, sky for the overall grade. Each ring also has a label and a number, never color alone.</p></div></div>

<h2>Voice</h2>
<p>Plain, specific and calm. We say what happened and what to do next. We talk like a good colleague, not a mascot.</p>
<ul><li>Sentence case. Active verbs. Name the student, quote the number.</li><li>Say what the data supports. The AI <i>suggests</i>; the teacher decides.</li><li>Errors state what went wrong and how to fix it. They don't apologize or joke.</li><li>The same action keeps the same name through the whole flow: "Save changes" ends in "Changes saved."</li></ul>
<div class="dd"><div class="yes"><b>Yes</b>7 students could use your attention.<br>Record work or attendance before assessing progress.<br>Add a student to see their progress.</div><div class="no"><b>No</b>Oops! Something went wrong 😅<br>Unlock powerful insights with AI-driven analytics!<br>Submit</div></div>

<h2>Files</h2>
<table><thead><tr><th>File</th><th>Use</th></tr></thead><tbody>
<tr><td><code>logo/lockup-horizontal*.svg</code></td><td>Headers, documents, email. Variants: full color, reverse, mono.</td></tr>
<tr><td><code>logo/lockup-stacked*.svg</code></td><td>Square or tall spaces, covers, slides.</td></tr>
<tr><td><code>logo/mark*.svg</code></td><td>The symbol alone: avatars, watermarks, merchandise.</td></tr>
<tr><td><code>logo/app-icon*.svg</code>, <code>app-icon-square.svg</code></td><td>App tiles and home-screen icons. Use the square for platforms that apply their own mask.</td></tr>
<tr><td><code>logo/favicon.svg</code></td><td>Browser tab and anything under 32 px.</td></tr>
<tr><td><code>png/</code></td><td>Ready exports: favicon, Apple touch icon, 192/512 icons, maskable icon, 1200x630 social card.</td></tr>
<tr><td><code>tokens.css</code>, <code>tokens.json</code></td><td>Color, type and radius tokens for code and design tools.</td></tr>
<tr><td><code>fonts/</code></td><td>Bricolage Grotesque 700 and 800 (OFL) for brand work outside the product.</td></tr>
<tr><td><code>tools/</code></td><td>Regenerates everything: <code>build_brand.py</code>, <code>export_png.mjs</code>, <code>build_guide.py</code>.</td></tr></tbody></table>
</main></body></html>
"""
(root / "brand-guide.html").write_text(html)
print("wrote brand-guide.html", len(html), "bytes")
