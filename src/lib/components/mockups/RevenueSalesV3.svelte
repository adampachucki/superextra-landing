<script lang="ts">
	import MockupBar from './MockupBar.svelte';
	const channels = [
		{ name: 'Dine-in', value: 160, color: '#6366f1' },
		{ name: 'Delivery', value: 88, color: '#f472b6' },
		{ name: 'Takeout', value: 58, color: '#06b6d4' }
	];

	const total = channels.reduce((sum, ch) => sum + ch.value, 0);
	const cx = 65;
	const cy = 52;
	const r = 34;
	const strokeW = 12;

	// Calculate arc segments
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
	const arcs = channels.map((ch) => {
		const angle = (ch.value / total) * 360;
		const startAngle = cumAngle;
		cumAngle += angle;
		const gap = 3;
		return {
			...ch,
			path: arcPath(startAngle + gap / 2, startAngle + angle - gap / 2),
			pct: Math.round((ch.value / total) * 100)
		};
	});
</script>

<MockupBar label="Channel Breakdown" compact>
	<div class="month-selector">
		<span class="month-arrow">&#8249;</span>
		<span class="month-name">Nov</span>
		<span class="month-arrow">&#8250;</span>
	</div>
</MockupBar>

<div class="summary">
	{#each channels as ch}
		<div class="stat">
			<span class="stat-dot" style="background: {ch.color}"></span>
			<div class="stat-text">
				<span class="stat-label">{ch.name}</span>
				<span class="stat-value">€{ch.value}K</span>
			</div>
		</div>
	{/each}
</div>

<div class="chart-area">
	<svg viewBox="0 0 200 108" fill="none">
		<!-- Donut arcs -->
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

		<!-- Center text -->
		<text x={cx} y={cy - 4} text-anchor="middle" class="center-value">${total}K</text>
		<text x={cx} y={cy + 6} text-anchor="middle" class="center-label">total</text>

		<!-- Gradient for fading text -->
		<defs>
			<linearGradient id="textFadeGrad" x1="0" y1="0" x2="0" y2="1">
				<stop offset="0%" stop-color="#1a1a1a" />
				<stop offset="60%" stop-color="#555555" />
				<stop offset="100%" stop-color="#555555" stop-opacity="0" />
			</linearGradient>
		</defs>

		<!-- Narrative text flowing off right edge -->
		<text x="128" y="18" class="overflow-text" fill="url(#textFadeGrad)">
			<tspan x="128" dy="0">Dine-in remains the</tspan>
			<tspan x="128" dy="9">dominant channel at</tspan>
			<tspan x="128" dy="9">52% of total revenue,</tspan>
			<tspan x="128" dy="9">while delivery grew</tspan>
			<tspan x="128" dy="9">steadily through the</tspan>
			<tspan x="128" dy="9">quarter reaching 29%</tspan>
			<tspan x="128" dy="9">of the monthly total.</tspan>
			<tspan x="128" dy="9">Takeout holds at 19%</tspan>
			<tspan x="128" dy="9">with seasonal peaks.</tspan>
		</text>
	</svg>
</div>

<div class="footer">
	<span class="footer-total">Total: ${total}K</span>
	<span class="footer-change">+4,8% vs Oct</span>
</div>

<style>
	/* ── Month selector ── */
	.month-selector {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		margin-left: auto;
		background: rgba(0, 0, 0, 0.04);
		border-radius: 0.25rem;
		padding: 0.2rem 0.4rem;
	}

	.month-arrow {
		font-size: 0.75rem;
		color: rgba(0, 0, 0, 0.3);
		line-height: 1;
		cursor: default;
	}

	.month-name {
		font-size: 0.5625rem;
		font-weight: 600;
		color: rgba(0, 0, 0, 0.5);
		min-width: 1.5rem;
		text-align: center;
	}

	/* ── Channel summary ── */
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
		font-size: 8px;
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
