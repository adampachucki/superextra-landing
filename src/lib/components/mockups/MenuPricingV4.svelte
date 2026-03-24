<script lang="ts">
	import MockupBar from './MockupBar.svelte';
	const viewW = 220;
	const viewH = 136;
	const padLeft = 26;
	const padRight = 10;
	const padTop = 10;
	const padBottom = 22;
	const plotW = viewW - padLeft - padRight;
	const plotH = viewH - padTop - padBottom;

	const bars = [
		{ label: "Q1'25", value: 11.5, featured: false },
		{ label: "Q2'25", value: 12.8, featured: false },
		{ label: "Q3'25", value: 14.2, featured: false },
		{ label: "Q4'25", value: 15.9, featured: false },
		{ label: "Q1'26", value: 17.4, featured: true }
	];

	const yMin = 10;
	const yMax = 18;
	const yRange = yMax - yMin;
	const yTicks = [10, 12, 14, 16, 18];

	const barCount = bars.length;
	const barGap = plotW / barCount;
	const barWidth = barGap * 0.54;

	function barHeight(value: number): number {
		return ((value - yMin) / yRange) * plotH;
	}

	function barX(index: number): number {
		return padLeft + barGap * index + (barGap - barWidth) / 2;
	}

	function barY(value: number): number {
		return padTop + plotH - barHeight(value);
	}

	function yTickY(tick: number): number {
		return padTop + plotH - ((tick - yMin) / yRange) * plotH;
	}
</script>

<MockupBar label="Price Index" icon="list" />

<div class="body">
	<svg class="chart" viewBox="0 0 {viewW} {viewH}">
		<defs>
			<linearGradient id="burgerFeaturedGrad" x1="0" y1="0" x2="0" y2="1">
				<stop offset="0%" stop-color="#1a1a2e" />
				<stop offset="100%" stop-color="#0d9488" />
			</linearGradient>
		</defs>

		<!-- Y-axis labels -->
		{#each yTicks as tick}
			<text
				x={padLeft - 5}
				y={yTickY(tick) + 2}
				text-anchor="end"
				class="y-label"
			>€{tick}</text>
		{/each}

		<!-- Horizontal dotted grid lines -->
		{#each yTicks as tick}
			<line
				x1={padLeft}
				y1={yTickY(tick)}
				x2={viewW - padRight}
				y2={yTickY(tick)}
				stroke="rgba(0,0,0,0.15)"
				stroke-width="0.5"
				stroke-dasharray="2,2.5"
			/>
		{/each}

		<!-- Bars (rendered on top of grid lines) -->
		{#each bars as bar, i}
			<rect
				x={barX(i)}
				y={barY(bar.value)}
				width={barWidth}
				height={barHeight(bar.value)}
				rx="1.5"
				ry="1.5"
				fill={bar.featured ? 'url(#burgerFeaturedGrad)' : '#e5e5e5'}
			/>

			<!-- Price label above the featured bar -->
			{#if bar.featured}
				<text
					x={barX(i) + barWidth / 2}
					y={barY(bar.value) - 4}
					text-anchor="middle"
					class="bar-value featured-value"
				>€{bar.value.toFixed(2).replace('.', ',')}</text>
			{/if}

			<!-- Quarter label below -->
			<text
				x={barX(i) + barWidth / 2}
				y={padTop + plotH + 14}
				text-anchor="middle"
				class="bar-name"
				class:bar-name-featured={bar.featured}
			>{bar.label}</text>
		{/each}
	</svg>

	<!-- Filters -->
	<div class="filters">
		<div class="filters-row">
			<button class="filter-pill" type="button">
				Burgers
				<svg class="chevron" viewBox="0 0 12 12" fill="none">
					<path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" />
				</svg>
			</button>
			<button class="filter-pill" type="button">
				Dine-in
				<svg class="chevron" viewBox="0 0 12 12" fill="none">
					<path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" />
				</svg>
			</button>
			<button class="filter-pill" type="button">
				<svg class="cal-icon" viewBox="0 0 12 12" fill="none">
					<rect x="1.5" y="2.5" width="9" height="8" rx="1" stroke="currentColor" stroke-width="0.9" />
					<line x1="1.5" y1="5" x2="10.5" y2="5" stroke="currentColor" stroke-width="0.9" />
					<line x1="4" y1="1.5" x2="4" y2="3.5" stroke="currentColor" stroke-width="0.9" stroke-linecap="round" />
					<line x1="8" y1="1.5" x2="8" y2="3.5" stroke="currentColor" stroke-width="0.9" stroke-linecap="round" />
				</svg>
				Q1'25 – Now
			</button>
		</div>
	</div>
</div>

<style>
	/* ── Body ── */
	.body {
		padding: 1rem 1.25rem 0.75rem;
	}

	/* ── Chart ── */
	.chart {
		width: 100%;
		height: auto;
		display: block;
	}

	.chart .y-label {
		font-size: 6px;
		fill: rgba(0, 0, 0, 0.5);
		font-weight: 400;
	}

	.chart .bar-value {
		font-size: 6.5px;
		fill: rgba(0, 0, 0, 0.65);
		font-weight: 600;
	}

	.chart .featured-value {
		fill: #1a1a2e;
	}

	.chart .bar-name {
		font-size: 5.5px;
		fill: rgba(0, 0, 0, 0.5);
		font-weight: 400;
	}

	.chart .bar-name-featured {
		fill: rgba(0, 0, 0, 0.85);
		font-weight: 600;
	}

	/* ── Filters ── */
	.filters {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		padding-top: 0.625rem;
		margin-top: 0.625rem;
		border-top: 1px solid rgba(0, 0, 0, 0.06);
	}

	.filters-row {
		display: flex;
		gap: 0.5rem;
	}

	.filter-pill {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		font-size: 0.6875rem;
		font-weight: 450;
		color: rgba(0, 0, 0, 0.5);
		background: rgba(0, 0, 0, 0.03);
		border: 1px solid rgba(0, 0, 0, 0.07);
		border-radius: 9999px;
		padding: 0.25rem 0.625rem;
		cursor: default;
		line-height: 1.3;
		white-space: nowrap;
	}

	.chevron {
		width: 0.625rem;
		height: 0.625rem;
		flex-shrink: 0;
	}

	.cal-icon {
		width: 0.6875rem;
		height: 0.6875rem;
		flex-shrink: 0;
	}
</style>
