<script lang="ts">
	import MockupBar from './MockupBar.svelte';
	const segments = [
		{ name: 'Local Critics', value: 4860, color: '#6366f1' },
		{ name: 'Local Visitors', value: 3120, color: '#f472b6' },
		{ name: 'Intl Tourists', value: 1490, color: '#06b6d4' }
	];

	const total = segments.reduce((sum, s) => sum + s.value, 0);
	const cx = 65;
	const cy = 52;
	const r = 34;
	const strokeW = 12;

	function polarToCartesian(centerX: number, centerY: number, radius: number, angleDeg: number) {
		const rad = ((angleDeg - 90) * Math.PI) / 180;
		return { x: centerX + radius * Math.cos(rad), y: centerY + radius * Math.sin(rad) };
	}

	function arcPath(startAngle: number, endAngle: number): string {
		const start = polarToCartesian(cx, cy, r, endAngle);
		const end = polarToCartesian(cx, cy, r, startAngle);
		const large = endAngle - startAngle > 180 ? 1 : 0;
		return `M ${start.x} ${start.y} A ${r} ${r} 0 ${large} 0 ${end.x} ${end.y}`;
	}

	let cumAngle = 0;
	const arcs = segments.map((s) => {
		const angle = (s.value / total) * 360;
		const startAngle = cumAngle;
		cumAngle += angle;
		const gap = 3;
		return {
			...s,
			path: arcPath(startAngle + gap / 2, startAngle + angle - gap / 2),
			pct: Math.round((s.value / total) * 100)
		};
	});
</script>

<MockupBar label="Reviewer Profile" icon="barchart" compact>
	<div class="range-pills">
		<span class="range-pill">7d</span>
		<span class="range-pill active">14d</span>
		<span class="range-pill">30d</span>
	</div>
</MockupBar>

<div class="summary">
	{#each segments as seg}
		<div class="stat">
			<span class="stat-dot" style="background: {seg.color}"></span>
			<div class="stat-text">
				<span class="stat-label">{seg.name}</span>
				<span class="stat-value">{seg.value.toLocaleString('de-DE')}</span>
			</div>
		</div>
	{/each}
</div>

<div class="chart-area">
	<svg viewBox="0 0 200 108" fill="none">
		{#each arcs as arc}
			<path
				d={arc.path}
				stroke={arc.color}
				stroke-width={strokeW}
				stroke-linecap="round"
				fill="none"
				opacity="0.8"
			/>
		{/each}

		<text x={cx} y={cy - 4} text-anchor="middle" class="center-value">{total.toLocaleString('de-DE')}</text>
		<text x={cx} y={cy + 6} text-anchor="middle" class="center-label">reviewers</text>

		<defs>
			<linearGradient id="guestTextFadeGrad" x1="0" y1="0" x2="0" y2="1">
				<stop offset="0%" stop-color="#1a1a1a" />
				<stop offset="60%" stop-color="#555555" />
				<stop offset="100%" stop-color="#555555" stop-opacity="0" />
			</linearGradient>
		</defs>

		<text x="128" y="18" class="overflow-text" fill="url(#guestTextFadeGrad)">
			<tspan x="128" dy="0">Local critics average 4,1</tspan>
			<tspan x="128" dy="9">stars and review 3,8 spots</tspan>
			<tspan x="128" dy="9">per quarter. Local visitors</tspan>
			<tspan x="128" dy="9">skew higher at 4,4 stars</tspan>
			<tspan x="128" dy="9">but focus almost exclusively</tspan>
			<tspan x="128" dy="9">on weekend dining. Intl</tspan>
			<tspan x="128" dy="9">tourists leave the most</tspan>
			<tspan x="128" dy="9">polarized ratings, clustering</tspan>
			<tspan x="128" dy="9">at 5 and 2 stars.</tspan>
		</text>
	</svg>
</div>

<div class="footer">
	<span class="footer-total">Reviewers: {total.toLocaleString('de-DE')}</span>
	<span class="footer-change">+8% vs 2024</span>
</div>

<style>
	/* ── Range pills ── */
	.range-pills {
		display: flex;
		gap: 0;
		background: rgba(0, 0, 0, 0.04);
		border-radius: 0.25rem;
		overflow: hidden;
		margin-left: auto;
	}

	.range-pill {
		font-size: 0.5625rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.3);
		padding: 0.2rem 0.4rem;
		cursor: default;
	}

	.range-pill.active {
		background: rgba(0, 0, 0, 0.06);
		color: rgba(0, 0, 0, 0.5);
		border-radius: 0.25rem;
	}

	/* ── Segment summary ── */
	.summary {
		display: flex;
		gap: 0.75rem;
		padding: 0.625rem 0.875rem;
		border-bottom: 1px solid rgba(0, 0, 0, 0.04);
	}

	.stat {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		flex: 1;
	}

	.stat-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.stat-text {
		display: flex;
		flex-direction: column;
	}

	.stat-label {
		font-size: 0.5625rem;
		color: rgba(0, 0, 0, 0.35);
		font-weight: 500;
		line-height: 1.2;
	}

	.stat-value {
		font-size: 0.8125rem;
		font-weight: 600;
		color: rgba(0, 0, 0, 0.75);
		line-height: 1.2;
	}

	/* ── Chart ── */
	.chart-area {
		padding: 0.375rem 0 0.25rem 0.5rem;
		min-width: 115%;
	}

	.chart-area svg {
		width: 100%;
		height: auto;
		display: block;
		overflow: visible;
	}

	.chart-area :global(.center-value) {
		font-size: 7px;
		font-weight: 700;
		fill: rgba(0, 0, 0, 0.8);
	}

	.chart-area :global(.center-label) {
		font-size: 4px;
		font-weight: 500;
		fill: rgba(0, 0, 0, 0.3);
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.chart-area :global(.overflow-text) {
		font-size: 5.5px;
		font-weight: 400;
		line-height: 1.6;
	}

	/* ── Footer ── */
	.footer {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.5rem 0.875rem 0.75rem;
		border-top: 1px solid rgba(0, 0, 0, 0.04);
	}

	.footer-total {
		font-size: 0.75rem;
		font-weight: 600;
		color: rgba(0, 0, 0, 0.65);
	}

	.footer-change {
		font-size: 0.625rem;
		font-weight: 600;
		color: #0d9488;
	}
</style>
