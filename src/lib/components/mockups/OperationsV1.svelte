<script lang="ts">
	import MockupBar from './MockupBar.svelte';
	const stats = [
		{ label: 'Avg. Salary (BOH)', sub: '€17,40/hr', trend: [15, 16, 17], change: '+6%', stroke: '#06b6d4' },
		{ label: 'Avg. Salary (FOH)', sub: '€14,20/hr', trend: [13, 14, 14], change: '+3%', stroke: '#06b6d4' },
		{ label: 'Open Positions', sub: '1.240 listed', trend: [800, 1050, 1240], change: '+18%', stroke: '#06b6d4' },
		{ label: 'Workers in Area', sub: '8,4K available', trend: [9, 8.7, 8.4], change: '−2%', stroke: '#f472b6' }
	];

	function sparklinePoints(trend: number[]): string {
		const min = Math.min(...trend);
		const max = Math.max(...trend);
		const range = max - min || 1;

		return trend
			.map((v, i) => {
				const x = i * 15;
				const y = 11 - ((v - min) / range) * 10;
				return `${x},${y}`;
			})
			.join(' ');
	}
</script>

<MockupBar label="Workforce">
	<div class="period-selector">
		<span class="period">3M</span>
		<span class="period active">6M</span>
		<span class="period">1Y</span>
	</div>
</MockupBar>

<div class="body">
	<div class="hero">
		<div class="hero-main">
			<span class="hero-value">€16,10</span>
			<span class="hero-change">+4,2%</span>
		</div>
		<div class="hero-sub">Avg. Hourly Wage · Berlin 10405</div>
	</div>

	<div class="stat-list">
		{#each stats as s, i}
			<div class="stat-row" class:first={i === 0}>
				<div class="stat-name">
					<span class="stat-label">{s.label}</span>
					<span class="stat-sub">{s.sub}</span>
				</div>
				<svg class="sparkline" viewBox="0 0 30 12" fill="none">
					<polyline
						points={sparklinePoints(s.trend)}
						stroke={s.stroke}
						stroke-width="1.5"
						stroke-linecap="round"
						stroke-linejoin="round"
					/>
				</svg>
				<span class="net-badge" style="color: {s.stroke}; background: {s.stroke}14;">
					{s.change}
				</span>
			</div>
		{/each}
	</div>

	<div class="source-note">Sources: Indeed, BLS, Google Jobs</div>
</div>

<style>
	.period-selector {
		display: flex;
		gap: 0;
		background: rgba(0, 0, 0, 0.04);
		border-radius: 0.25rem;
		overflow: hidden;
		margin-left: auto;
	}

	.period {
		font-size: 0.5625rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.3);
		padding: 0.2rem 0.4rem;
		cursor: default;
	}

	.period.active {
		background: rgba(0, 0, 0, 0.06);
		color: rgba(0, 0, 0, 0.5);
		border-radius: 0.25rem;
	}

	.body {
		padding: 0.875rem 1.25rem 0.75rem;
	}

	.hero {
		margin-bottom: 0.875rem;
	}

	.hero-main {
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

	.hero-change {
		font-size: 0.8125rem;
		font-weight: 600;
		color: #06b6d4;
	}

	.hero-sub {
		font-size: 0.6875rem;
		color: rgba(0, 0, 0, 0.35);
		margin-top: 0.2rem;
	}

	.stat-list {
		display: flex;
		flex-direction: column;
		border-top: 1px solid rgba(0, 0, 0, 0.04);
		padding-top: 0.5rem;
	}

	.stat-row {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		padding: 0.5rem 0;
		border-top: 1px solid rgba(0, 0, 0, 0.04);
	}

	.stat-row.first {
		border-top: none;
	}

	.stat-name {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
	}

	.stat-label {
		font-size: 0.6875rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.55);
	}

	.stat-sub {
		font-size: 0.5625rem;
		color: rgba(0, 0, 0, 0.3);
	}

	.sparkline {
		width: 2.5rem;
		height: 1rem;
		flex-shrink: 0;
	}

	.net-badge {
		font-size: 0.625rem;
		font-weight: 600;
		padding: 0.2rem 0.45rem;
		border-radius: 0.3rem;
		flex-shrink: 0;
		line-height: 1.2;
	}

	.source-note {
		font-size: 0.5rem;
		color: rgba(0, 0, 0, 0.25);
		margin-top: 0.75rem;
		padding-top: 0.5rem;
		border-top: 1px solid rgba(0, 0, 0, 0.04);
	}
</style>
