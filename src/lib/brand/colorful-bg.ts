// Live colourful-background engine — a faithful TS port of the canvas renderer that
// produced the approved brand draws. Used by the /brand page for on-page previews AND by
// its SVG/PNG download engine, so preview and export come from one source of truth.
//
// Side-effect-free: only defines DRAWS + paintColorful, all drawing happens at call time
// in the browser, so importing during SvelteKit prerender is safe.

export type Draw = {
	c1: string; // hex, no '#'
	c2: string;
	ang: number; // gradient angle, degrees
	seed: number; // blob layout seed
	rich: boolean; // true → circular blob glows; false → faint near-gradient blobs
	cool?: boolean; // restrict rich blobs to violet/pink/cyan/indigo
	bs?: number; // rich blob strength ×
	br?: number; // rich blob radius ×
	grain?: number; // film-grain overlay alpha (default 0.5)
};

export type Theme = { rich: Draw; flat: Draw };

const theme = (
	c1: string,
	c2: string,
	ang: number,
	seed: number,
	extra: Partial<Draw> = {}
): Theme => ({
	rich: { c1, c2, ang, seed, rich: true, ...extra },
	flat: { c1, c2, ang, seed, rich: false }
});

// The colour themes, in picker order. Params match the approved renders.
export const DRAWS: Record<string, Theme> = {
	periwinkle: theme('b39ddb', '6d8fe3', 6, 3),
	'lavender-pink': theme('a78bfa', 'f472b6', 8, 7),
	'violet-cyan': theme('a78bfa', '22b6d4', 8, 5),
	'blue-teal': theme('6366f1', '06b6d4', 8, 11),
	'indigo-violet': theme('6366f1', 'b39ddb', 8, 9),
	mint: theme('6ee7b7', '2fb6d4', 8, 13),
	dusk: theme('5d47b3', '324fb0', 8, 4, { cool: true, br: 1.5, bs: 0.62 })
};

type RGB = [number, number, number];
const PALETTE: RGB[] = [
	[110, 231, 183],
	[167, 139, 250],
	[244, 114, 182],
	[251, 191, 36],
	[6, 182, 212],
	[99, 102, 241]
];
const COOLPAL: RGB[] = [
	[167, 139, 250],
	[244, 114, 182],
	[6, 182, 212],
	[99, 102, 241]
];
const hx = (h: string): RGB => [
	parseInt(h.slice(0, 2), 16),
	parseInt(h.slice(2, 4), 16),
	parseInt(h.slice(4, 6), 16)
];
const lerp = (a: RGB, b: RGB, t: number): RGB => [
	a[0] + (b[0] - a[0]) * t,
	a[1] + (b[1] - a[1]) * t,
	a[2] + (b[2] - a[2]) * t
];
const lighten = (c: RGB, t: number): RGB => lerp(c, [255, 255, 255], t);

// Paint the full background (gradient -> blobs -> film grain) into ctx at W x H.
// Grain is generated per output pixel, so exported masters keep a fine native texture
// instead of baking in coarse cells for a guessed downstream display size.
export function paintColorful(ctx: CanvasRenderingContext2D, W: number, H: number, d: Draw): void {
	const a = hx(d.c1);
	const b = hx(d.c2);
	const ANG = (d.ang * Math.PI) / 180;
	const RICH = d.rich;
	const GRAIN = d.grain ?? 0.5;
	const BS = d.bs ?? 1;
	const BR = d.br ?? 1;
	let _r = ((d.seed || 3) * 2654435761) >>> 0;
	const rnd = () => {
		_r = (_r * 1103515245 + 12345) & 0x7fffffff;
		return _r / 0x7fffffff;
	};

	// 1) angled base gradient
	const cx = W / 2;
	const cy = H / 2;
	const rad = Math.max(W, H) * 0.62;
	const g = ctx.createLinearGradient(
		cx - Math.cos(ANG) * rad,
		cy - Math.sin(ANG) * rad,
		cx + Math.cos(ANG) * rad,
		cy + Math.sin(ANG) * rad
	);
	g.addColorStop(0, `rgb(${a[0]},${a[1]},${a[2]})`);
	g.addColorStop(1, `rgb(${b[0]},${b[1]},${b[2]})`);
	ctx.fillStyle = g;
	ctx.fillRect(0, 0, W, H);

	// 2) soft radial blobs
	const RPAL = d.cool ? COOLPAL : PALETTE;
	// Flat-finish blobs draw from a near-gradient pool; rich-finish ones use RPAL, so
	// only build the flat pool when it's actually used.
	const flatPOOL: RGB[] = RICH ? [] : [a, b, lerp(a, b, 0.5), lighten(a, 0.28), lighten(b, 0.22)];
	const NB = RICH ? 16 : 4;
	const RBASE = RICH ? (W + H) / 2 : Math.min(W, H);
	for (let i = 0; i < NB; i++) {
		const x = RICH ? (rnd() * 1.3 - 0.15) * W : rnd() * W;
		const y = RICH ? (rnd() * 1.3 - 0.15) * H : rnd() * H;
		const r = ((RICH ? 0.16 : 0.3) + rnd() * (RICH ? 0.24 : 0.4)) * RBASE * (RICH ? BR : 1);
		const col = RICH
			? RPAL[Math.floor(rnd() * RPAL.length)]
			: flatPOOL[Math.floor(rnd() * flatPOOL.length)];
		const op = (RICH ? 0.2 + rnd() * 0.22 : 0.06 + rnd() * 0.03) * (RICH ? BS : 1);
		const c0 = `${col[0] | 0},${col[1] | 0},${col[2] | 0}`;
		const rg = ctx.createRadialGradient(x, y, 0, x, y, r);
		rg.addColorStop(0, `rgba(${c0},0.7)`);
		rg.addColorStop(0.4, `rgba(${c0},0.3)`);
		rg.addColorStop(1, `rgba(${c0},0)`);
		ctx.save();
		ctx.globalAlpha = op;
		ctx.fillStyle = rg;
		ctx.beginPath();
		ctx.arc(x, y, r, 0, 7);
		ctx.fill();
		ctx.restore();
	}

	// 3) film grain. Deterministic (so it doesn't reshuffle on every repaint and matches
	//    exports), but hashed per pixel index - reusing the blob LCG here tiles its lattice
	//    into visible diagonal patterns, so each pixel gets an independent hashed value.
	const off = document.createElement('canvas');
	off.width = W;
	off.height = H;
	const o = off.getContext('2d');
	if (o) {
		const img = o.createImageData(W, H);
		const gseed = Math.imul(d.seed || 3, 0x9e3779b1) >>> 0;
		for (let p = 0, i = 0; i < img.data.length; i += 4, p++) {
			let hsh = (p ^ gseed) >>> 0;
			hsh = Math.imul(hsh ^ (hsh >>> 16), 0x45d9f3b);
			hsh = Math.imul(hsh ^ (hsh >>> 16), 0x45d9f3b);
			hsh ^= hsh >>> 16;
			const v = hsh & 255;
			img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
			img.data[i + 3] = 255;
		}
		o.putImageData(img, 0, 0);
		ctx.save();
		ctx.globalCompositeOperation = 'overlay';
		ctx.globalAlpha = GRAIN;
		ctx.drawImage(off, 0, 0);
		ctx.restore();
	}
}
