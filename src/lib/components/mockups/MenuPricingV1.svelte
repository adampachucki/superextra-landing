<script lang="ts">
	const months = ['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar'];
	const youPrices = [26, 27, 27, 28, 29, 28];
	const marketPrices = [30, 31, 32, 33, 32, 32];

	const viewW = 200;
	const viewH = 55;
	const padX = 8;
	const padY = 6;
	const padBottom = 10;
	const plotW = viewW - padX * 2;
	const plotH = viewH - padY - padBottom;

	const allValues = [...youPrices, ...marketPrices];
	const minVal = Math.min(...allValues) - 2;
	const maxVal = Math.max(...allValues) + 2;
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

	const youPoints = toPoints(youPrices);
	const marketPoints = toPoints(marketPrices);

	const gridLines = [0.25, 0.5, 0.75].map((pct) => ({
		y: padY + pct * plotH
	}));

	const monthLabels = months.map((m, i) => ({
		label: m,
		x: padX + (i / (months.length - 1)) * plotW
	}));

	const youAvg = Math.round(youPrices.reduce((a, b) => a + b, 0) / youPrices.length);
	const marketAvg = Math.round(marketPrices.reduce((a, b) => a + b, 0) / marketPrices.length);
</script>

<!-- 1. Top bar -->
<div class="top-bar">
	<div class="bar-icon">
		<span></span><span></span>
	</div>
	<span class="bar-label">Price Trends</span>
	<div class="legend-row">
		<span class="legend-item"><span class="legend-line you"></span>You</span>
		<span class="legend-item"><span class="legend-line market"></span>Market</span>
	</div>
</div>

<div class="body">
	<!-- 2. Chart SVG -->
	<svg class="chart" viewBox="0 0 {viewW} {viewH}">
		{#each gridLines as line}
			<line
				x1={padX}
				y1={line.y}
				x2={viewW - padX}
				y2={line.y}
				stroke="rgba(0,0,0,0.06)"
				stroke-width="0.5"
				stroke-dasharray="3,3"
			/>
		{/each}

		<polyline
			points={marketPoints}
			fill="none"
			stroke="rgba(0,0,0,0.15)"
			stroke-width="1.5"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>

		<polyline
			points={youPoints}
			fill="none"
			stroke="#6366f1"
			stroke-width="1.5"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>

		{#each monthLabels as m}
			<text
				x={m.x}
				y={viewH - 2}
				text-anchor="middle"
				class="month-label"
			>{m.label}</text>
		{/each}
	</svg>

	<!-- 3. Stats row -->
	<div class="stats-row">
		<div class="stat">
			<span class="stat-label">Your avg</span>
			<span class="stat-value you">${youAvg}</span>
		</div>
		<div class="stat">
			<span class="stat-label">Market avg</span>
			<span class="stat-value">${marketAvg}</span>
		</div>
	</div>
</div>

<!-- 4. Border + 5. Filters row -->
<div class="filters-section">
	<div class="filters-row">
		<span class="dropdown-pill">Mains <span class="chevron">&#9662;</span></span>
		<div class="pill-group">
			<span class="pill active">Dine-in</span>
			<span class="pill">Delivery</span>
		</div>
	</div>
</div>

<style>
	/* ── Top bar ── */
	.top-bar {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.75rem 1.25rem;
		border-bottom: 1px solid rgba(0, 0, 0, 0.04);
	}

	.bar-icon {
		display: flex;
		gap: 2px;
	}
	.bar-icon span {
		display: block;
		width: 2.5px;
		height: 12px;
		background: rgba(0, 0, 0, 0.25);
		border-radius: 1px;
	}

	.bar-label {
		font-size: 0.8125rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.6);
	}

	/* ── Legend (in top bar) ── */
	.legend-row {
		margin-left: auto;
		display: flex;
		gap: 0.75rem;
	}

	.legend-item {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.5625rem;
		color: rgba(0, 0, 0, 0.3);
	}

	.legend-line {
		width: 10px;
		height: 2px;
		border-radius: 1px;
		flex-shrink: 0;
	}

	.legend-line.you {
		background: #6366f1;
	}

	.legend-line.market {
		background: rgba(0, 0, 0, 0.15);
	}

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

	.chart .month-label {
		font-size: 3.5px;
		fill: rgba(0, 0, 0, 0.25);
		font-weight: 400;
	}

	/* ── Stats row (below chart) ── */
	.stats-row {
		display: flex;
		gap: 1rem;
		margin-top: 0.625rem;
	}

	.stat {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.stat-label {
		font-size: 0.5625rem;
		color: rgba(0, 0, 0, 0.25);
		font-weight: 400;
	}

	.stat-value {
		font-size: 0.8125rem;
		font-weight: 600;
		color: rgba(0, 0, 0, 0.5);
	}

	.stat-value.you {
		color: #6366f1;
	}

	/* ── Filters section (bottom, separated by border) ── */
	.filters-section {
		border-top: 1px solid rgba(0, 0, 0, 0.06);
		padding: 0.625rem 1.25rem;
	}

	.filters-row {
		display: flex;
		align-items: center;
		gap: 0.625rem;
	}

	/* Dropdown pill — bigger */
	.dropdown-pill {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.5);
		border: 1px solid rgba(0, 0, 0, 0.1);
		background: transparent;
		padding: 0.3rem 0.75rem;
		border-radius: 9999px;
		cursor: pointer;
		white-space: nowrap;
	}

	.chevron {
		font-size: 0.625rem;
		line-height: 1;
		color: rgba(0, 0, 0, 0.3);
	}

	/* Segmented toggle — bigger */
	.pill-group {
		display: flex;
		gap: 1px;
		background: rgba(0, 0, 0, 0.05);
		border-radius: 9999px;
		padding: 2px;
		margin-left: auto;
	}

	.pill {
		font-size: 0.75rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.3);
		padding: 0.25rem 0.625rem;
		border-radius: 9999px;
		cursor: pointer;
		white-space: nowrap;
	}

	.pill.active {
		background: white;
		color: rgba(0, 0, 0, 0.6);
		box-shadow: 0 0.5px 1.5px rgba(0, 0, 0, 0.08);
	}
</style>
