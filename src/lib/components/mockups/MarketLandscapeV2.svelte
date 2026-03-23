<script lang="ts">
	const categories = [
		{ name: 'Vegan', locations: 127, trend: [4, 7, 11], stroke: '#06b6d4', grad: 'from-[#6ee7b7] to-[#06b6d4]' },
		{ name: 'Asian Fusion', locations: 203, trend: [5, 6, 8], stroke: '#6366f1', grad: 'from-[#06b6d4] to-[#6366f1]' },
		{ name: 'Mexican', locations: 341, trend: [6, 7, 7], stroke: '#6366f1', grad: 'from-[#a78bfa] to-[#6366f1]' },
		{ name: 'Italian', locations: 456, trend: [9, 7, 5], stroke: '#f472b6', grad: 'from-[#fbbf24] to-[#f472b6]' },
		{ name: 'American', locations: 512, trend: [8, 7, 6], stroke: '#a78bfa', grad: 'from-[#f472b6] to-[#a78bfa]' }
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

<div class="top-bar">
	<div class="bar-icon">
		<span></span><span></span>
	</div>
	<span class="bar-label">Category Trends</span>
	<div class="period-selector">
		<span class="period">3M</span>
		<span class="period active">6M</span>
		<span class="period">1Y</span>
	</div>
</div>

<div class="body">
	{#each categories as cat, i}
		<div class="row">
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
		</div>
	{/each}
</div>


<style>
	.top-bar {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.75rem 0.875rem;
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
		padding: 0.625rem 0.875rem;
	}

	.circle {
		width: 2rem;
		height: 2rem;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.row {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		padding: 0.375rem 0;
	}

	.name-group {
		flex: 1;
	}

	.name {
		font-size: 0.8125rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.75);
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

</style>
