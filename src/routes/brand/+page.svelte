<script lang="ts">
	import { onMount } from 'svelte';
	import { DRAWS, paintColorful, type Draw } from '$lib/brand/colorful-bg';
	import {
		MARK_LINES,
		MARK_VB,
		MARK_STROKE,
		MARK_K,
		GAP_K,
		RAISE_K,
		MONO_MARK_K,
		MONO_GAP_K,
		MONO_DROP_K,
		lockupGeom
	} from '$lib/brand/brand-geometry';

	const PIN_LENGTH = 4;

	let html = $state<string | null>(null);
	let phase = $state<'locked' | 'revealing' | 'unlocked'>('locked');
	let digits = $state<string[]>(Array(PIN_LENGTH).fill(''));
	let shake = $state(false);
	let busy = $state(false);
	let inputs: HTMLInputElement[] = [];
	// The injected gallery content, and each gallery's currently-selected colour theme.
	let content = $state<HTMLElement | undefined>(undefined);
	let selectedTheme: Record<string, string> = $state({});

	function b64ToBytes(b64: string) {
		return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
	}

	async function tryDecrypt(pin: string): Promise<string | null> {
		try {
			// Loaded only when a PIN is actually checked — a cached reload reads
			// plaintext from sessionStorage and never fetches the 80 KB bundle.
			const { BRAND_SALT, BRAND_IV, BRAND_CIPHERTEXT, BRAND_ITERATIONS } =
				await import('$lib/brand/brand-encrypted');
			const keyMaterial = await crypto.subtle.importKey(
				'raw',
				new TextEncoder().encode(pin),
				'PBKDF2',
				false,
				['deriveKey']
			);
			const key = await crypto.subtle.deriveKey(
				{
					name: 'PBKDF2',
					salt: b64ToBytes(BRAND_SALT),
					iterations: BRAND_ITERATIONS,
					hash: 'SHA-256'
				},
				keyMaterial,
				{ name: 'AES-GCM', length: 256 },
				false,
				['decrypt']
			);
			const decrypted = await crypto.subtle.decrypt(
				{ name: 'AES-GCM', iv: b64ToBytes(BRAND_IV) },
				key,
				b64ToBytes(BRAND_CIPHERTEXT)
			);
			return new TextDecoder().decode(decrypted);
		} catch {
			return null;
		}
	}

	onMount(() => {
		const cached = sessionStorage.getItem('brand_html');
		if (cached !== null) {
			html = cached;
			phase = 'unlocked';
			return;
		}
		if (window.matchMedia('(pointer: fine)').matches) inputs[0]?.focus();
	});

	async function onDigit(index: number, value: string) {
		if (busy) return;
		if (value && !/^\d$/.test(value)) {
			digits[index] = '';
			return;
		}
		digits[index] = value;
		if (value && index < PIN_LENGTH - 1) inputs[index + 1]?.focus();

		if (digits.every((d) => d !== '')) {
			busy = true;
			const result = await tryDecrypt(digits.join(''));
			busy = false;
			if (result) {
				sessionStorage.setItem('brand_html', result);
				html = result;
				phase = 'revealing';
				setTimeout(() => (phase = 'unlocked'), 400);
			} else {
				shake = true;
				setTimeout(() => {
					shake = false;
					digits = Array(PIN_LENGTH).fill('');
					inputs[0]?.focus();
				}, 500);
			}
		}
	}

	function onKeydown(index: number, e: KeyboardEvent) {
		if (e.key === 'Backspace' && !digits[index] && index > 0) inputs[index - 1]?.focus();
	}

	// ── Asset downloads (SVG + PNG, generated client-side) ───────────────────
	// The mark is four lines; PNG is drawn straight onto a canvas (and text via the
	// loaded system font), so exports are crisp at any size with no rasterization.
	type DL = {
		name: string;
		kind: 'mark' | 'monogram' | 'lockup' | 'tile';
		bg: 'transparent' | 'cream' | 'black' | 'color';
		w: number;
		h: number;
		markFrac?: number;
		layout?: 'lockup' | 'split' | 'splitbr';
		k?: number;
		m?: number;
		gallery?: string; // colour tile → resolve theme from this gallery's picker
	};
	const DL_FONT = "-apple-system,BlinkMacSystemFont,'Inter',ui-sans-serif,system-ui,sans-serif";
	const dlInk = (bg: string) => (bg === 'black' || bg === 'color' ? '#fefdf9' : '#1a1a1a');

	// Resolve a colour tile's Draw from its gallery's current theme pick.
	function resolveDraw(d: DL): Draw | undefined {
		if (d.bg !== 'color' || !d.gallery) return undefined;
		const key = selectedTheme[d.gallery];
		return key ? DRAWS[key]?.rich : undefined;
	}
	function colorName(d: DL): string {
		const key = (d.gallery && selectedTheme[d.gallery]) || 'colour';
		return d.name.replace(/color$/, key);
	}
	function dlMeasure(text: string, fontPx: number): number {
		const c = document.createElement('canvas').getContext('2d')!;
		c.font = `300 ${fontPx}px ${DL_FONT}`;
		c.letterSpacing = '-0.025em';
		return c.measureText(text).width;
	}
	function dlStrokeMark(
		ctx: CanvasRenderingContext2D,
		x: number,
		y: number,
		box: number,
		c: string
	) {
		ctx.strokeStyle = c;
		ctx.lineWidth = (box * MARK_STROKE) / MARK_VB;
		ctx.lineCap = 'butt';
		for (const [x1, y1, x2, y2] of MARK_LINES) {
			ctx.beginPath();
			ctx.moveTo(x + (x1 / MARK_VB) * box, y + (y1 / MARK_VB) * box);
			ctx.lineTo(x + (x2 / MARK_VB) * box, y + (y2 / MARK_VB) * box);
			ctx.stroke();
		}
	}
	function dlPaintBg(ctx: CanvasRenderingContext2D, bg: string, w: number, h: number, draw?: Draw) {
		if (bg === 'cream') {
			ctx.fillStyle = '#fefdf9';
			ctx.fillRect(0, 0, w, h);
		} else if (bg === 'black') {
			ctx.fillStyle = '#141210';
			ctx.fillRect(0, 0, w, h);
		} else if (bg === 'color' && draw) {
			paintColorful(ctx, w, h, draw);
		}
	}
	function dlSetText(ctx: CanvasRenderingContext2D, px: number, c: string) {
		ctx.fillStyle = c;
		ctx.font = `300 ${px}px ${DL_FONT}`;
		ctx.letterSpacing = '-0.025em';
		ctx.textBaseline = 'middle';
	}
	// Gallery-tile geometry — the shared lockup layout, so the canvas exports and the
	// CSS preview place the mark/wordmark/tagline on identical coordinates.
	function dlTileGeom(d: DL) {
		return lockupGeom(d.w, d.h, d.k ?? 1, d.m ?? 0.12, d.layout ?? 'lockup');
	}
	function dlTileTag(ctx: CanvasRenderingContext2D, g: ReturnType<typeof dlTileGeom>, c: string) {
		ctx.fillStyle = c;
		ctx.font = `300 ${g.tagsz}px ${DL_FONT}`;
		ctx.letterSpacing = '0.01em';
		ctx.textBaseline = 'alphabetic';
		ctx.textAlign = g.tagAnchor === 'end' ? 'right' : 'left';
		ctx.fillText('AI consultant for every restaurant', g.tagX, g.tagBaseline);
		ctx.textAlign = 'left';
	}
	async function dlPNG(d: DL, draw?: Draw): Promise<Blob | null> {
		await document.fonts.ready;
		const color = dlInk(d.bg);
		let w = d.w;
		const h = d.h;
		const cv = document.createElement('canvas');
		const ctx = cv.getContext('2d')!;
		if (d.kind === 'lockup') {
			const word = h * 0.55;
			w = Math.ceil(word * MARK_K + word * GAP_K + dlMeasure('Superextra', word));
		}
		cv.width = w;
		cv.height = h;
		dlPaintBg(ctx, d.bg, w, h, draw);
		if (d.kind === 'tile') {
			const g = dlTileGeom(d);
			dlSetText(ctx, g.word, color);
			ctx.fillText('Superextra', g.wordX, g.wordCY);
			dlStrokeMark(ctx, g.markX, g.markY, g.markw, color);
			dlTileTag(ctx, g, color);
		} else if (d.kind === 'lockup') {
			const word = h * 0.55,
				markBox = word * MARK_K,
				gap = word * GAP_K,
				raise = word * RAISE_K;
			dlSetText(ctx, word, color);
			ctx.fillText('Superextra', markBox + gap, h / 2);
			dlStrokeMark(ctx, 0, (h - markBox) / 2 - raise, markBox, color);
		} else if (d.kind === 'monogram') {
			const sf = Math.min(w, h) * 0.5,
				markBox = sf * MONO_MARK_K,
				gap = sf * MONO_GAP_K,
				raise = sf * RAISE_K,
				drop = sf * MONO_DROP_K;
			const x0 = (w - (markBox + gap + dlMeasure('S', sf))) / 2;
			dlSetText(ctx, sf, color);
			ctx.fillText('S', x0 + markBox + gap, h / 2 + drop);
			dlStrokeMark(ctx, x0, (h - markBox) / 2 - raise + drop, markBox, color);
		} else {
			const box = Math.min(w, h) * (d.markFrac ?? 0.7);
			dlStrokeMark(ctx, (w - box) / 2, (h - box) / 2, box, color);
		}
		return await new Promise<Blob | null>((res) => cv.toBlob(res, 'image/png'));
	}
	function dlSVGMark(ox: number, oy: number, box: number, c: string): string {
		const sw = ((box * MARK_STROKE) / MARK_VB).toFixed(2);
		return MARK_LINES.map(
			([x1, y1, x2, y2]) =>
				`<line x1="${(ox + (x1 / MARK_VB) * box).toFixed(2)}" y1="${(oy + (y1 / MARK_VB) * box).toFixed(2)}" x2="${(ox + (x2 / MARK_VB) * box).toFixed(2)}" y2="${(oy + (y2 / MARK_VB) * box).toFixed(2)}" stroke="${c}" stroke-width="${sw}"/>`
		).join('');
	}
	function dlSVGText(x: number, h: number, px: number, c: string, t: string): string {
		return `<text x="${x.toFixed(2)}" y="${(h / 2).toFixed(2)}" font-family="${DL_FONT}" font-weight="300" font-size="${px.toFixed(2)}" letter-spacing="-0.025em" dominant-baseline="central" fill="${c}">${t}</text>`;
	}
	function dlSVG(d: DL, draw?: Draw): string {
		const color = dlInk(d.bg);
		let w = d.w;
		const h = d.h;
		let body: string;
		if (d.kind === 'tile') {
			const g = dlTileGeom(d);
			body =
				dlSVGMark(g.markX, g.markY, g.markw, color) +
				`<text x="${g.wordX.toFixed(2)}" y="${g.wordCY.toFixed(2)}" font-family="${DL_FONT}" font-weight="300" font-size="${g.word.toFixed(2)}" letter-spacing="-0.025em" dominant-baseline="central" fill="${color}">Superextra</text>` +
				`<text x="${g.tagX.toFixed(2)}" y="${g.tagBaseline.toFixed(2)}" font-family="${DL_FONT}" font-weight="300" font-size="${g.tagsz.toFixed(2)}" letter-spacing="0.01em" text-anchor="${g.tagAnchor}" fill="${color}">AI consultant for every restaurant</text>`;
		} else if (d.kind === 'lockup') {
			const word = h * 0.55,
				markBox = word * MARK_K,
				gap = word * GAP_K,
				raise = word * RAISE_K;
			w = Math.ceil(markBox + gap + dlMeasure('Superextra', word));
			body =
				dlSVGMark(0, (h - markBox) / 2 - raise, markBox, color) +
				dlSVGText(markBox + gap, h, word, color, 'Superextra');
		} else if (d.kind === 'monogram') {
			const sf = Math.min(w, h) * 0.5,
				markBox = sf * MONO_MARK_K,
				gap = sf * MONO_GAP_K,
				raise = sf * RAISE_K,
				drop = sf * MONO_DROP_K;
			const x0 = (w - (markBox + gap + dlMeasure('S', sf))) / 2;
			// dlSVGText centres at h/2; pass h + 2·drop so the baseline lands at h/2 + drop.
			body =
				dlSVGMark(x0, (h - markBox) / 2 - raise + drop, markBox, color) +
				dlSVGText(x0 + markBox + gap, h + 2 * drop, sf, color, 'S');
		} else {
			const box = Math.min(w, h) * (d.markFrac ?? 0.7);
			body = dlSVGMark((w - box) / 2, (h - box) / 2, box, color);
		}
		let bgEl = '';
		if (d.bg === 'cream') bgEl = `<rect width="${w}" height="${h}" fill="#fefdf9"/>`;
		else if (d.bg === 'black') bgEl = `<rect width="${w}" height="${h}" fill="#141210"/>`;
		else if (d.bg === 'color' && draw) {
			// Rasterise the live background and embed it (vector lockup over a raster bg).
			const bc = document.createElement('canvas');
			bc.width = w;
			bc.height = h;
			paintColorful(bc.getContext('2d')!, w, h, draw);
			bgEl = `<image href="${bc.toDataURL('image/png')}" width="${w}" height="${h}" preserveAspectRatio="xMidYMid slice"/>`;
		}
		return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">${bgEl}${body}</svg>`;
	}
	function dlSave(data: Blob | string, filename: string, type: string) {
		const blob = typeof data === 'string' ? new Blob([data], { type }) : data;
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = filename;
		a.click();
		setTimeout(() => URL.revokeObjectURL(url), 2000);
	}
	async function onAssetClick(e: MouseEvent) {
		const btn = (e.target as HTMLElement).closest('button.dl') as HTMLElement | null;
		if (!btn) return;
		const host = btn.closest('[data-dl]') as HTMLElement | null;
		if (!host?.dataset.dl) return;
		const d = JSON.parse(host.dataset.dl) as DL;
		const draw = resolveDraw(d);
		const name = d.bg === 'color' ? colorName(d) : d.name;
		if (btn.dataset.fmt === 'svg') dlSave(dlSVG(d, draw), `${name}.svg`, 'image/svg+xml');
		else {
			const blob = await dlPNG(d, draw);
			if (blob) dlSave(blob, `${name}.png`, 'image/png');
		}
	}

	// ── Live colourful backgrounds ───────────────────────────────────────────
	// Each colour tile/swatch is a <canvas>; paint it from the engine, sized to its
	// display pixels so the film grain reads at the same zoom on every asset size.
	function paintCanvas(cv: HTMLCanvasElement) {
		const cw = Math.round(cv.clientWidth);
		const ch = Math.round(cv.clientHeight);
		if (!cw || !ch) return;
		const dpr = Math.min(window.devicePixelRatio || 1, 2);
		cv.width = Math.round(cw * dpr);
		cv.height = Math.round(ch * dpr);
		const ctx = cv.getContext('2d')!;
		let draw: Draw | undefined;
		if (cv.dataset.gallery) {
			draw = DRAWS[selectedTheme[cv.dataset.gallery]]?.rich;
		} else if (cv.dataset.draw) {
			const t = DRAWS[cv.dataset.draw];
			draw = t && (cv.dataset.finish === 'flat' ? t.flat : t.rich);
		}
		if (draw) paintColorful(ctx, cv.width, cv.height, draw);
	}
	function paintScope(sel: string) {
		content?.querySelectorAll<HTMLCanvasElement>(sel).forEach(paintCanvas);
	}
	function initThemes() {
		const sel: Record<string, string> = {};
		content?.querySelectorAll<HTMLElement>('.bgsel').forEach((el) => {
			if (el.dataset.gallery && el.dataset.default) sel[el.dataset.gallery] = el.dataset.default;
		});
		selectedTheme = sel;
	}
	function onThemeClick(e: MouseEvent) {
		const btn = (e.target as HTMLElement).closest('button.theme') as HTMLElement | null;
		if (!btn) return;
		const sel = btn.closest('.bgsel') as HTMLElement | null;
		const g = sel?.dataset.gallery;
		const key = btn.dataset.theme;
		if (!g || !key) return;
		selectedTheme = { ...selectedTheme, [g]: key };
		sel.querySelectorAll('button.theme').forEach((b) => b.classList.toggle('active', b === btn));
		paintScope(`canvas.bgc[data-gallery="${g}"]`);
	}
	// One delegated click handler for the injected content; download and theme clicks
	// are mutually exclusive (button.dl vs button.theme), so each guards itself.
	function onContentClick(e: MouseEvent) {
		onAssetClick(e);
		onThemeClick(e);
	}
	$effect(() => {
		if (phase !== 'unlocked') return;
		let ro: ResizeObserver | undefined;
		let raf = requestAnimationFrame(() => {
			initThemes();
			paintScope('canvas.bgc');
			ro = new ResizeObserver(() => {
				cancelAnimationFrame(raf);
				raf = requestAnimationFrame(() => paintScope('canvas.bgc'));
			});
			if (content) ro.observe(content);
		});
		document.addEventListener('click', onContentClick);
		return () => {
			document.removeEventListener('click', onContentClick);
			ro?.disconnect();
			cancelAnimationFrame(raf);
		};
	});
</script>

<svelte:head>
	<title>Superextra — Brand</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

{#if phase === 'unlocked'}
	<!-- Trusted source: our own HTML, AES-GCM-decrypted from the bundled ciphertext (never user input).
	     DOMPurify isn't used because the content ships its own <style> block, which sanitizers strip. -->
	<!-- eslint-disable-next-line svelte/no-at-html-tags -->
	<div class="reveal" bind:this={content}>{@html html}</div>
{:else}
	<div class="gate" class:fade-out={phase === 'revealing'}>
		<svg class="gmark" viewBox="0 0 {MARK_VB} {MARK_VB}" fill="none">
			{#each MARK_LINES as [x1, y1, x2, y2] (x1 + ',' + y1 + ',' + x2 + ',' + y2)}
				<line {x1} {y1} {x2} {y2} stroke="currentColor" stroke-width={MARK_STROKE} />
			{/each}
		</svg>
		<div class="pins" class:shake>
			{#each digits as d, i (i)}
				<input
					bind:this={inputs[i]}
					type="text"
					inputmode="numeric"
					maxlength="1"
					value={d}
					disabled={busy}
					oninput={(e) => onDigit(i, e.currentTarget.value)}
					onkeydown={(e) => onKeydown(i, e)}
				/>
			{/each}
		</div>
	</div>
{/if}

<style>
	.gate {
		position: fixed;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 22px;
		background: #1a1714;
		color: #ede9e3;
		animation: fade-in 0.4s ease;
	}
	.gate.fade-out {
		animation: fade-out 0.4s ease forwards;
	}
	.gmark {
		width: 26px;
		height: 26px;
		opacity: 0.55;
	}
	.pins {
		display: flex;
		gap: 12px;
	}
	/* Cached reload: pre-paint guard in app.html hides the prompt so the
	   gate reads as a loading splash until the content hydrates in. */
	:global(html[data-brand-unlocked]) .pins {
		display: none;
	}
	.pins input {
		height: 52px;
		width: 42px;
		border-radius: 9px;
		border: 1px solid rgba(237, 233, 227, 0.16);
		background: transparent;
		text-align: center;
		font-size: 20px;
		color: #ede9e3;
		outline: none;
		transition: border-color 0.2s ease;
		font-family: 'Inter', system-ui, sans-serif;
	}
	.pins input:focus {
		border-color: rgba(237, 233, 227, 0.5);
	}
	.pins input:disabled {
		opacity: 0.3;
	}
	.pins.shake {
		animation: shake 0.45s ease;
	}
	.reveal {
		animation: fade-in 0.5s ease;
	}
	@keyframes fade-in {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}
	@keyframes fade-out {
		from {
			opacity: 1;
		}
		to {
			opacity: 0;
		}
	}
	@keyframes shake {
		0%,
		100% {
			transform: translateX(0);
		}
		20%,
		60% {
			transform: translateX(-7px);
		}
		40%,
		80% {
			transform: translateX(7px);
		}
	}
</style>
