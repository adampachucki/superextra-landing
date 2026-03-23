<script lang="ts">
	const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
	const values = [90, 105, 130, 115, 150, 170, 160, 185, 155, 200, 215, 230];

	const viewW = 220;
	const viewH = 90;
	const padL = 22;
	const padR = -20;
	const padT = 6;
	const padB = 16;
	const plotW = viewW - padL - padR;
	const plotH = viewH - padT - padB;

	const minVal = 0;
	const maxVal = 300;
	const range = maxVal - minVal;

	function toX(i: number): number {
		return padL + (i / (values.length - 1)) * plotW;
	}

	function toY(v: number): number {
		return padT + (1 - (v - minVal) / range) * plotH;
	}

	const linePoints = values.map((v, i) => `${toX(i)},${toY(v)}`).join(' ');

	// Area fill: line points + bottom-right + bottom-left to close the shape
	const lastX = toX(values.length - 1);
	const firstX = toX(0);
	const bottomY = padT + plotH;
	const areaPoints = `${linePoints} ${lastX},${bottomY} ${firstX},${bottomY}`;

	// Y-axis grid lines
	const yTicks = [0, 100, 200, 300];
	const gridLines = yTicks.map((v) => ({
		y: toY(v),
		label: v === 0 ? '$0' : `$${v}K`
	}));

	// X-axis labels (show every other month)
	const xLabels = months
		.map((m, i) => ({ label: m, x: toX(i) }))
		.filter((_, i) => i % 2 === 0);

	// Highlighted data point (Jun)
	const dotIndex = 5;
	const dotPointX = toX(dotIndex);
	const dotPointY = toY(values[dotIndex]);
</script>

<div class="top-bar">
	<div class="bar-icon">
		<span></span><span></span>
	</div>
	<span class="bar-label">Financial Overview</span>
	<div class="year-pills">
		<span class="year-pill">2023</span>
		<span class="year-pill">2024</span>
		<span class="year-pill active">2025</span>
	</div>
</div>

<div class="body">
	<div class="hero">
		<span class="hero-value">$2.1M</span>
		<span class="hero-growth">+12.4%</span>
	</div>
	<div class="hero-subtitle">Annual Revenue · Benchmarked Cohort</div>

	<svg class="chart" viewBox="0 0 {viewW} {viewH}" preserveAspectRatio="xMidYMid meet">
		<defs>
			<linearGradient id="revAreaGrad" x1="0" y1="0" x2="0" y2="1">
				<stop offset="0%" stop-color="#6366f1" stop-opacity="0.2" />
				<stop offset="100%" stop-color="#6366f1" stop-opacity="0" />
			</linearGradient>
		</defs>

		{#each gridLines as line}
			<line
				x1={padL}
				y1={line.y}
				x2={viewW - padR}
				y2={line.y}
				stroke="rgba(0,0,0,0.06)"
				stroke-width="0.4"
				stroke-dasharray="2,2"
			/>
			<text
				x={padL - 3}
				y={line.y + 1.5}
				text-anchor="end"
				class="axis-label"
			>{line.label}</text>
		{/each}

		<polygon points={areaPoints} fill="url(#revAreaGrad)" />

		<polyline
			points={linePoints}
			fill="none"
			stroke="#6366f1"
			stroke-width="1.5"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>

		<circle cx={dotPointX} cy={dotPointY} r="2.5" fill="#6366f1" />
		<circle cx={dotPointX} cy={dotPointY} r="4.5" fill="none" stroke="#6366f1" stroke-opacity="0.25" stroke-width="1" />

		{#each xLabels as tick}
			<text
				x={tick.x}
				y={viewH - 2}
				text-anchor="middle"
				class="axis-label"
			>{tick.label}</text>
		{/each}
	</svg>

	<div class="metric-tabs">
		<span class="metric-tab active">Revenue</span>
		<span class="metric-tab">Costs</span>
		<span class="metric-tab">Margins</span>
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

	.year-pills {
		display: flex;
		gap: 0;
		background: rgba(0, 0, 0, 0.04);
		border-radius: 0.25rem;
		overflow: hidden;
		margin-left: auto;
	}

	.year-pill {
		font-size: 0.5625rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.3);
		padding: 0.2rem 0.4rem;
		cursor: default;
	}

	.year-pill.active {
		background: rgba(0, 0, 0, 0.06);
		color: rgba(0, 0, 0, 0.5);
		border-radius: 0.25rem;
	}

	/* ── Body ── */
	.body {
		padding: 0.875rem 1.25rem 0.75rem;
	}

	/* ── Hero metric ── */
	.hero {
		display: flex;
		align-items: baseline;
		gap: 0.5rem;
	}

	.hero-value {
		font-size: 1.75rem;
		font-weight: 700;
		color: rgba(0, 0, 0, 0.88);
		line-height: 1.1;
		letter-spacing: -0.02em;
	}

	.hero-growth {
		font-size: 0.8125rem;
		font-weight: 600;
		color: #0d9488;
		line-height: 1;
	}

	.hero-subtitle {
		font-size: 0.6875rem;
		color: rgba(0, 0, 0, 0.35);
		margin-top: 0.2rem;
		margin-bottom: 0.75rem;
	}

	/* ── Chart ── */
	.chart {
		width: calc(100% + 3rem);
		height: auto;
		display: block;
		margin-bottom: 0.625rem;
	}

	.chart :global(.axis-label),
	.axis-label {
		font-size: 5px;
		fill: rgba(0, 0, 0, 0.35);
		font-weight: 400;
	}

	/* ── Metric tabs ── */
	.metric-tabs {
		display: flex;
		gap: 0;
		border-top: 1px solid rgba(0, 0, 0, 0.04);
		padding-top: 0.625rem;
	}

	.metric-tab {
		flex: 1;
		text-align: center;
		font-size: 0.6875rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.3);
		padding: 0.375rem 0;
		border-radius: 0.375rem;
		cursor: default;
	}

	.metric-tab.active {
		background: rgba(0, 0, 0, 0.05);
		color: rgba(0, 0, 0, 0.6);
	}
</style>
