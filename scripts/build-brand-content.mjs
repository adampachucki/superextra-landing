/**
 * Generates the Superextra brand-collection HTML (src/lib/brand/brand-content.html).
 * Pure HTML/CSS — gallery tiles use container-query (cqw) units so they scale crisply
 * with no per-tile images. Only the colorful backgrounds + avatar + Stripe marks are files.
 *
 * Run:  node scripts/build-brand-content.mjs   (then: npm run encrypt-brand <PIN>)
 */
import { writeFileSync, mkdirSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const A = '/brand-assets'; // served from static/brand-assets

const MK = (c) =>
	`<svg viewBox="0 0 12 12" fill="none"><line x1="6" y1="0.5" x2="6" y2="11.5" stroke="${c}" stroke-width="1.5"/><line x1="1.24" y1="3.25" x2="10.76" y2="8.75" stroke="${c}" stroke-width="1.5"/><line x1="1.24" y1="8.75" x2="10.76" y2="3.25" stroke="${c}" stroke-width="1.5"/></svg>`;

// ── Temp exploration: asterisk with extra arms ───────────────────────────────
// Each variant is a set of lines through the center (6,6), radius ≈5.5 (matches MK).
const LN = ([x1, y1, x2, y2], c, sw = 1.5) =>
	`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${c}" stroke-width="${sw}"/>`;
const AST = (lines, c, style = '', sw = 1.5) =>
	`<svg viewBox="0 0 12 12" fill="none" style="${style}">${lines.map((l) => LN(l, c, sw)).join('')}</svg>`;
const V = [6, 0.5, 6, 11.5]; // 90° (vertical)
const H = [0.5, 6, 11.5, 6]; // 0° (horizontal)
const D1 = [1.24, 3.25, 10.76, 8.75]; // ±30° diagonals (today's mark)
const D2 = [1.24, 8.75, 10.76, 3.25];
const X1 = [2.11, 2.11, 9.89, 9.89]; // 45° diagonals (even 8-point)
const X2 = [2.11, 9.89, 9.89, 2.11]; // 135°
const ARM_VARIANTS = [
	{ name: '6-point — current', lines: [V, D1, D2], note: "today's mark · 3 lines, arms every 60°" },
	// Thinner stroke: four lines cross at one point, so 1.5 reads heavier here.
	{
		name: '8-point — even',
		lines: [V, H, X1, X2],
		sw: 1.3,
		note: '+2 arms · 4 lines, arms every 45°'
	}
];
function armCard(v) {
	const sw = v.sw ?? 1.5;
	const r = (n) => n.toFixed(2);
	// Lockup mark/gap/raise locked to the logo system's exact ratios — mark 18/22,
	// gap 2/22, raise 8/22 of the wordmark size (same as tile() and the Logo section).
	const WORD = 38,
		MARKW = WORD * (18 / 22),
		GAP = WORD * (2 / 22),
		RAISE = WORD * (8 / 22);
	const big = AST(v.lines, '#1a1a1a', 'width:92px;height:92px', sw);
	const lk = AST(
		v.lines,
		'#1a1a1a',
		`width:${r(MARKW)}px;height:${r(MARKW)}px;margin-top:-${r(RAISE)}px`,
		sw
	);
	const sm = AST(v.lines, '#1a1a1a', 'width:18px;height:18px', sw);
	return `<div class="card"><div class="frame cream" style="min-height:230px;flex-direction:column;gap:20px">${big}<div style="display:flex;align-items:center;gap:${r(GAP)}px;color:#1a1a1a">${lk}<span class="wm" style="font-size:${WORD}px">Superextra</span></div><div style="display:flex;align-items:center;gap:8px">${sm}<span style="font-size:12px;color:#6f6a62">18px · sidebar size</span></div></div><div class="cap"><b>${v.name}</b> · <span>${v.note}</span></div></div>`;
}

// One gallery tile, sized entirely in cqw (% of the tile's own width).
function tile({ w, h, bg, layout = 'lockup', k = 1, m = 0.12, label, note, bgUrl }) {
	const WORD = 5.85 * k,
		MARKW = WORD * (18 / 22),
		GAP = WORD * (2 / 22),
		RAISE = WORD * (8 / 22),
		TAGSZ = WORD * 0.31;
	const M = ((Math.min(w, h) / w) * m * 100).toFixed(2); // cqw
	const ink = bg === 'white' ? '#1a1a1a' : '#fefdf9';
	const r = (n) => n.toFixed(2);
	const mark = `<div style="display:flex;align-items:center;gap:${r(GAP)}cqw"><span style="display:inline-flex;width:${r(MARKW)}cqw;height:${r(MARKW)}cqw;margin-top:-${r(RAISE)}cqw">${MK(ink)}</span><span class="wm" style="font-size:${r(WORD)}cqw;color:${ink};white-space:nowrap">Superextra</span></div>`;
	const tag = (ex = '') =>
		`<div style="font-size:${r(TAGSZ)}cqw;font-weight:300;letter-spacing:0.01em;color:${ink};white-space:nowrap;${ex}">AI consultant for every restaurant</div>`;
	let inner;
	if (layout === 'split' || layout === 'splitbr') {
		const ta = layout === 'splitbr' ? `right:${M}cqw` : `left:${M}cqw`;
		inner = `<div style="position:absolute;left:${M}cqw;top:${M}cqw">${mark}</div><div style="position:absolute;${ta};bottom:${M}cqw">${tag()}</div>`;
	} else {
		inner = `<div style="position:absolute;left:${M}cqw;bottom:${M}cqw;display:flex;flex-direction:column;align-items:flex-start">${mark}${tag(`margin-top:${r(WORD * 0.14)}cqw;margin-left:${r(MARKW + GAP)}cqw`)}</div>`;
	}
	const aspect = h > w ? 'portrait' : w === h ? 'square' : 'wide';
	const bgcss =
		bg === 'white'
			? 'background:#fefdf9'
			: bg === 'black'
				? 'background:#141210'
				: `background:url(${bgUrl || `${A}/superextra-bg-color-${aspect}.jpg`}) center/cover`;
	return `<figure class="tile"><div class="cv" style="aspect-ratio:${w}/${h};${bgcss}">${inner}</div><figcaption><b>${label}</b>${note ? ` · <span>${note}</span>` : ''}</figcaption></figure>`;
}

const grid = (cols, items) =>
	`<div class="grid" style="grid-template-columns:repeat(${cols},1fr)">${items.map(tile).join('')}</div>`;

// One ad creative: a headline as the hero, the wordmark as a corner signature.
// Same cqw system as tile() so it scales crisply to any export size.
function adCard({ headline, bg = 'white', w = 1080, h = 1080, label, note }) {
	const ink = bg === 'white' ? '#1a1a1a' : '#fefdf9';
	const M = ((Math.min(w, h) / w) * 0.06 * 100).toFixed(2); // cqw
	const aspect = h > w ? 'portrait' : w === h ? 'square' : 'wide';
	const bgcss =
		bg === 'white'
			? 'background:#fefdf9'
			: bg === 'black'
				? 'background:#141210'
				: `background:url(${A}/superextra-bg-color-${aspect}.jpg) center/cover`;
	const r = (n) => n.toFixed(2);
	const WM = 4.6,
		MARKW = WM * (18 / 22),
		GAP = WM * (2 / 22),
		RAISE = WM * (8 / 22);
	const sig = `<div style="position:absolute;left:${M}cqw;bottom:${M}cqw;display:flex;align-items:center;gap:${r(GAP)}cqw"><span style="display:inline-flex;width:${r(MARKW)}cqw;height:${r(MARKW)}cqw;margin-top:-${r(RAISE)}cqw">${MK(ink)}</span><span class="wm" style="font-size:${WM}cqw;color:${ink};white-space:nowrap">Superextra</span></div>`;
	const head = `<div style="position:absolute;left:${M}cqw;right:${M}cqw;top:${M}cqw;font-size:12cqw;line-height:1.06;font-weight:500;letter-spacing:-0.03em;color:${ink}">${headline}</div>`;
	return `<figure class="tile"><div class="cv" style="aspect-ratio:${w}/${h};${bgcss}">${head}${sig}</div><figcaption><b>${label}</b>${note ? ` · <span>${note}</span>` : ''}</figcaption></figure>`;
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

const COVER = matrix(1640, 624);
const SQUARE = matrix(1080, 1080, { k: 1.5, m: 0.075 });
const PORTRAIT = matrix(1080, 1920, { k: 1.5, m: 0.075 });
const BANNERS = [
	{ w: 1500, h: 500, bg: 'white', layout: 'lockup', label: 'Wide', note: 'lockup · white' },
	{
		w: 1500,
		h: 500,
		bg: 'color',
		layout: 'splitbr',
		label: 'Wide',
		note: 'split-right · colorful'
	},
	{ w: 1500, h: 500, bg: 'black', layout: 'split', label: 'Wide', note: 'split-left · black' },
	{ w: 1128, h: 191, bg: 'white', layout: 'splitbr', k: 0.85, label: 'Thin', note: 'white' },
	{ w: 1128, h: 191, bg: 'black', layout: 'splitbr', k: 0.85, label: 'Thin', note: 'black' },
	{ w: 1128, h: 191, bg: 'color', layout: 'splitbr', k: 0.85, label: 'Thin', note: 'colorful' }
];

const html = `<style>
:root{--bg:#1a1714;--panel:#211e1a;--panel2:#262320;--line:#2e2a25;--line2:#3d3832;--ink:#ede9e3;--mut:#9b958c;--soft:#c7c1b8;--cream:#fefdf9;--sb:248px}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--ink);font-family:'Inter',-apple-system,system-ui,sans-serif;-webkit-font-smoothing:antialiased;line-height:1.5}
.wm{font-family:-apple-system,BlinkMacSystemFont,'Inter',ui-sans-serif,system-ui,sans-serif;font-weight:300;letter-spacing:-0.025em}
.sidebar{position:fixed;top:0;left:0;width:var(--sb);height:100vh;overflow-y:auto;background:#171411;border-right:1px solid var(--line);padding:28px 22px 40px}
.sbrand{display:flex;align-items:center;gap:2px;margin-bottom:6px}
.sbrand svg{width:18px;height:18px;margin-top:-8px}.sbrand .nm{font-size:22px;font-family:-apple-system,BlinkMacSystemFont,'Inter',ui-sans-serif,system-ui,sans-serif;font-weight:300;letter-spacing:-0.025em}
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
<aside class="sidebar">
  <div class="sbrand"><svg viewBox="0 0 12 12" fill="none"><line x1="6" y1="0.5" x2="6" y2="11.5" stroke="#ede9e3" stroke-width="1.5"/><line x1="1.24" y1="3.25" x2="10.76" y2="8.75" stroke="#ede9e3" stroke-width="1.5"/><line x1="1.24" y1="8.75" x2="10.76" y2="3.25" stroke="#ede9e3" stroke-width="1.5"/></svg><span class="nm">Superextra</span></div>
  <p class="sbrand-sub">Brand assets &amp; guidelines</p>
  <div class="navgroup"><h4>Foundations</h4><a href="#overview">Overview</a><a href="#logo">Logo</a><a href="#color">Color</a><a href="#type">Typography</a></div>
  <div class="navgroup"><h4>System</h4><a href="#layouts">Layouts</a><a href="#backgrounds">Backgrounds</a><a href="#colorful">Colorful palette</a></div>
  <div class="navgroup"><h4>Gallery</h4><a href="#cover">Cover</a><a href="#square">Square</a><a href="#portrait">Portrait</a><a href="#banners">Banners</a></div>
  <div class="navgroup"><h4>Marketing</h4><a href="#ads">Ad creatives</a></div>
  <div class="navgroup"><h4>Marks &amp; partners</h4><a href="#profile">Profile</a><a href="#stripe">Stripe</a></div>
  <div class="navgroup"><h4>Reference</h4><a href="#files">Files &amp; naming</a></div>
  <div class="navgroup"><h4>Explorations</h4><a href="#explore">Asterisk arms</a></div>
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
    <p class="lede">A six-point asterisk mark beside the “Superextra” wordmark in the system sans, Light weight. The mark sits raised — its center aligns near the cap height of the wordmark.</p>
    <div class="grid" style="grid-template-columns:repeat(2,1fr)">
      <div class="card"><div class="frame cream" style="min-height:200px"><svg viewBox="0 0 12 12" fill="none" style="width:120px;height:120px"><line x1="6" y1="0.5" x2="6" y2="11.5" stroke="#1a1a1a" stroke-width="1.5"/><line x1="1.24" y1="3.25" x2="10.76" y2="8.75" stroke="#1a1a1a" stroke-width="1.5"/><line x1="1.24" y1="8.75" x2="10.76" y2="3.25" stroke="#1a1a1a" stroke-width="1.5"/></svg></div><div class="cap"><b>Mark</b> · the asterisk, used alone as the icon/avatar</div></div>
      <div class="card"><div class="frame cream" style="min-height:200px"><div style="display:flex;align-items:center;gap:6px;color:#1a1a1a"><svg viewBox="0 0 12 12" fill="none" style="width:54px;height:54px;margin-top:-24px"><line x1="6" y1="0.5" x2="6" y2="11.5" stroke="#1a1a1a" stroke-width="1.5"/><line x1="1.24" y1="3.25" x2="10.76" y2="8.75" stroke="#1a1a1a" stroke-width="1.5"/><line x1="1.24" y1="8.75" x2="10.76" y2="3.25" stroke="#1a1a1a" stroke-width="1.5"/></svg><span class="wm" style="font-size:66px">Superextra</span></div></div><div class="cap"><b>Wordmark</b> · mark + name, the primary lockup</div></div>
    </div>
    <div class="do"><div class="b ok"><div class="t">Do</div>Keep the raised mark, Light weight, and −0.025em tracking. Give the logo clear space of at least the mark’s height on every side.</div><div class="b no"><div class="t">Don’t</div>Recolor, outline, stretch, re-space, or swap the typeface. Don’t lower the mark to the baseline.</div></div>
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
				bg: 'white',
				layout: 'lockup',
				label: 'Lockup',
				note: 'tagline under text'
			},
			{
				w: 1640,
				h: 624,
				bg: 'white',
				layout: 'split',
				label: 'Split',
				note: 'tagline bottom-left'
			},
			{
				w: 1640,
				h: 624,
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
    <p class="lede">Every surface uses white, black, or the colorful gradient with noise — rendered at native resolution per size so the grain stays crisp. The colorful background comes in several color draws (see <a href="#colorful" style="color:var(--soft)">Colorful palette</a>).</p>
    ${grid(3, [
			{ w: 1640, h: 624, bg: 'white', layout: 'lockup', label: 'White', note: '#FEFDF9' },
			{ w: 1640, h: 624, bg: 'black', layout: 'lockup', label: 'Black', note: '#141210' },
			{ w: 1640, h: 624, bg: 'color', layout: 'lockup', label: 'Colorful + noise' }
		])}
  </section>

  <div class="hr"></div>
  <section id="colorful">
    <div class="eyebrow">System</div><h2>Colorful palette</h2>
    <p class="lede">The colorful background comes in several color draws — the brand accent palette over film-grain noise. Pick per campaign; the wordmark stays cream.</p>
    <div class="grid" style="grid-template-columns:repeat(2,1fr)">${[
			['periwinkle', 'Periwinkle', 'violet-pink → blue'],
			['lavender-pink', 'Lavender → Pink', 'violet → pink'],
			['violet-cyan', 'Violet → Cyan', ''],
			['blue-teal', 'Blue → Teal', 'indigo → cyan'],
			['indigo-violet', 'Indigo → Violet', ''],
			['mint', 'Mint', 'emerald → cyan']
		]
			.map(
				([k, n, nt]) =>
					`<figure class="tile"><div class="cv" style="aspect-ratio:1640/624;background:url(${A}/superextra-bg-${k}.jpg) center/cover"></div><figcaption><b>${n}</b>${nt ? ` · <span>${nt}</span>` : ''}</figcaption></figure>`
			)
			.join('')}</div>
    <h3>On the colorful backgrounds</h3>
    <p class="note">The lockup over a few of the draws — cream wordmark, same placement system.</p>
    ${grid(2, [
			{
				w: 1640,
				h: 624,
				bg: 'color',
				bgUrl: `${A}/superextra-bg-periwinkle.jpg`,
				layout: 'lockup',
				label: 'Periwinkle',
				note: 'lockup'
			},
			{
				w: 1640,
				h: 624,
				bg: 'color',
				bgUrl: `${A}/superextra-bg-lavender-pink.jpg`,
				layout: 'splitbr',
				label: 'Lavender → Pink',
				note: 'split'
			},
			{
				w: 1640,
				h: 624,
				bg: 'color',
				bgUrl: `${A}/superextra-bg-blue-teal.jpg`,
				layout: 'lockup',
				label: 'Blue → Teal',
				note: 'lockup'
			},
			{
				w: 1640,
				h: 624,
				bg: 'color',
				bgUrl: `${A}/superextra-bg-violet-cyan.jpg`,
				layout: 'splitbr',
				label: 'Violet → Cyan',
				note: 'split'
			}
		])}
  </section>

  <div class="hr"></div>
  <section id="cover"><div class="eyebrow">Gallery</div><h2>Cover · 1640×624</h2><p class="lede">Every layout across every background.</p>${grid(3, COVER)}</section>
  <div class="hr"></div>
  <section id="square"><div class="eyebrow">Gallery</div><h2>Square · 1080×1080</h2><p class="lede">Instagram &amp; shared posts — larger wordmark so it reads in-app.</p>${grid(3, SQUARE)}</section>
  <div class="hr"></div>
  <section id="portrait"><div class="eyebrow">Gallery</div><h2>Portrait · 1080×1920</h2><p class="lede">Stories &amp; Reels.</p>${grid(3, PORTRAIT)}</section>
  <div class="hr"></div>
  <section id="banners"><div class="eyebrow">Gallery</div><h2>Banners</h2><p class="lede">Wide 1500×500 and thin 1128×191 (LinkedIn-style). Thin uses the corner split.</p>${grid(1, BANNERS)}</section>

  <div class="hr"></div>
  <section id="ads">
    <div class="eyebrow">Marketing</div><h2>Ad creatives · 1080×1080</h2>
    <p class="lede">Paid-social lead ads. Each card carries one headline as the hero, the wordmark as signature — the in-feed image. Primary text, CTA, and targeting live in the campaign.</p>
    <div class="grid" style="grid-template-columns:repeat(2,1fr)">${AD_CREATIVES.map(adCard).join('')}</div>
  </section>

  <div class="hr"></div>
  <section id="profile">
    <div class="eyebrow">Marks &amp; partners</div><h2>Profile &amp; avatar</h2>
    <p class="lede">One square mark-on-cream avatar serves every platform. It crops cleanly to a circle (Instagram, X, Facebook) and a rounded square (LinkedIn, Google).</p>
    <div class="grid" style="grid-template-columns:repeat(4,1fr)">
      <div class="card"><div class="frame" style="padding:22px"><img src="${A}/superextra-avatar.png" style="width:120px;border-radius:50%"/></div><div class="cap"><b>Circle</b> <span class="dim">— IG · X · FB</span></div></div>
      <div class="card"><div class="frame" style="padding:22px"><img src="${A}/superextra-avatar.png" style="width:120px;border-radius:16px"/></div><div class="cap"><b>Square</b> <span class="dim">— LinkedIn · Google</span></div></div>
    </div>
  </section>

  <div class="hr"></div>
  <section id="stripe">
    <div class="eyebrow">Marks &amp; partners</div><h2>Stripe</h2>
    <p class="lede">Upload targets for Stripe → Settings → Branding (set in both live and test mode). Icon shows in emails, Checkout, the customer portal, and invoices; logo shows in Checkout and invoice PDFs.</p>
    <div class="grid" style="grid-template-columns:repeat(2,1fr)">
      <div class="card"><div class="frame cream"><img src="${A}/superextra-stripe-icon.png" style="width:150px"/></div><div class="cap"><b>Icon</b> <span class="dim">— 512×512</span></div></div>
      <div class="card"><div class="frame cream"><img src="${A}/superextra-stripe-logo.png" style="width:80%"/></div><div class="cap"><b>Logo</b> <span class="dim">— transparent wordmark</span></div></div>
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
      <tr><td><code>superextra-avatar.png</code></td><td>Square avatar, all platforms</td><td>1080×1080</td></tr>
      <tr><td><code>superextra-bg-{white,black}.png</code></td><td>Neutral backgrounds</td><td>per format</td></tr>
      <tr><td><code>superextra-bg-color-{wide,square,portrait}.png</code></td><td>Colorful + noise, native per aspect</td><td>1640×624 · 1080² · 1080×1920</td></tr>
      <tr><td><code>superextra-stripe-icon.png</code></td><td>Stripe icon</td><td>512×512</td></tr>
      <tr><td><code>superextra-stripe-logo.png</code></td><td>Stripe logo, transparent</td><td>1760×480</td></tr>
      <tr><td><code>superextra-&lt;platform&gt;-&lt;format&gt;.png</code></td><td>Social exports, e.g. <code>superextra-instagram-square.png</code></td><td>platform spec, 2×</td></tr>
    </tbody></table>
  </section>

  <div class="hr"></div>
  <section id="explore">
    <div class="eyebrow">Temp · exploration</div><h2>Asterisk — extra arms</h2>
    <p class="lede">A scratchpad, not part of the system. The mark is a six-point asterisk today — three lines crossing at the center. This explores two more arms: an even eight-point, four lines 45° apart. Each is shown large, in the lockup, and at 18px sidebar size.</p>
    <div class="grid" style="grid-template-columns:repeat(2,1fr)">${ARM_VARIANTS.map(armCard).join('')}</div>
    <p class="note">More arms means a denser center — where the strokes cross, the eight-point can clog at small sizes. A thinner stroke (≈1.2) or a small center gap would offset it.</p>
  </section>
</main>`;

mkdirSync(join(root, 'src/lib/brand'), { recursive: true });
writeFileSync(join(root, 'src/lib/brand/brand-content.html'), html);
console.log('Wrote src/lib/brand/brand-content.html (' + html.length + ' chars)');
