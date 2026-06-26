<script lang="ts">
	// Internal ad studio — compose paid-social campaigns, preview in-feed, export PNGs.
	// Always loads the committed campaign from src/lib/brand/ads-data.ts (no localStorage,
	// so it can never get stuck on a stale state). Edits are session-only — use
	// "Export JSON" to hand changes back to commit into the data file.
	import BrandGate from '$lib/components/brand/BrandGate.svelte';
	import {
		campaigns,
		newAd,
		CTAS,
		COLOR_THEMES,
		type Campaign,
		type Ad,
		type Bg,
		type ColorTheme
	} from '$lib/brand/ads-data';
	import { cardInnerHTML, exportPng, fill, glyphDefs } from '$lib/brand/ad-creative';
	import { paintColorful, DRAWS } from '$lib/brand/colorful-bg';

	let store = $state<Campaign[]>(structuredClone(campaigns));
	let ci = $state(0); // selected campaign index
	let selected = $state(0); // selected ad index within the campaign
	let copied = $state(false);
	let showJson = $state(false);

	const data = $derived(store[ci]);
	const si = $derived(Math.min(selected, data.ads.length - 1)); // clamped ad index
	const ad = $derived(data.ads[si]);

	const BGS: { key: Bg; label: string }[] = [
		{ key: 'white', label: 'Cream' },
		{ key: 'black', label: 'Black' },
		{ key: 'color', label: 'Colour' }
	];

	function setHero(v: string) {
		store[ci].ads[si].hero = v.replace(/\n/g, '<br>');
	}

	function addAd() {
		const id = String.fromCharCode(65 + data.ads.length);
		store[ci].ads.push(newAd(id));
		selected = data.ads.length - 1;
	}
	function duplicateAd() {
		const copy = structuredClone($state.snapshot(ad)) as Ad;
		copy.id = copy.id + '′';
		store[ci].ads.splice(si + 1, 0, copy);
		selected = si + 1;
	}
	function removeAd(i: number) {
		if (data.ads.length <= 1) return;
		store[ci].ads.splice(i, 1);
		selected = Math.max(0, Math.min(selected, data.ads.length - 1));
	}
	function resetToFile() {
		store = structuredClone(campaigns);
		ci = 0;
		selected = 0;
	}
	async function exportJson() {
		const json = JSON.stringify(store, null, 2);
		try {
			await navigator.clipboard.writeText(json);
			copied = true;
			setTimeout(() => (copied = false), 1600);
		} catch {
			/* clipboard blocked — the panel below has the JSON to copy manually */
		}
		showJson = true;
	}

	function paintAd(node: HTMLCanvasElement, theme: ColorTheme) {
		const draw = (t: ColorTheme) => {
			const ctx = node.getContext('2d');
			if (ctx) paintColorful(ctx, node.width, node.height, DRAWS[t].rich);
		};
		draw(theme);
		return { update: (t: ColorTheme) => draw(t) };
	}
</script>

<svelte:head>
	<title>Superextra — Ad studio</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

{#snippet mark()}
	<svg viewBox="0 0 12 12" fill="none" style="width:54%;height:54%">
		<line x1="6" y1="0.5" x2="6" y2="11.5" stroke="#1a1a1a" stroke-width="1.3" />
		<line x1="0.5" y1="6" x2="11.5" y2="6" stroke="#1a1a1a" stroke-width="1.3" />
		<line x1="2.11" y1="2.11" x2="9.89" y2="9.89" stroke="#1a1a1a" stroke-width="1.3" />
		<line x1="2.11" y1="9.89" x2="9.89" y2="2.11" stroke="#1a1a1a" stroke-width="1.3" />
	</svg>
{/snippet}

{#snippet card(a: Ad)}
	<div class="sq" style="background:{fill(a)}">
		{#if a.bg === 'color'}
			<canvas class="bgc" width="1080" height="1080" use:paintAd={a.colorTheme}></canvas>
		{/if}
		<!-- eslint-disable-next-line svelte/no-at-html-tags -- internal: generated headline + lockup SVG, no user input -->
		{@html cardInnerHTML(a)}
	</div>
{/snippet}

{#snippet fbMock(a: Ad)}
	<div class="fb">
		<div class="fb-h">
			<span class="av">{@render mark()}</span>
			<div class="fb-meta">
				<div class="nm">Superextra</div>
				<div class="sub">Sponsored · 🌐</div>
			</div>
			<div class="dots">⋯</div>
		</div>
		<div class="fb-txt">{a.primary}</div>
		{@render card(a)}
		<div class="fb-bar">
			<div class="fb-bar-txt">
				<div class="dom">AGENT.SUPEREXTRA.AI</div>
				<div class="hl">{a.headline}</div>
			</div>
			<button class="cta">{a.cta}</button>
		</div>
		<div class="fb-act"><span>👍 Like</span><span>💬 Comment</span><span>↪ Share</span></div>
	</div>
{/snippet}

{#snippet igMock(a: Ad)}
	<div class="ig">
		<div class="ig-h">
			<span class="av sm">{@render mark()}</span>
			<div class="ig-nm">superextra <span class="sub">· Sponsored</span></div>
			<div class="dots">⋯</div>
		</div>
		{@render card(a)}
		<div class="ig-cta"><span>{a.cta}</span><span class="chev">›</span></div>
		<div class="ig-act"><span>♥&nbsp;&nbsp;💬&nbsp;&nbsp;➤</span><span>🔖</span></div>
		<div class="ig-cap"><b>superextra</b> {a.primary}</div>
	</div>
{/snippet}

<BrandGate>
	<!-- eslint-disable-next-line svelte/no-at-html-tags -- internal: static glyph <defs>, no user input -->
	{@html glyphDefs()}
	<div class="studio">
		<aside class="side">
			<div class="brand"><b>Superextra</b> · Ad studio</div>
			<label class="fld">
				<span>Campaign</span>
				<select bind:value={ci} onchange={() => (selected = 0)}>
					{#each store as c, i (i)}<option value={i}>{c.name}</option>{/each}
				</select>
			</label>
			<label class="fld">
				<span>Name</span>
				<input bind:value={store[ci].name} />
			</label>
			<div class="addrow">
				<button onclick={addAd}>+ Add</button>
				<button onclick={duplicateAd}>Duplicate</button>
			</div>
			<div class="spacer"></div>
			<div class="sidefoot">
				<button class="primary" onclick={exportJson}>{copied ? 'Copied ✓' : 'Export JSON'}</button>
				<button class="ghost" onclick={resetToFile}>Reset to file</button>
			</div>
		</aside>

		<main class="main">
			<div class="adtabs">
				{#each data.ads as a, i (a.id + i)}
					<button class="adtab" class:on={i === si} onclick={() => (selected = i)}>
						<b>{a.id}</b><span>{a.note}</span>
						{#if data.ads.length > 1}
							<span
								class="rm"
								role="button"
								tabindex="0"
								onclick={(e) => {
									e.stopPropagation();
									removeAd(i);
								}}
								onkeydown={() => {}}>×</span
							>
						{/if}
					</button>
				{/each}
			</div>
			<div class="toolbar">
				<div class="seg">
					{#each BGS as b (b.key)}
						<button class:on={ad.bg === b.key} onclick={() => (store[ci].ads[si].bg = b.key)}>
							{b.label}
						</button>
					{/each}
				</div>
				{#if ad.bg === 'color'}
					<select bind:value={store[ci].ads[si].colorTheme}>
						{#each COLOR_THEMES as t (t.key)}<option value={t.key}>{t.label}</option>{/each}
					</select>
				{/if}
				<select bind:value={store[ci].ads[si].cta}>
					{#each CTAS as c (c)}<option value={c}>{c}</option>{/each}
				</select>
				<label class="chk">
					<input type="checkbox" bind:checked={store[ci].ads[si].taglineOnCard} /> tagline
				</label>
				<button class="dl" onclick={() => exportPng($state.snapshot(ad) as Ad)}>Download PNG</button
				>
			</div>

			<div class="grid">
				<div class="editor">
					<label class="fld"
						><span>Headline (image)</span>
						<textarea
							rows="3"
							value={ad.hero.replace(/<br\s*\/?>/gi, '\n')}
							oninput={(e) => setHero(e.currentTarget.value)}
						></textarea>
					</label>
					<label class="fld"
						><span>Primary text {ad.headline === '' ? '(post caption)' : ''}</span>
						<textarea rows="8" bind:value={store[ci].ads[si].primary}></textarea>
					</label>
					<label class="fld"
						><span>Meta headline</span>
						<input bind:value={store[ci].ads[si].headline} />
					</label>
					<label class="fld"
						><span>Note (internal)</span>
						<input bind:value={store[ci].ads[si].note} />
					</label>
				</div>
				<div class="preview">
					<div class="plat">Facebook</div>
					{@render fbMock(ad)}
					<div class="plat" style="margin-top:18px">Instagram</div>
					{@render igMock(ad)}
				</div>
			</div>

			{#if showJson}
				<div class="jsonpanel">
					<div class="jh">
						<span
							>Campaigns JSON — paste into the <code>campaigns</code> array in
							<code>src/lib/brand/ads-data.ts</code></span
						>
						<button onclick={() => (showJson = false)}>Close</button>
					</div>
					<textarea readonly rows="12">{JSON.stringify(store, null, 2)}</textarea>
				</div>
			{/if}
		</main>
	</div>
</BrandGate>

<style>
	.studio {
		display: flex;
		min-height: 100vh;
		background: #1a1714;
		color: #ede9e3;
		font-family:
			'Inter',
			-apple-system,
			system-ui,
			sans-serif;
	}
	.side {
		width: 248px;
		flex: none;
		display: flex;
		flex-direction: column;
		gap: 14px;
		padding: 22px 18px;
		background: #171411;
		border-right: 1px solid #2e2a25;
	}
	.brand {
		font-size: 13px;
		color: #9b958c;
	}
	.brand b {
		color: #ede9e3;
		font-weight: 600;
	}
	.fld {
		display: flex;
		flex-direction: column;
		gap: 5px;
		font-size: 11px;
		color: #9b958c;
	}
	.fld span {
		letter-spacing: 0.03em;
		text-transform: uppercase;
	}
	input,
	textarea,
	select {
		background: #211e1a;
		border: 1px solid #2e2a25;
		border-radius: 7px;
		color: #ede9e3;
		font: inherit;
		font-size: 13px;
		padding: 8px 10px;
		outline: none;
	}
	input:focus,
	textarea:focus,
	select:focus {
		border-color: #5b5650;
	}
	textarea {
		resize: vertical;
		line-height: 1.4;
	}
	.adtabs {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		margin-bottom: 16px;
	}
	.adtab {
		display: inline-flex;
		align-items: center;
		gap: 7px;
		text-align: left;
		background: #211e1a;
		border: 1px solid #2e2a25;
		border-radius: 8px;
		padding: 7px 12px;
		color: #9b958c;
		cursor: pointer;
		font: inherit;
		font-size: 12.5px;
	}
	.adtab:hover {
		border-color: #5b5650;
		color: #ede9e3;
	}
	.adtab.on {
		background: #ede9e3;
		border-color: #ede9e3;
		color: #1a1714;
	}
	.adtab b {
		color: #c7c1b8;
	}
	.adtab.on b {
		color: #1a1714;
	}
	.adtab .rm {
		color: #6f6a62;
		font-size: 15px;
		padding: 0 1px;
	}
	.adtab .rm:hover {
		color: #e0907f;
	}
	.addrow {
		display: flex;
		gap: 8px;
	}
	.addrow button,
	.sidefoot button,
	.toolbar .dl {
		background: #211e1a;
		border: 1px solid #2e2a25;
		border-radius: 7px;
		color: #c7c1b8;
		padding: 8px 12px;
		font: inherit;
		font-size: 12.5px;
		cursor: pointer;
	}
	.addrow button:hover,
	.sidefoot button:hover {
		border-color: #5b5650;
		color: #ede9e3;
	}
	.spacer {
		flex: 1;
	}
	.sidefoot {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.sidefoot .primary {
		background: #ede9e3;
		color: #1a1714;
		font-weight: 600;
		border-color: #ede9e3;
	}
	.main {
		flex: 1;
		min-width: 0;
		padding: 22px 28px 80px;
	}
	.toolbar {
		display: flex;
		align-items: center;
		gap: 12px;
		flex-wrap: wrap;
		margin-bottom: 22px;
	}
	.seg {
		display: inline-flex;
		border: 1px solid #2e2a25;
		border-radius: 8px;
		overflow: hidden;
	}
	.seg button {
		background: #211e1a;
		border: 0;
		color: #9b958c;
		padding: 8px 14px;
		font: inherit;
		font-size: 12.5px;
		cursor: pointer;
	}
	.seg button.on {
		background: #ede9e3;
		color: #1a1714;
		font-weight: 600;
	}
	.toolbar .dl {
		margin-left: auto;
	}
	.chk {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: 12.5px;
		color: #9b958c;
	}
	.chk input {
		padding: 0;
	}
	.grid {
		display: grid;
		grid-template-columns: minmax(300px, 1fr) auto;
		gap: 34px;
		align-items: start;
	}
	.editor {
		display: flex;
		flex-direction: column;
		gap: 16px;
		max-width: 440px;
	}
	.editor .fld span {
		color: #c7c1b8;
	}
	.preview {
		flex: none;
	}
	.plat {
		font-size: 11px;
		color: #6f6a62;
		margin-bottom: 8px;
		letter-spacing: 0.04em;
	}

	.jsonpanel {
		margin-top: 28px;
		border: 1px solid #2e2a25;
		border-radius: 10px;
		overflow: hidden;
	}
	.jh {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 10px 14px;
		background: #211e1a;
		font-size: 12px;
		color: #9b958c;
	}
	.jh code {
		color: #ede9e3;
		font-family: ui-monospace, Menlo, monospace;
	}
	.jh button {
		background: transparent;
		border: 1px solid #3d3832;
		border-radius: 6px;
		color: #c7c1b8;
		padding: 4px 10px;
		cursor: pointer;
		font: inherit;
		font-size: 12px;
	}
	.jsonpanel textarea {
		width: 100%;
		border: 0;
		border-radius: 0;
		font-family: ui-monospace, Menlo, monospace;
		font-size: 12px;
	}

	/* Creative square — cqw resolves against this container. */
	.sq {
		width: 100%;
		aspect-ratio: 1 / 1;
		container-type: inline-size;
		position: relative;
		overflow: hidden;
	}
	.bgc {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		display: block;
	}
	.av {
		flex: none;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 40px;
		height: 40px;
		border-radius: 50%;
		background: #fefdf9;
		border: 1px solid #e6e2da;
	}
	.av.sm {
		width: 30px;
		height: 30px;
	}
	.dots {
		margin-left: auto;
		color: #65676b;
		font-size: 18px;
		align-self: flex-start;
	}

	/* Facebook */
	.fb {
		width: 400px;
		background: #fff;
		border-radius: 10px;
		color: #050505;
		overflow: hidden;
	}
	.fb-h {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 12px 12px 8px;
	}
	.fb-meta .nm {
		font-size: 14px;
		font-weight: 600;
	}
	.fb-meta .sub {
		font-size: 12px;
		color: #65676b;
	}
	.fb-txt {
		font-size: 14px;
		line-height: 1.4;
		padding: 0 12px 10px;
	}
	.fb-bar {
		display: flex;
		align-items: center;
		gap: 12px;
		background: #f0f2f5;
		padding: 10px 12px;
	}
	.fb-bar-txt {
		min-width: 0;
		flex: 1;
	}
	.fb-bar-txt .dom {
		font-size: 11px;
		letter-spacing: 0.03em;
		color: #65676b;
		text-transform: uppercase;
	}
	.fb-bar-txt .hl {
		font-size: 15px;
		font-weight: 600;
		margin-top: 2px;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.cta {
		flex: none;
		border: 0;
		background: #e4e6eb;
		color: #050505;
		font-weight: 600;
		font-size: 13px;
		padding: 9px 14px;
		border-radius: 6px;
	}
	.fb-act {
		display: flex;
		justify-content: space-around;
		padding: 8px 4px;
		border-top: 1px solid #e6e7eb;
		color: #65676b;
		font-size: 13px;
		font-weight: 600;
	}

	/* Instagram */
	.ig {
		width: 360px;
		background: #fff;
		border: 1px solid #dbdbdb;
		border-radius: 8px;
		color: #262626;
		overflow: hidden;
	}
	.ig-h {
		display: flex;
		align-items: center;
		gap: 9px;
		padding: 10px 12px;
	}
	.ig-nm {
		font-size: 13px;
		font-weight: 600;
	}
	.ig-nm .sub {
		font-weight: 400;
		color: #737373;
	}
	.ig-cta {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 11px 14px;
		font-size: 14px;
		font-weight: 600;
		color: #00376b;
		background: #fafafa;
		border-top: 1px solid #efefef;
		border-bottom: 1px solid #efefef;
	}
	.ig-cta .chev {
		color: #8e8e8e;
		font-size: 18px;
	}
	.ig-act {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 10px 14px 4px;
		font-size: 20px;
	}
	.ig-cap {
		font-size: 13px;
		line-height: 1.4;
		padding: 4px 14px 14px;
	}
	.ig-cap b {
		font-weight: 600;
	}
</style>
