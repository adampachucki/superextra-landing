<script lang="ts">
	import MockupBar from './MockupBar.svelte';
	const categories = [
		{
			name: 'Vegan',
			locations: 14,
			trend: [4, 7, 11],
			net: 7,
			grad: 'from-[#6ee7b7] to-[#06b6d4]',
			stroke: '#06b6d4'
		},
		{
			name: 'Italian',
			locations: 48,
			trend: [8, 5, 6],
			net: -2,
			grad: 'from-[#fbbf24] to-[#f472b6]',
			stroke: '#f472b6'
		},
		{
			name: 'Asian Fusion',
			locations: 31,
			trend: [6, 7, 6],
			net: 0,
			grad: 'from-[#06b6d4] to-[#6366f1]',
			stroke: '#06b6d4'
		},
		{
			name: 'American',
			locations: 52,
			trend: [9, 7, 5],
			net: -4,
			grad: 'from-[#f472b6] to-[#a78bfa]',
			stroke: '#f472b6'
		},
		{
			name: 'Mexican',
			locations: 35,
			trend: [7, 8, 10],
			net: 3,
			grad: 'from-[#a78bfa] to-[#6366f1]',
			stroke: '#06b6d4'
		}
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

<MockupBar label="Category Trends" icon="trend">
	<div class="period-selector">
		<span class="period">3M</span>
		<span class="period active">6M</span>
		<span class="period">1Y</span>
	</div>
</MockupBar>

<div class="body">
	{#each categories as cat, i}
		<div class="row" class:row-border={i > 0}>
			<div class="circle bg-gradient-to-br {cat.grad}"></div>
			<div class="name-group">
				<span class="name">{cat.name}</span>
				<span class="subtitle">{cat.locations} locations</span>
			</div>
			<svg class="sparkline" viewBox="0 0 30 12" fill="none">
				<polyline
					points={sparklinePoints(cat.trend)}
					stroke={cat.stroke}
					stroke-width="1.5"
					stroke-linecap="round"
					stroke-linejoin="round"
				/>
			</svg>
			<span class="net-badge" style="color: {cat.stroke}; background: {cat.stroke}14;">
				{cat.net > 0 ? '+' : ''}{cat.net}
			</span>
		</div>
	{/each}
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
	}

	.period.active {
		background: rgba(0, 0, 0, 0.06);
		color: rgba(0, 0, 0, 0.5);
		border-radius: 0.25rem;
	}

	.body {
		padding: 0.625rem 1.25rem;
	}

	.row {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		padding: 0.5rem 0;
	}

	.row-border {
		border-top: 1px solid rgba(0, 0, 0, 0.04);
	}

	.circle {
		width: 2rem;
		height: 2rem;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.name-group {
		flex: 1;
	}

	.name {
		font-size: 0.8125rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.75);
		display: block;
	}

	.subtitle {
		font-size: 0.6875rem;
		color: rgba(0, 0, 0, 0.35);
		display: block;
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
</style>
