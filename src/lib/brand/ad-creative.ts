// Renders one 1080×1080 ad creative two ways from a single source of geometry:
//  - cardInnerHTML(): the live DOM preview (headline as live Inter text + lockup as outlined SVG)
//  - drawCreative()/exportPng(): the same thing rasterised to a canvas for a Meta-ready PNG.
import { lockupGeom, MARK_LINES, MARK_VB, MARK_STROKE } from './brand-geometry.js';
import { markLinesSVG, glyphPathSVG, glyphDefs, glyphWidth, BASELINE_K } from './brand-render.js';
import { UPM, SUPEREXTRA, TAGLINE } from './brand-glyphs.js';
import { paintColorful, DRAWS } from './colorful-bg';
import type { Ad, Bg } from './ads-data';

export { glyphDefs };

const K = 1.2; // wordmark size factor — larger than the /brand signature
const M_FRAC = 0.06; // padding as a fraction of the square
const HEAD_FRAC = 0.12; // headline font-size as a fraction of the square
const SYS = "-apple-system,BlinkMacSystemFont,'Inter',ui-sans-serif,system-ui,sans-serif";

const ink = (bg: Bg) => (bg === 'white' ? '#1a1a1a' : '#fefdf9');
export const fill = (ad: Ad) =>
	ad.bg === 'black' ? '#141210' : ad.bg === 'color' ? '#6366f1' : '#fefdf9';

const WORD_REF = { ref: 'se-word', adv: SUPEREXTRA.adv };
const TAG_REF = { ref: 'se-tag', adv: TAGLINE.adv };

// --- DOM preview (SVG overlay) -------------------------------------------------

function lockupBody(w: number, h: number, color: string, withTag: boolean): string {
	const g = lockupGeom(w, h, K, M_FRAC, 'lockup');
	let s = markLinesSVG(g.markX, g.markY, g.markw, color);
	s += glyphPathSVG(WORD_REF, g.wordX, g.wordCY + BASELINE_K * g.word, g.word, color);
	if (withTag) {
		const tagX = g.tagAnchor === 'end' ? g.tagX - glyphWidth(TAGLINE, g.tagsz) : g.tagX;
		s += glyphPathSVG(TAG_REF, tagX, g.tagBaseline, g.tagsz, color);
	}
	return s;
}

/** The creative's inner HTML — headline (live text) + lockup (SVG). cqw resolves against
 * the container, so the same string scales to any preview size. */
export function cardInnerHTML(ad: Ad): string {
	const color = ink(ad.bg);
	const M = M_FRAC * 100;
	const head = `<div style="position:absolute;left:${M}cqw;right:${M}cqw;top:${M}cqw;font-size:${HEAD_FRAC * 100}cqw;line-height:1.06;font-weight:500;letter-spacing:-0.03em;color:${color};font-family:${SYS}">${ad.hero}</div>`;
	const lock = `<svg viewBox="0 0 1080 1080" preserveAspectRatio="none" aria-hidden="true" style="position:absolute;inset:0;width:100%;height:100%">${lockupBody(1080, 1080, color, ad.taglineOnCard)}</svg>`;
	return head + lock;
}

// --- PNG export (canvas) -------------------------------------------------------

function drawLockup(
	ctx: CanvasRenderingContext2D,
	S: number,
	color: string,
	withTag: boolean
): void {
	const g = lockupGeom(S, S, K, M_FRAC, 'lockup');
	// mark — four strokes
	ctx.save();
	ctx.strokeStyle = color;
	ctx.lineWidth = (g.markw * MARK_STROKE) / MARK_VB;
	for (const [x1, y1, x2, y2] of MARK_LINES) {
		ctx.beginPath();
		ctx.moveTo(g.markX + (x1 / MARK_VB) * g.markw, g.markY + (y1 / MARK_VB) * g.markw);
		ctx.lineTo(g.markX + (x2 / MARK_VB) * g.markw, g.markY + (y2 / MARK_VB) * g.markw);
		ctx.stroke();
	}
	ctx.restore();
	// wordmark + tagline — outlined glyph paths (font units, y-up)
	const glyph = (d: string, x: number, baseline: number, size: number) => {
		const s = size / UPM;
		ctx.save();
		ctx.translate(x, baseline);
		ctx.scale(s, -s);
		ctx.fillStyle = color;
		ctx.fill(new Path2D(d));
		ctx.restore();
	};
	glyph(SUPEREXTRA.d, g.wordX, g.wordCY + BASELINE_K * g.word, g.word);
	if (withTag) {
		const tagX = g.tagAnchor === 'end' ? g.tagX - glyphWidth(TAGLINE, g.tagsz) : g.tagX;
		glyph(TAGLINE.d, tagX, g.tagBaseline, g.tagsz);
	}
}

/** Draw the full 1080-square creative into a canvas context. Fonts must be ready first. */
export function drawCreative(ctx: CanvasRenderingContext2D, S: number, ad: Ad): void {
	const color = ink(ad.bg);
	// background
	if (ad.bg === 'color') paintColorful(ctx, S, S, DRAWS[ad.colorTheme].rich);
	else {
		ctx.fillStyle = ad.bg === 'black' ? '#141210' : '#fefdf9';
		ctx.fillRect(0, 0, S, S);
	}
	// headline — live Inter, wrapped on the authored <br>s
	const size = HEAD_FRAC * S;
	const lh = size * 1.06;
	const M = M_FRAC * S;
	ctx.save();
	ctx.fillStyle = color;
	ctx.font = `500 ${size}px Inter, ${SYS}`;
	ctx.textBaseline = 'alphabetic';
	if ('letterSpacing' in ctx)
		(ctx as unknown as { letterSpacing: string }).letterSpacing = `${-0.03 * size}px`;
	const lines = ad.hero.split(/<br\s*\/?>/i);
	lines.forEach((line, i) => ctx.fillText(line, M, M + size * 0.82 + i * lh));
	ctx.restore();
	// lockup
	drawLockup(ctx, S, color, ad.taglineOnCard);
}

/** Render the creative to a 1080 PNG and trigger a download. */
export async function exportPng(ad: Ad): Promise<void> {
	const S = 1080;
	await document.fonts.load(`500 ${HEAD_FRAC * S}px Inter`);
	await document.fonts.ready;
	const canvas = document.createElement('canvas');
	canvas.width = canvas.height = S;
	const ctx = canvas.getContext('2d');
	if (!ctx) return;
	drawCreative(ctx, S, ad);
	const blob: Blob | null = await new Promise((r) => canvas.toBlob(r, 'image/png'));
	if (!blob) return;
	const url = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = url;
	a.download = `superextra-ad-${ad.id.toLowerCase()}-${ad.bg}.png`;
	a.click();
	URL.revokeObjectURL(url);
}
