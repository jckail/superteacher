# Super Teacher brand kit

Open **[brand-guide.html](brand-guide.html)** in a browser for the full guide: logo, color, type, product patterns and voice.

**Tagline:** Know who needs you today.
**Idea:** a book (the craft), a cape (the quiet heroics) and a spark (the student who is seen).
**Palette:** Cape Blue `#0B63E5` does the work; Spark Orange `#FF8A1F` is the spark (logo, AI, one highlight per screen); Midnight `#0A1F44` for the wordmark. Status colors are functional and separate.
**Type:** Bricolage Grotesque (display, OFL) and the system UI font (product).

| Path | What |
| --- | --- |
| `logo/` | SVG logo set: lockups, mark, app icons, favicon, wordmark (outlined, no font needed) |
| `png/` | Exports: favicon, Apple touch icon, 192/512 icons, maskable icon, 1200x630 social card |
| `tokens.css`, `tokens.json` | Color, type and radius tokens. `web/src/styles.css` mirrors them |
| `fonts/` | Bricolage Grotesque 700/800 with its OFL license |
| `brand-guide.html` | The generated guide |
| `tools/` | Generators (below) |

## Regenerate

Everything is generated; edit the constants, not the outputs.

```bash
# logos (needs fonttools: pip install fonttools brotli)
python -I brand/tools/build_brand.py brand/fonts/bricolage-grotesque-latin-800-normal.woff
# PNGs + web favicon/manifest set (copies into web/public)
cd web && node ../brand/tools/export_png.mjs      # set CHROMIUM=/path/to/chrome if Playwright's browser is not installed
# the guide (contrast figures are computed from tokens.json)
python -I brand/tools/build_guide.py
```

If you change a color, change it in `tokens.json`, `tokens.css` and `web/src/styles.css`, then regenerate. Keep contrast pairings in the guide's table passing.
