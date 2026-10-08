// Renders PNG exports from the SVGs with the Chromium that ships with Playwright.
//   cd web && node ../brand/tools/export_png.mjs        (needs web/node_modules; copies the web-facing set to web/public)
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync, mkdirSync, copyFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const brand = path.resolve(here, '..');
const web = path.resolve(brand, '..', 'web');
const { chromium } = createRequire(path.join(web, 'package.json'))('@playwright/test');
const svg = (n) => readFileSync(path.join(brand, 'logo', n), 'utf8');

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM });
const page = await browser.newPage();
async function render(html, w, h, out, transparent = false) {
  await page.setViewportSize({ width: w, height: h });
  await page.setContent(`<!doctype html><meta charset=utf-8><style>html,body{margin:0;background:${transparent ? 'transparent' : '#fff'}}svg{display:block;width:${w}px;height:${h}px}</style>${html}`);
  await page.screenshot({ path: out, omitBackground: transparent });
}
const png = (n) => path.join(brand, 'png', n);
mkdirSync(path.join(brand, 'png'), { recursive: true });
await render(svg('favicon.svg'), 32, 32, png('favicon-32.png'), true);
await render(svg('app-icon-square.svg'), 180, 180, png('apple-touch-icon.png'));
await render(svg('app-icon.svg'), 192, 192, png('icon-192.png'), true);
await render(svg('app-icon.svg'), 512, 512, png('icon-512.png'), true);
await render(svg('app-icon-square.svg'), 512, 512, png('icon-512-maskable.png'));
await render(svg('mark.svg'), 512, 512, png('mark-512.png'), true);

// Social card: Midnight field, reverse lockup, one line of promise.
const font = (w) => `@font-face{font-family:B;font-weight:${w};src:url(data:font/woff;base64,${readFileSync(path.join(brand, 'fonts', `bricolage-grotesque-latin-${w}-normal.woff`)).toString('base64')})}`;
await page.setViewportSize({ width: 1200, height: 630 });
await page.setContent(`<!doctype html><meta charset=utf-8><style>${font(800)}html,body{margin:0}
.c{width:1200px;height:630px;box-sizing:border-box;padding:72px 84px;display:flex;flex-direction:column;justify-content:space-between;color:#fff;
background:radial-gradient(900px 520px at 88% 0%,rgba(11,99,229,.55),transparent 70%),#0A1F44;font-family:B,system-ui}
.l svg{height:92px;width:auto;display:block}h1{margin:0;font-weight:800;font-size:92px;line-height:1.02;letter-spacing:-.035em;max-width:900px}
p{margin:18px 0 0;font:500 30px/1.3 system-ui,sans-serif;color:#b9c8e6}</style>
<div class=c><div class=l>${svg('lockup-horizontal-reverse.svg')}</div><div><h1>Know who needs you today.</h1><p>Grades, attendance and a clear next step for every student.</p></div></div>`);
await page.screenshot({ path: png('og-image.png') });
await browser.close();

// Web-facing set.
const pub = path.join(web, 'public');
mkdirSync(path.join(pub, 'brand'), { recursive: true });
for (const f of ['apple-touch-icon.png', 'icon-192.png', 'icon-512.png', 'icon-512-maskable.png', 'og-image.png']) copyFileSync(png(f), path.join(pub, f));
copyFileSync(path.join(brand, 'logo', 'favicon.svg'), path.join(pub, 'favicon.svg'));
copyFileSync(png('favicon-32.png'), path.join(pub, 'favicon-32.png'));
for (const f of ['app-icon.svg', 'mark.svg']) copyFileSync(path.join(brand, 'logo', f), path.join(pub, 'brand', f));
writeFileSync(path.join(pub, 'site.webmanifest'), JSON.stringify({
  name: 'Super Teacher', short_name: 'Super Teacher', start_url: '/', display: 'standalone', background_color: '#F5F5F7', theme_color: '#0B63E5',
  icons: [{ src: '/icon-192.png', sizes: '192x192', type: 'image/png' }, { src: '/icon-512.png', sizes: '512x512', type: 'image/png' }, { src: '/icon-512-maskable.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' }],
}, null, 2) + '\n');
console.log('exported');
