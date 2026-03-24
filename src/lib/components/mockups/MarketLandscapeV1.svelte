<script lang="ts">
	import MockupBar from './MockupBar.svelte';
	const openings = [8, 12, 10, 14, 13, 14];
	const closings = [10, 8, 12, 9, 8, 7];

	const viewW = 200;
	const viewH = 45;
	const padX = 8;
	const padY = 4;
	const plotW = viewW - padX * 2;
	const plotH = viewH - padY * 2;

	const allValues = [...openings, ...closings];
	const minVal = Math.min(...allValues);
	const maxVal = Math.max(...allValues);
	const range = maxVal - minVal || 1;

	function toPoints(data: number[]): string {
		return data
			.map((v, i) => {
				const x = padX + (i / (data.length - 1)) * plotW;
				const y = padY + (1 - (v - minVal) / range) * plotH;
				return `${x},${y}`;
			})
			.join(' ');
	}

	const openingsPoints = toPoints(openings);
	const closingsPoints = toPoints(closings);

	const gridLines = [0.25, 0.5, 0.75].map((pct) => {
		const y = padY + pct * plotH;
		const value = Math.round(maxVal - pct * range);
		return { y, value };
	});

	const categories = [
		{ name: 'Vegan', openings: 6, closings: 1, grad: 'from-[#6ee7b7] to-[#06b6d4]' },
		{ name: 'Italian', openings: 4, closings: 3, grad: 'from-[#fbbf24] to-[#f472b6]' },
		{ name: 'Asian Fusion', openings: 5, closings: 2, grad: 'from-[#06b6d4] to-[#6366f1]' },
		{ name: 'American', openings: 2, closings: 4, grad: 'from-[#f472b6] to-[#a78bfa]' }
	];
</script>

<MockupBar label="Market Activity" icon="barchart">
	<div class="header-legend">
		<span class="legend-item"><span class="legend-dot" style="background:#6366f1"></span>Open</span>
		<span class="legend-item"><span class="legend-dot" style="background:rgba(var(--mockup-text),0.15)"></span>Close</span>
	</div>
</MockupBar>

<div class="body">
	<svg class="chart" viewBox="0 0 {viewW} {viewH}" preserveAspectRatio="none">
		{#each gridLines as line}
			<line x1={padX} y1={line.y} x2={viewW - padX} y2={line.y} style="stroke: rgba(var(--mockup-text), 0.06)" stroke-width="0.5" stroke-dasharray="3,3" />
		{/each}
		<polyline
			points={openingsPoints}
			fill="none"
			stroke="#6366f1"
			stroke-width="1.5"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<polyline
			points={closingsPoints}
			fill="none"
			style="stroke: rgba(var(--mockup-text), 0.15)"
			stroke-width="1.5"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	</svg>

	<div class="category-section">
		{#each categories as c}
			<div class="category-row">
				<div class="category-dot bg-gradient-to-br {c.grad}"></div>
				<span class="category-name">{c.name}</span>
				<span class="category-pair">
					<span class="pair-open">+{c.openings}</span>
					<span class="pair-slash">/</span>
					<span class="pair-close">&minus;{c.closings}</span>
				</span>
			</div>
		{/each}
	</div>

</div>

<style>
	/* ── Body ── */
	.body {
		padding: 0.75rem 1.25rem;
	}

	/* ── Line chart ── */
	.chart {
		width: 100%;
		height: auto;
		display: block;
	}

	.header-legend {
		margin-left: auto;
		display: flex;
		gap: 0.5rem;
	}

	.legend-item {
		display: flex;
		align-items: center;
		gap: 0.2rem;
		font-size: 0.5625rem;
		color: rgba(var(--mockup-text), 0.3);
	}

	.legend-dot {
		width: 5px;
		height: 5px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	/* ── Category rows ── */
	.category-section {
		border-top: 1px solid rgba(var(--mockup-text), 0.04);
		margin-top: 0.625rem;
		padding-top: 0.625rem;
	}

	.category-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.375rem 0;
	}

	.category-dot {
		width: 1.75rem;
		height: 1.75rem;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.category-name {
		flex: 1;
		font-size: 0.8125rem;
		font-weight: 500;
		color: rgba(var(--mockup-text), 0.75);
	}

	.category-pair {
		font-size: 0.6875rem;
		display: flex;
		align-items: center;
		gap: 0.2rem;
	}

	.pair-open {
		color: #6366f1;
		font-weight: 600;
	}

	.pair-slash {
		color: rgba(var(--mockup-text), 0.12);
	}

	.pair-close {
		color: rgba(var(--mockup-text), 0.2);
	}

</style>
