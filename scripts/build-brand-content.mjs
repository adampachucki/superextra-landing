/**
 * Generates the Superextra brand-collection HTML (src/lib/brand/brand-content.html).
 * Pure HTML/CSS — gallery tiles use container-query (cqw) units so they scale crisply.
 * Nothing is shipped as an image: marks are inline SVG, colorful backgrounds are painted
 * live in a <canvas>, and every export is rendered client-side by the brand route.
 *
 * Run:  node scripts/build-brand-content.mjs   (then: npm run encrypt-brand <PIN>)
 */
import { writeFileSync, mkdirSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import {
	MARK_LINES,
	MARK_VB,
	MARK_STROKE,
	MARK_K,
	GAP_K,
	LOCKUP_RAISE_K,
	WORD_K,
	TAG_K,
	TAG_GAP_K,
	TAG_BOTTOM_K,
	MONO_MARK_K,
	MONO_GAP_K,
	MONO_RAISE_K,
	MONO_CAP_K,
	MONO_DROP_K
} from '../src/lib/brand/brand-geometry.js';
import { lockupBodySVG, glyphDefs } from '../src/lib/brand/brand-render.js';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

// Eight-point asterisk mark — geometry from the shared brand-geometry module.
const MK = (c) =>
	`<svg viewBox="0 0 ${MARK_VB} ${MARK_VB}" fill="none">${MARK_LINES.map(
		([x1, y1, x2, y2]) =>
			`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${c}" stroke-width="${MARK_STROKE}"/>`
	).join('')}</svg>`;

// Download controls — the brand route's export engine reads data-dl and renders
// the SVG / PNG client-side. dbg maps the gallery 'white' bg name to 'cream'.
const dbg = (bg) => (bg === 'white' ? 'cream' : bg);
const dl = (o) =>
	`<span class="dlbtns" data-dl='${JSON.stringify(o)}'><button type="button" class="dl" data-fmt="svg">SVG</button><button type="button" class="dl" data-fmt="png">PNG</button></span>`;

// Colour themes for the per-gallery picker. The brand route paints the live <canvas>
// backgrounds and resolves a tile's theme from its gallery's current selection.
const THEMES = [
	['periwinkle', 'Periwinkle'],
	['lavender-pink', 'Lavender → Pink'],
	['violet-cyan', 'Violet → Cyan'],
	['blue-teal', 'Blue → Teal'],
	['indigo-violet', 'Indigo → Violet'],
	['mint', 'Mint'],
	['dusk', 'Dusk']
];
const bgsel = (gallery, def) =>
	`<div class="bgsel" data-gallery="${gallery}" data-default="${def}"><span class="bgsel-l">Colour theme</span>${THEMES.map(([k, n]) => `<button type="button" class="theme${k === def ? ' active' : ''}" data-theme="${k}">${n}</button>`).join('')}</div>`;

// Real-size preview strip — the brand route composes the avatar export at full resolution, then
// downscales each canvas to the px size platforms actually display, so the grain pick can be
// judged where it matters (fine grain washes out small; coarse survives). Follows a gallery picker.
const SIZE_PX = [96, 64, 48, 32];
const sizeStrip = (gallery, kind) =>
	`<div class="sizes">${SIZE_PX.map(
		(px) =>
			`<figure class="szf"><canvas class="szc" data-gallery="${gallery}" data-kind="${kind}" data-size="${px}" style="width:${px}px;height:${px}px"></canvas><figcaption>${px}px</figcaption></figure>`
	).join('')}</div>`;

// Shorter-side display size for avatars/icons. The colorful grain is calibrated so a cell reads
// as a fine speck at this size — so it survives the shrink from the big export instead of washing
// out. (Matches AVATAR_SHOWN_AT in the brand route's export engine.)
const AVATAR_SHOWN_AT = 96;

// Icon / avatar tiles — the mark alone, and the ✲S monogram, on each background.
function iconTile({ kind, bg, crop, label }) {
	const r = (n) => n.toFixed(2);
	const ink = bg === 'white' ? '#1a1a1a' : '#fefdf9';
	const size = 128;
	const bgcss = bg === 'white' ? 'background:#fefdf9' : bg === 'black' ? 'background:#141210' : '';
	const canvasEl = bg === 'color' ? `<canvas class="bgc" data-gallery="profile"></canvas>` : '';
	const radius = crop === 'circle' ? '50%' : '24px';
	let inner;
	if (kind === 'mark') {
		const mw = size * 0.46;
		inner = `<span style="display:inline-flex;width:${r(mw)}px;height:${r(mw)}px">${MK(ink)}</span>`;
	} else {
		const SF = size * 0.5,
			mw = SF * MONO_MARK_K,
			gap = SF * MONO_GAP_K,
			raise = SF * MONO_RAISE_K,
			drop = SF * MONO_DROP_K;
		// align-items:center centres the "S"; the mark is raised visually (position, not
		// margin, so it doesn't skew centring); the whole group drops to sit centred.
		inner = `<div style="display:flex;align-items:center;gap:${r(gap)}px;color:${ink};line-height:1;transform:translateY(${r(drop)}px)"><span style="display:inline-flex;width:${r(mw)}px;height:${r(mw)}px;position:relative;top:-${r(raise)}px">${MK(ink)}</span><span class="wm" style="font-size:${r(SF)}px;color:${ink}">S</span></div>`;
	}
	const sq = crop === 'square';
	const gx = bg === 'color' ? { gallery: 'profile' } : {};
	const desc =
		kind === 'mark'
			? {
					name: `superextra-${sq ? 'icon' : 'avatar'}-${dbg(bg)}`,
					kind: 'mark',
					bg: dbg(bg),
					w: sq ? 512 : 1080,
					h: sq ? 512 : 1080,
					markFrac: sq ? 0.5 : 0.44,
					shownAt: AVATAR_SHOWN_AT,
					...gx
				}
			: {
					name: `superextra-monogram-${sq ? 'icon' : 'avatar'}-${dbg(bg)}`,
					kind: 'monogram',
					bg: dbg(bg),
					w: sq ? 512 : 1080,
					h: sq ? 512 : 1080,
					shownAt: AVATAR_SHOWN_AT,
					...gx
				};
	return `<div class="card"><div class="frame" style="padding:24px"><div style="position:relative;width:${size}px;height:${size}px;${bgcss};border-radius:${radius};overflow:hidden;display:flex;align-items:center;justify-content:center">${canvasEl}<span class="ic-fg">${inner}</span></div></div><div class="cap"><b>${label}</b>${dl(desc)}</div></div>`;
}
const ICON_BGS = [
	['white', 'Cream'],
	['black', 'Black'],
	['color', 'Colorful']
];
const iconSet = (kind) =>
	[
		...ICON_BGS.map(([bg, bn]) => iconTile({ kind, bg, crop: 'square', label: `${bn} · icon` })),
		...ICON_BGS.map(([bg, bn]) => iconTile({ kind, bg, crop: 'circle', label: `${bn} · avatar` }))
	].join('');

// One gallery tile, sized entirely in cqw (% of the tile's own width).
function tile({
	w,
	h,
	bg,
	layout = 'lockup',
	k = 1,
	m = 0.12,
	label,
	note,
	gallery,
	theme,
	download
}) {
	const ink = bg === 'white' ? '#1a1a1a' : '#fefdf9';
	// The lockup is rendered as the SAME outlined SF Pro Light SVG the export draws (shared
	// brand-render), so the preview is byte-identical to the downloaded file — no live-font
	// optical-sizing drift, and the wordmark/tagline proportions are constant on every tile.
	const inner = `<svg class="lk" viewBox="0 0 ${w} ${h}">${lockupBodySVG(w, h, k, m, layout, ink, true)}</svg>`;
	// Colourful backgrounds are painted live by the brand route into a <canvas>: a tile
	// either follows a gallery's theme picker (data-gallery) or shows a fixed draw (data-draw).
	const isColor = bg === 'color';
	const canvasEl = isColor
		? gallery
			? `<canvas class="bgc" data-gallery="${gallery}"></canvas>`
			: `<canvas class="bgc" data-draw="${theme || 'periwinkle'}" data-finish="rich"></canvas>`
		: '';
	const bgcss = bg === 'white' ? 'background:#fefdf9' : bg === 'black' ? 'background:#141210' : '';
	// Every downloadable colour tile follows a gallery's theme picker; there is no
	// downloadable fixed-draw tile, so the export only ever resolves via `gallery`.
	const ctrl = download
		? dl({
				name: `superextra-${w}x${h}-${layout}-${dbg(bg)}`,
				kind: 'tile',
				bg: dbg(bg),
				w,
				h,
				layout,
				k,
				m,
				...(isColor && gallery ? { gallery } : {})
			})
		: '';
	return `<figure class="tile"><div class="cv" style="aspect-ratio:${w}/${h};${bgcss}">${canvasEl}${inner}</div><figcaption><b>${label}</b>${note ? ` · <span>${note}</span>` : ''}${ctrl}</figcaption></figure>`;
}

const grid = (cols, items) =>
	`<div class="grid" style="grid-template-columns:repeat(${cols},1fr)">${items.map(tile).join('')}</div>`;

// One ad creative: a headline as the hero, the wordmark as a corner signature.
// Same cqw system as tile() so it scales crisply to any export size.
function adCard({ headline, bg = 'white', w = 1080, h = 1080, label, note }) {
	const ink = bg === 'white' ? '#1a1a1a' : '#fefdf9';
	const M = ((Math.min(w, h) / w) * 0.06 * 100).toFixed(2); // cqw
	const canvasEl =
		bg === 'color' ? `<canvas class="bgc" data-draw="dusk" data-finish="rich"></canvas>` : '';
	const bgcss = bg === 'white' ? 'background:#fefdf9' : bg === 'black' ? 'background:#141210' : '';
	const r = (n) => n.toFixed(2);
	const WM = 4.6,
		MARKW = WM * MARK_K,
		GAP = WM * GAP_K,
		RAISE = WM * LOCKUP_RAISE_K;
	const sig = `<div style="position:absolute;left:${M}cqw;bottom:${M}cqw;display:flex;align-items:center;gap:${r(GAP)}cqw"><span style="display:inline-flex;width:${r(MARKW)}cqw;height:${r(MARKW)}cqw;position:relative;top:-${r(RAISE)}cqw">${MK(ink)}</span><span class="wm" style="font-size:${WM}cqw;color:${ink};white-space:nowrap">Superextra</span></div>`;
	const head = `<div style="position:absolute;left:${M}cqw;right:${M}cqw;top:${M}cqw;font-size:12cqw;line-height:1.06;font-weight:500;letter-spacing:-0.03em;color:${ink}">${headline}</div>`;
	return `<figure class="tile"><div class="cv" style="aspect-ratio:${w}/${h};${bgcss}">${canvasEl}${head}${sig}</div><figcaption><b>${label}</b>${note ? ` · <span>${note}</span>` : ''}</figcaption></figure>`;
}

// Paid-social lead ads. Headline is the in-image hero; full copy lives in the campaign.
const AD_CREATIVES = [
	{ headline: 'Why your<br>restaurant<br>slowed down', label: 'A', note: 'why is it happening' },
	{ headline: 'AI consultant<br>for every<br>restaurant', label: 'B', note: 'the big decisions' },
	{ headline: 'Beat the<br>restaurant<br>next door', label: 'C', note: 'beat the competitor' },
	{ headline: 'Your menu.<br>More guests.<br>Better margins.', label: 'D', note: 'pricing' }
].map((a) => ({ ...a, w: 1080, h: 1080, bg: 'white' }));

const LAYS = [
	['lockup', 'Lockup'],
	['split', 'Split · bottom-left'],
	['splitbr', 'Split · bottom-right']
];
const BGS = [
	['white', 'White'],
	['black', 'Black'],
	['color', 'Colorful']
];
const matrix = (w, h, extra = {}) =>
	BGS.flatMap(([bg, bn]) =>
		LAYS.map(([ly, ln]) => ({ w, h, bg, layout: ly, label: ln, note: bn, ...extra }))
	);

// Export formats — the single source for the gallery sizes AND the Construction spec table,
// so the documented scale can never drift from what's actually rendered. `k` scales the lockup
// relative to the canvas; `m` is the inset margin (× the shorter side).
const FORMATS = [
	{ id: 'cover', label: 'Cover', w: 1640, h: 624, k: 0.85, m: 0.12 },
	{ id: 'square', label: 'Square', w: 1080, h: 1080, k: 1.5, m: 0.075 },
	{ id: 'portrait', label: 'Portrait', w: 1080, h: 1920, k: 1.5, m: 0.075 },
	{ id: 'bannerWide', label: 'Banner · wide', w: 1500, h: 500, k: 1, m: 0.12 },
	{ id: 'bannerThin', label: 'Banner · thin', w: 1128, h: 191, k: 0.85, m: 0.12 }
];
const F = Object.fromEntries(FORMATS.map((f) => [f.id, f]));

const COVER = matrix(F.cover.w, F.cover.h, {
	k: F.cover.k,
	m: F.cover.m,
	download: true,
	gallery: 'cover'
});
const SQUARE = matrix(F.square.w, F.square.h, {
	k: F.square.k,
	m: F.square.m,
	download: true,
	gallery: 'square'
});
const PORTRAIT = matrix(F.portrait.w, F.portrait.h, {
	k: F.portrait.k,
	m: F.portrait.m,
	download: true,
	gallery: 'portrait'
});
const wide = { w: F.bannerWide.w, h: F.bannerWide.h, k: F.bannerWide.k };
const thin = { w: F.bannerThin.w, h: F.bannerThin.h, k: F.bannerThin.k };
const BANNERS = [
	{ ...wide, bg: 'white', layout: 'lockup', label: 'Wide', note: 'lockup · white' },
	{ ...wide, bg: 'color', layout: 'splitbr', label: 'Wide', note: 'split-right · colorful' },
	{ ...wide, bg: 'black', layout: 'split', label: 'Wide', note: 'split-left · black' },
	{ ...thin, bg: 'white', layout: 'splitbr', label: 'Thin', note: 'white' },
	{ ...thin, bg: 'black', layout: 'splitbr', label: 'Thin', note: 'black' },
	{ ...thin, bg: 'color', layout: 'splitbr', label: 'Thin', note: 'colorful' }
].map((b) => ({ ...b, download: true, gallery: 'banners' }));

// Colorful background swatch (no lockup) — a live canvas preview of one draw + finish.
const bgFig = (draw, finish, ar, title, note) =>
	`<figure class="tile"><div class="cv" style="aspect-ratio:${ar}"><canvas class="bgc" data-draw="${draw}" data-finish="${finish}"></canvas></div><figcaption><b>${title}</b>${note ? ` · <span>${note}</span>` : ''}</figcaption></figure>`;

// The colour draws, each available flat (gradient + noise) and rich (+ circular glows).
const COLOR_DRAWS = [
	['periwinkle', 'Periwinkle', 'violet-pink → blue'],
	['lavender-pink', 'Lavender → Pink', 'violet → pink'],
	['violet-cyan', 'Violet → Cyan', ''],
	['blue-teal', 'Blue → Teal', 'indigo → cyan'],
	['indigo-violet', 'Indigo → Violet', ''],
	['mint', 'Mint', 'emerald → cyan']
];

// Construction spec — generated from the same constants the lockup renders from, so the
// documented proportions/scale can never drift from the artwork. Edit brand-geometry, re-run.
const num = (n) => Number(n.toFixed(3)).toString();
const constructionSpec = `
    <h3>Construction — proportions <span class="pill">one source of truth</span></h3>
    <p class="note">Every ratio below is <b style="color:var(--ink);font-weight:600">× the wordmark size</b> (the font-size of “Superextra”). The lockup is built from these fixed ratios — never spaced by eye — so it stays self-similar at every size. The tagline is left-aligned to the “S” (not the mark) and runs <b style="color:var(--ink);font-weight:600">≈ 8%</b> past the wordmark’s right edge — a fixed consequence of its size, so it is identical on every asset.</p>
    <table class="files"><thead><tr><th>Measure</th><th>Ratio · × wordmark</th></tr></thead><tbody>
      <tr><td>Mark width</td><td><code>${num(MARK_K)}</code></td></tr>
      <tr><td>Mark → wordmark gap</td><td><code>2 / 22 ≈ ${num(GAP_K)}</code></td></tr>
      <tr><td>Mark raise — centre above the wordmark’s centre</td><td><code>${num(LOCKUP_RAISE_K)}</code></td></tr>
      <tr><td>Tagline size</td><td><code>${num(TAG_K)}</code></td></tr>
      <tr><td>Tagline baseline — below the wordmark’s centre</td><td><code>${num(TAG_GAP_K * TAG_K + 0.5)}</code></td></tr>
      <tr><td>Tagline baseline — above the bottom inset</td><td><code>${num(TAG_BOTTOM_K)} × tagline</code> · <code>${num(TAG_BOTTOM_K * TAG_K)}</code> × wordmark</td></tr>
    </tbody></table>

    <h3>Scale per format</h3>
    <p class="note">The wordmark is <code>${num(WORD_K)}%</code> of the tile width at <code>k = 1</code> — i.e. <code>word = ${num(WORD_K)} · k · width ÷ 100</code>. The inset margin is <code>m × the shorter side</code>. <code>k</code> is the only knob that changes the logo’s size relative to the canvas.</p>
    <table class="files"><thead><tr><th>Format</th><th>Size</th><th>k</th><th>Wordmark</th><th>Inset m</th></tr></thead><tbody>
      ${FORMATS.map(
				(f) =>
					`<tr><td>${f.label}</td><td>${f.w}×${f.h}</td><td><code>${num(f.k)}</code></td><td>${(WORD_K * f.k).toFixed(2)}% · ${Math.round((WORD_K * f.k * f.w) / 100)}px</td><td><code>${num(f.m)}</code></td></tr>`
			).join('')}
    </tbody></table>

    <h3>Monogram <span class="pill">✲S</span></h3>
    <p class="note">A separate icon — the mark as a superscript over the “S”. Ratios are <b style="color:var(--ink);font-weight:600">× the “S” size</b>.</p>
    <table class="files"><thead><tr><th>Measure</th><th>Ratio · × S</th></tr></thead><tbody>
      <tr><td>Mark width</td><td><code>${num(MONO_MARK_K)}</code></td></tr>
      <tr><td>Mark → S gap</td><td><code>${num(MONO_GAP_K)}</code></td></tr>
      <tr><td>Mark raise</td><td><code>${num(MONO_RAISE_K)}</code></td></tr>
      <tr><td>S cap height (approx.)</td><td><code>${num(MONO_CAP_K)}</code></td></tr>
      <tr><td>Group drop — re-centres the ✲S in a square</td><td><code>≈ ${num(MONO_DROP_K)}</code></td></tr>
    </tbody></table>

    <h3>Typeface</h3>
    <p class="note">The system sans at the <b style="color:var(--ink);font-weight:600">Light</b> instance — SF Pro on Apple, Inter (300) elsewhere — variable weight <code>274.315</code> (where CSS <code>font-weight: 300</code> maps). Tracking: wordmark <code>−0.025em</code>, tagline <code>+0.01em</code>. Every export embeds the wordmark/tagline as <b style="color:var(--ink);font-weight:600">outlined vector paths</b> (SF Pro Light), so each file is the exact typeface with no font dependency.</p>

    <p class="note">Every asset — the previews on this page <b style="color:var(--ink);font-weight:600">and</b> every downloaded SVG/PNG — renders from one shared pipeline: <code>brand-geometry</code> (these proportions) + <code>brand-glyphs</code> (the SF Pro Light outlines) + <code>brand-render</code> (the lockup SVG). <b style="color:var(--ink);font-weight:600">Preview equals export, pixel-for-pixel, on every asset — and this whole spec is generated from those same constants, so it can’t drift.</b> Change a number in <code>brand-geometry</code>, re-run the generator, and it updates everywhere — including here.</p>
`;

const html = `<style>
:root{--bg:#1a1714;--panel:#211e1a;--panel2:#262320;--line:#2e2a25;--line2:#3d3832;--ink:#ede9e3;--mut:#9b958c;--soft:#c7c1b8;--cream:#fefdf9;--sb:248px}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--ink);font-family:'Inter',-apple-system,system-ui,sans-serif;-webkit-font-smoothing:antialiased;line-height:1.5}
.wm{font-family:-apple-system,BlinkMacSystemFont,'Inter',ui-sans-serif,system-ui,sans-serif;font-weight:300;letter-spacing:-0.025em}
.sidebar{position:fixed;top:0;left:0;width:var(--sb);height:100vh;overflow-y:auto;background:#171411;border-right:1px solid var(--line);padding:28px 22px 40px}
.sbrand{display:flex;align-items:center;gap:2px;margin-bottom:6px}
.sbrand svg{width:16.5px;height:16.5px;margin-top:-8px}.sbrand .nm{font-size:22px;font-family:-apple-system,BlinkMacSystemFont,'Inter',ui-sans-serif,system-ui,sans-serif;font-weight:300;letter-spacing:-0.025em}
.sbrand-sub{font-size:12px;color:var(--mut);margin-bottom:26px}
.navgroup{margin-bottom:20px}
.navgroup h4{font-size:10.5px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:#6f6a62;margin:0 0 8px 2px}
.navgroup a{display:block;font-size:13.5px;color:var(--soft);text-decoration:none;padding:5px 8px;border-radius:7px}
.navgroup a:hover{background:var(--panel);color:var(--ink)}
.navgroup a.active{background:var(--panel2);color:var(--ink);font-weight:500}
main{margin-left:var(--sb);max-width:1000px;padding:60px 56px 160px}
section{padding-top:54px;scroll-margin-top:24px}section:first-child{padding-top:8px}
.eyebrow{font-size:11px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);margin-bottom:10px}
h1{font-size:38px;font-weight:300;letter-spacing:-0.03em;margin-bottom:14px}
h2{font-size:24px;font-weight:500;letter-spacing:-0.02em;margin-bottom:6px}
h3{font-size:14px;font-weight:600;color:var(--soft);margin:26px 0 12px}
p.lede{font-size:16px;color:var(--soft);max-width:680px;margin-bottom:8px}
p.note{font-size:13.5px;color:var(--mut);max-width:680px;margin:10px 0}
.hr{height:1px;background:var(--line);margin:46px 0 0}
.grid{display:grid;gap:18px;margin-top:18px}
.tile figcaption{margin-top:9px;font-size:12px;color:var(--soft)}
.tile figcaption b{color:var(--ink);font-weight:600}.tile figcaption span{color:var(--mut)}
.cv{position:relative;width:100%;border-radius:12px;border:1px solid var(--line);overflow:hidden;container-type:inline-size}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.card .frame{display:flex;align-items:center;justify-content:center;padding:30px}
.card img{display:block;max-width:100%}
.cap{padding:11px 14px;font-size:12.5px;color:var(--soft);border-top:1px solid var(--line);line-height:1.45}
.cap b{color:var(--ink);font-weight:600}.cap .dim{color:var(--mut)}
.dlbtns{display:inline-flex;gap:6px;margin-left:8px;vertical-align:middle}
.dl{font-family:inherit;font-size:10px;font-weight:600;letter-spacing:.05em;color:var(--mut);background:transparent;border:1px solid var(--line2);border-radius:6px;padding:2px 7px;cursor:pointer;transition:color .15s,border-color .15s}
.dl:hover{color:var(--ink);border-color:var(--soft)}
.bgc{position:absolute;inset:0;width:100%;height:100%;display:block}
.lk{position:absolute;inset:0;width:100%;height:100%;display:block}
.ic-fg{position:relative;z-index:1;display:inline-flex;align-items:center;justify-content:center}
.bgsel{display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin:16px 0 2px}
.bgsel-l{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);margin-right:4px}
.theme{font-family:inherit;font-size:12px;color:var(--soft);background:transparent;border:1px solid var(--line2);border-radius:999px;padding:3px 11px;cursor:pointer;transition:color .15s,border-color .15s,background .15s}
.theme:hover{color:var(--ink);border-color:var(--soft)}
.theme.active{color:var(--ink);background:var(--panel2);border-color:var(--soft);font-weight:600}
.sizerow{display:flex;align-items:flex-end;gap:18px;margin:14px 0}
.szlabel{width:34px;flex:none;font-size:12px;color:var(--mut);padding-bottom:24px}
.sizes{display:flex;align-items:flex-end;gap:20px}
.szf{display:flex;flex-direction:column;align-items:center;gap:7px}
.szc{display:block;border-radius:50%;border:1px solid var(--line)}
.szf figcaption{font-size:10.5px;color:var(--mut);font-variant-numeric:tabular-nums}
.cream{background:var(--cream)}
.swatch{border:1px solid var(--line);border-radius:12px;overflow:hidden}
.swatch .chip{height:96px}.swatch .meta{padding:11px 13px;font-size:12.5px}
.swatch .meta b{display:block;color:var(--ink);font-weight:600;margin-bottom:2px}.swatch .meta span{color:var(--mut);font-variant-numeric:tabular-nums}
.palette{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-top:14px}
.palette .p{border-radius:10px;border:1px solid var(--line);overflow:hidden}.palette .p .c{height:64px}.palette .p .m{padding:8px 10px;font-size:11px;color:var(--mut);font-variant-numeric:tabular-nums}
.type{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:28px 30px}
.type .row{display:flex;align-items:baseline;gap:18px;padding:12px 0;border-bottom:1px solid var(--line)}.type .row:last-child{border-bottom:0}
.type .w{width:120px;flex:none;font-size:12.5px;color:var(--mut)}.type .s{color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,'Inter',ui-sans-serif,system-ui,sans-serif}
table.files{width:100%;border-collapse:collapse;margin-top:16px;font-size:13px}
table.files th{text-align:left;color:var(--mut);font-weight:600;font-size:11px;letter-spacing:.06em;text-transform:uppercase;padding:8px 12px;border-bottom:1px solid var(--line)}
table.files td{padding:10px 12px;border-bottom:1px solid var(--line);color:var(--soft);vertical-align:top}
table.files td code,p code{color:var(--ink);font-family:ui-monospace,Menlo,monospace;font-size:12px}
.pill{display:inline-block;font-size:11px;color:var(--mut);border:1px solid var(--line2);border-radius:999px;padding:2px 9px;margin-left:8px}
.do{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
.do .b{border:1px solid var(--line);border-radius:10px;padding:14px 16px;font-size:13.5px;color:var(--soft)}
.do .b .t{font-weight:600;margin-bottom:4px}.do .ok .t{color:#7fd6a6}.do .no .t{color:#e0907f}
@media(max-width:820px){.sidebar{display:none}main{margin-left:0;padding:32px 22px 120px}.palette{grid-template-columns:repeat(3,1fr)}}
</style>
${glyphDefs()}
<aside class="sidebar">
  <div class="sbrand">${MK('#ede9e3')}<span class="nm">Superextra</span></div>
  <p class="sbrand-sub">Brand assets &amp; guidelines</p>
  <div class="navgroup"><h4>Foundations</h4><a href="#overview">Overview</a><a href="#logo">Logo</a><a href="#color">Color</a><a href="#type">Typography</a></div>
  <div class="navgroup"><h4>System</h4><a href="#layouts">Layouts</a><a href="#backgrounds">Backgrounds</a><a href="#colorful">Colorful palette</a></div>
  <div class="navgroup"><h4>Gallery</h4><a href="#cover">Cover</a><a href="#square">Square</a><a href="#portrait">Portrait</a><a href="#banners">Banners</a></div>
  <div class="navgroup"><h4>Marketing</h4><a href="#ads">Ad creatives</a></div>
  <div class="navgroup"><h4>Marks &amp; partners</h4><a href="#profile">Profile</a><a href="#stripe">Stripe</a></div>
  <div class="navgroup"><h4>Reference</h4><a href="#files">Files &amp; naming</a></div>
</aside>
<main>
  <section id="overview">
    <div class="eyebrow">Superextra</div><h1>Brand assets</h1>
    <p class="lede">The marks, colors, type, and layout system for Superextra — an AI consultant for every restaurant. Every surface is built from one set of rules so the brand stays recognizable.</p>
    <p class="note">Three things never change: the asterisk mark, the Inter wordmark, and the three backgrounds (white, black, colorful). Everything else is composition.</p>
  </section>

  <div class="hr"></div>
  <section id="logo">
    <div class="eyebrow">Foundations</div><h2>Logo</h2>
    <p class="lede">An eight-point asterisk mark beside the “Superextra” wordmark in the system sans, Light weight. The mark sits raised — its center aligns near the cap height of the wordmark.</p>
    <div class="grid" style="grid-template-columns:repeat(2,1fr)">
      <div class="card"><div class="frame cream" style="min-height:200px"><span style="display:inline-flex;width:120px;height:120px">${MK('#1a1a1a')}</span></div><div class="cap"><b>Mark</b> · the asterisk, used alone as the icon/avatar${dl({ name: 'superextra-mark', kind: 'mark', bg: 'transparent', w: 512, h: 512, markFrac: 0.78 })}</div></div>
      <div class="card"><div class="frame cream" style="min-height:200px"><div style="display:flex;align-items:center;gap:6px;color:#1a1a1a"><span style="display:inline-flex;width:49.5px;height:49.5px;position:relative;top:-11.88px">${MK('#1a1a1a')}</span><span class="wm" style="font-size:66px">Superextra</span></div></div><div class="cap"><b>Wordmark</b> · mark + name, the primary lockup${dl({ name: 'superextra-wordmark', kind: 'lockup', bg: 'transparent', w: 0, h: 480 })}</div></div>
    </div>
    <div class="do"><div class="b ok"><div class="t">Do</div>Keep the raised mark, Light weight, and −0.025em tracking. Give the logo clear space of at least the mark’s height on every side.</div><div class="b no"><div class="t">Don’t</div>Recolor, outline, stretch, re-space, or swap the typeface. Don’t lower the mark to the baseline.</div></div>
${constructionSpec}
  </section>

  <div class="hr"></div>
  <section id="color">
    <div class="eyebrow">Foundations</div><h2>Color</h2>
    <p class="lede">Two neutrals carry the brand; one accent system lives only inside the colorful background. Surfaces are always one of the three backgrounds.</p>
    <h3>Core</h3>
    <div class="grid" style="grid-template-columns:repeat(3,1fr)">
      <div class="swatch"><div class="chip" style="background:#fefdf9;border-bottom:1px solid #ebe7e0"></div><div class="meta"><b>White (cream)</b><span>#FEFDF9 · rgb(254 253 249)</span></div></div>
      <div class="swatch"><div class="chip" style="background:#141210"></div><div class="meta"><b>Black</b><span>#141210 · rgb(20 18 16)</span></div></div>
      <div class="swatch"><div class="chip" style="background:#1a1a1a"></div><div class="meta"><b>Ink</b><span>#1A1A1A · mark &amp; text</span></div></div>
    </div>
    <h3>Accent palette <span class="pill">gradient only</span></h3>
    <p class="note">These six hues appear only blended inside the colorful background — never as flat fills, borders, or text.</p>
    <div class="palette">
      <div class="p"><div class="c" style="background:#6EE7B7"></div><div class="m">#6EE7B7</div></div>
      <div class="p"><div class="c" style="background:#A78BFA"></div><div class="m">#A78BFA</div></div>
      <div class="p"><div class="c" style="background:#F472B6"></div><div class="m">#F472B6</div></div>
      <div class="p"><div class="c" style="background:#FBBF24"></div><div class="m">#FBBF24</div></div>
      <div class="p"><div class="c" style="background:#06B6D4"></div><div class="m">#06B6D4</div></div>
      <div class="p"><div class="c" style="background:#6366F1"></div><div class="m">#6366F1</div></div>
    </div>
  </section>

  <div class="hr"></div>
  <section id="type">
    <div class="eyebrow">Foundations</div><h2>Typography</h2>
    <p class="lede">The system sans stack — San Francisco on Apple devices, Inter as the cross-platform fallback (matches the product's <code>--font-sans</code>). The wordmark and taglines use Light (300); supporting copy uses Regular and Medium.</p>
    <div class="type">
      <div class="row"><div class="w">Light · 300</div><div class="s wm" style="font-size:34px">Superextra</div></div>
      <div class="row"><div class="w">Regular · 400</div><div class="s" style="font-weight:400;font-size:22px">AI consultant for every restaurant</div></div>
      <div class="row"><div class="w">Medium · 500</div><div class="s" style="font-weight:500;font-size:18px">Section labels &amp; UI</div></div>
    </div>
    <p class="note">Wordmark tracking −0.025em (Tailwind <code>tracking-tight</code>). Tagline: “AI consultant for every restaurant” — no leading “An”.</p>
  </section>

  <div class="hr"></div>
  <section id="layouts">
    <div class="eyebrow">System</div><h2>Layouts</h2>
    <p class="lede">Every composition is the same lockup, placed. Tagline is full-strength (matches the wordmark color). Choose by format — taller frames suit the split; thin frames suit the corner split.</p>
    ${grid(3, [
			{
				w: 1640,
				h: 624,
				k: 0.85,
				bg: 'white',
				layout: 'lockup',
				label: 'Lockup',
				note: 'tagline under text'
			},
			{
				w: 1640,
				h: 624,
				k: 0.85,
				bg: 'white',
				layout: 'split',
				label: 'Split',
				note: 'tagline bottom-left'
			},
			{
				w: 1640,
				h: 624,
				k: 0.85,
				bg: 'white',
				layout: 'splitbr',
				label: 'Split',
				note: 'tagline bottom-right'
			}
		])}
    <h3>Rules</h3>
    <p class="note">• <b>Lockup:</b> tagline under the wordmark text, left-aligned to the “S” (not the mark).<br>• <b>Split:</b> mark top-left, tagline in a bottom corner.<br>• <b>Thin banners:</b> mark top-left, tagline bottom-right; baseline sits on the letters (a, c, e), descenders hang below.<br>• Avatar overlap (Facebook, X) → keep the mark top-left so the platform avatar never covers it.</p>
  </section>

  <div class="hr"></div>
  <section id="backgrounds">
    <div class="eyebrow">System</div><h2>Backgrounds</h2>
    <p class="lede">Every surface uses white, black, or the colorful gradient with film grain. The grain is tuned per asset to stay a fine, even texture at the size each surface is shown — so it never averages away on small exports or turns coarse on large ones. The colorful background comes in several color draws (see <a href="#colorful" style="color:var(--soft)">Colorful palette</a>).</p>
    ${grid(3, [
			{ w: 1640, h: 624, k: 0.85, bg: 'white', layout: 'lockup', label: 'White', note: '#FEFDF9' },
			{ w: 1640, h: 624, k: 0.85, bg: 'black', layout: 'lockup', label: 'Black', note: '#141210' },
			{
				w: 1640,
				h: 624,
				k: 0.85,
				bg: 'color',
				theme: 'periwinkle',
				layout: 'lockup',
				label: 'Colorful + noise'
			}
		])}
  </section>

  <div class="hr"></div>
  <section id="colorful">
    <div class="eyebrow">System</div><h2>Colorful palette</h2>
    <p class="lede">The colorful background is a set of color draws over film-grain noise, in two finishes: <b style="color:var(--ink);font-weight:600">flat</b> (gradient + noise) and <b style="color:var(--ink);font-weight:600">rich</b> (adds soft circular glows, like the squares and banners). Both are kept — pick per surface. The wordmark stays cream.</p>

    <h3>Dusk <span class="pill">icons · squares · profiles</span></h3>
    <p class="note">The darker violet→blue draw. Use it whenever an icon, square post, or profile photo needs the colorful background, so the cream mark always reads. Square for avatars and app icons; wide where a dusk banner is needed.</p>
    <div class="grid" style="grid-template-columns:repeat(2,1fr)">
      ${bgFig('dusk', 'rich', '1/1', 'Dusk · square', 'rich — circular glows')}
      ${bgFig('dusk', 'flat', '1/1', 'Dusk · square', 'flat — gradient + noise')}
    </div>
    <div class="grid" style="grid-template-columns:repeat(2,1fr)">
      ${bgFig('dusk', 'rich', '1640/624', 'Dusk · wide', 'rich — circular glows')}
      ${bgFig('dusk', 'flat', '1640/624', 'Dusk · wide', 'flat — gradient + noise')}
    </div>

    <h3>Color draws <span class="pill">flat &amp; rich</span></h3>
    <p class="note">Each draw in both finishes — flat on the left, rich on the right. Pick any of these per gallery below; the lockup galleries render the rich finish live.</p>
    <div class="grid" style="grid-template-columns:repeat(2,1fr)">${COLOR_DRAWS.map(
			([k, n, nt]) =>
				bgFig(k, 'flat', '1640/624', n, `flat${nt ? ` — ${nt}` : ''}`) +
				bgFig(k, 'rich', '1640/624', n, 'rich — circular glows')
		).join('')}</div>
  </section>

  <div class="hr"></div>
  <section id="cover"><div class="eyebrow">Gallery</div><h2>Cover · 1640×624</h2><p class="lede">Every layout, on white, black, and the colour theme you pick. Each tile exports SVG or PNG.</p>${bgsel('cover', 'periwinkle')}${grid(3, COVER)}</section>
  <div class="hr"></div>
  <section id="square"><div class="eyebrow">Gallery</div><h2>Square · 1080×1080</h2><p class="lede">Instagram &amp; shared posts — larger wordmark so it reads in-app.</p>${bgsel('square', 'dusk')}${grid(3, SQUARE)}</section>
  <div class="hr"></div>
  <section id="portrait"><div class="eyebrow">Gallery</div><h2>Portrait · 1080×1920</h2><p class="lede">Stories &amp; Reels.</p>${bgsel('portrait', 'dusk')}${grid(3, PORTRAIT)}</section>
  <div class="hr"></div>
  <section id="banners"><div class="eyebrow">Gallery</div><h2>Banners</h2><p class="lede">Wide 1500×500 and thin 1128×191 (LinkedIn-style). Thin uses the corner split.</p>${bgsel('banners', 'dusk')}${grid(1, BANNERS)}</section>

  <div class="hr"></div>
  <section id="ads">
    <div class="eyebrow">Marketing</div><h2>Ad creatives · 1080×1080</h2>
    <p class="lede">Paid-social lead ads. Each card carries one headline as the hero, the wordmark as signature — the in-feed image. Primary text, CTA, and targeting live in the campaign.</p>
    <div class="grid" style="grid-template-columns:repeat(2,1fr)">${AD_CREATIVES.map(adCard).join('')}</div>
  </section>

  <div class="hr"></div>
  <section id="profile">
    <div class="eyebrow">Marks &amp; partners</div><h2>Profile &amp; icon</h2>
    <p class="lede">Two icon treatments — the mark alone, and the ✲S monogram (the mark as a small superscript over the “S”). Each works as a rounded-square app icon and a circular avatar, on every background.</p>
    <p class="note">Avatars are displayed tiny, so the colorful grain is tuned to stay a fine, even texture at avatar size instead of averaging away when a platform shrinks the export. The strip below shows it at the sizes platforms actually render.</p>
    ${bgsel('profile', 'dusk')}
    <h3>Shown at real size <span class="pill">downscaled like a platform</span></h3>
    <p class="note">The colorful avatar composed at full export resolution, then shrunk to the sizes platforms display — so you can see the grain holds an even, fine texture at every size.</p>
    <div class="sizerow"><span class="szlabel">Mark</span>${sizeStrip('profile', 'mark')}</div>
    <div class="sizerow"><span class="szlabel">✲S</span>${sizeStrip('profile', 'mono')}</div>
    <h3>Mark</h3>
    <div class="grid" style="grid-template-columns:repeat(3,1fr)">${iconSet('mark')}</div>
    <h3>✲S monogram</h3>
    <div class="grid" style="grid-template-columns:repeat(3,1fr)">${iconSet('mono')}</div>
  </section>

  <div class="hr"></div>
  <section id="stripe">
    <div class="eyebrow">Marks &amp; partners</div><h2>Stripe</h2>
    <p class="lede">Upload targets for Stripe → Settings → Branding (set in both live and test mode). Icon shows in emails, Checkout, the customer portal, and invoices; logo shows in Checkout and invoice PDFs.</p>
    <div class="grid" style="grid-template-columns:repeat(2,1fr)">
      <div class="card"><div class="frame cream" style="min-height:180px"><span style="display:inline-flex;width:140px;height:140px">${MK('#1a1a1a')}</span></div><div class="cap"><b>Icon</b> <span class="dim">— 512×512</span>${dl({ name: 'superextra-stripe-icon', kind: 'mark', bg: 'cream', w: 512, h: 512, markFrac: 0.5 })}</div></div>
      <div class="card"><div class="frame cream" style="min-height:180px"><div style="display:flex;align-items:center;gap:6px;color:#1a1a1a"><span style="display:inline-flex;width:49.5px;height:49.5px;position:relative;top:-11.88px">${MK('#1a1a1a')}</span><span class="wm" style="font-size:66px">Superextra</span></div></div><div class="cap"><b>Logo</b> <span class="dim">— transparent wordmark</span>${dl({ name: 'superextra-stripe-logo', kind: 'lockup', bg: 'transparent', w: 0, h: 480 })}</div></div>
    </div>
    <p class="note">Companion settings — Brand color <code>#1A1A1A</code>, Accent <code>#FEFDF9</code>, Checkout font Inter.</p>
  </section>

  <div class="hr"></div>
  <section id="files">
    <div class="eyebrow">Reference</div><h2>Files &amp; naming</h2>
    <p class="lede">Exports follow <code>superextra-&lt;category&gt;-&lt;variant&gt;.png</code> — lowercase, hyphenated, no spaces or versions in the name.</p>
    <table class="files"><thead><tr><th>File</th><th>What it is</th><th>Size</th></tr></thead><tbody>
      <tr><td><code>superextra-mark.svg</code></td><td>Asterisk mark (vector)</td><td>any</td></tr>
      <tr><td><code>superextra-wordmark.png</code></td><td>Mark + wordmark, transparent</td><td>1760×480</td></tr>
      <tr><td>neutral backgrounds</td><td>Flat colours — white #FEFDF9, black #141210; no asset, baked into each export</td><td>—</td></tr>
      <tr><td>colourful backgrounds</td><td>Generated live in-browser per asset (no files) — pick a theme per gallery, then export the composed tile as SVG/PNG</td><td>any</td></tr>
      <tr><td><code>superextra-&lt;platform&gt;-&lt;format&gt;.png</code></td><td>Social exports, e.g. <code>superextra-instagram-square.png</code></td><td>platform spec, 2×</td></tr>
    </tbody></table>
  </section>

</main>`;

mkdirSync(join(root, 'src/lib/brand'), { recursive: true });
writeFileSync(join(root, 'src/lib/brand/brand-content.html'), html);
console.log('Wrote src/lib/brand/brand-content.html (' + html.length + ' chars)');
