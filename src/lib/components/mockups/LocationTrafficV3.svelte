<script lang="ts">
	import MockupBar from './MockupBar.svelte';
	const zones = ['Kollwitzplatz', 'Helmholtzpl.', 'Kastanienallee', 'Schönhauser'];
	const periods = ['Q1', 'Q2', 'Q3', 'Q4'];

	const traffic: number[][] = [
		[8.4, 9.1, 9.5, 9.2],
		[6.8, 7.2, 7.5, 7.8],
		[5.2, 5.0, 5.8, 6.1],
		[4.1, 4.5, 4.3, 4.8]
	];

	function cellColor(score: number): string {
		if (score >= 9.0) return 'rgba(99, 102, 241, 0.55)';
		if (score >= 8.0) return 'rgba(99, 102, 241, 0.35)';
		if (score >= 7.0) return 'rgba(6, 182, 212, 0.35)';
		if (score >= 6.0) return 'rgba(6, 182, 212, 0.2)';
		if (score >= 5.0) return 'rgba(244, 114, 182, 0.25)';
		return 'rgba(244, 114, 182, 0.4)';
	}

	const legendStops = [
		{ color: 'rgba(244, 114, 182, 0.4)' },
		{ color: 'rgba(244, 114, 182, 0.25)' },
		{ color: 'rgba(6, 182, 212, 0.2)' },
		{ color: 'rgba(6, 182, 212, 0.35)' },
		{ color: 'rgba(99, 102, 241, 0.35)' },
		{ color: 'rgba(99, 102, 241, 0.55)' }
	];
</script>

<div class="wrapper">
	<MockupBar label="Foot Traffic Index" compact>
		<div class="range-pills">
			<span class="range-pill">6m</span>
			<span class="range-pill active">1y</span>
			<span class="range-pill">2y</span>
		</div>
	</MockupBar>

	<div class="body">
		<div class="heatmap">
			<div class="heatmap-header">
				<div class="row-label-spacer"></div>
				{#each periods as period}
					<div class="col-header">{period}</div>
				{/each}
			</div>

			{#each zones as zone, rowIdx}
				<div class="heatmap-row">
					<div class="row-label">{zone}</div>
					{#each traffic[rowIdx] as score}
						<div class="cell" style="background: {cellColor(score)}">
							{score.toFixed(1)}
						</div>
					{/each}
				</div>
			{/each}
		</div>

		<div class="summary">
			<div class="summary-left">
				<span class="summary-value">7.4</span>
				<span class="summary-denominator">/ 10</span>
			</div>
			<div class="summary-right">
				<span class="summary-change">+0.6</span>
				<span class="summary-context">vs prior year</span>
			</div>
		</div>

		<div class="legend">
			<span class="legend-label">Low</span>
			<div class="legend-bar">
				{#each legendStops as stop}
					<div class="legend-stop" style="background: {stop.color}"></div>
				{/each}
			</div>
			<span class="legend-label">High</span>
		</div>
	</div>
</div>

<style>
	.wrapper {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-width: 115%;
	}

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

	.body {
		padding: 1rem 1rem;
	}

	.heatmap {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}

	.heatmap-header {
		display: flex;
		align-items: flex-end;
		gap: 0.3rem;
		padding-bottom: 0.25rem;
	}

	.row-label-spacer {
		width: 4.75rem;
		flex-shrink: 0;
	}

	.col-header {
		flex: 1;
		text-align: center;
		font-size: 0.5625rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.35);
	}

	.heatmap-row {
		display: flex;
		align-items: center;
		gap: 0.3rem;
	}

	.row-label {
		width: 4.75rem;
		flex-shrink: 0;
		font-size: 0.6875rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.55);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		text-align: right;
		padding-right: 0.5rem;
	}

	.cell {
		flex: 1;
		aspect-ratio: 1.3;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 0.25rem;
		font-size: 0.625rem;
		font-weight: 600;
		color: rgba(0, 0, 0, 0.65);
		line-height: 1;
	}

	.summary {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		border-top: 1px solid rgba(0, 0, 0, 0.04);
		margin-top: 0.75rem;
		padding-top: 0.75rem;
	}

	.summary-left {
		display: flex;
		align-items: baseline;
		gap: 0.25rem;
	}

	.summary-value {
		font-size: 1.5rem;
		font-weight: 700;
		color: rgba(0, 0, 0, 0.88);
		line-height: 1.1;
		letter-spacing: -0.02em;
	}

	.summary-denominator {
		font-size: 0.75rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.3);
	}

	.summary-right {
		display: flex;
		align-items: baseline;
		gap: 0.25rem;
	}

	.summary-change {
		font-size: 0.8125rem;
		font-weight: 600;
		color: #0d9488;
	}

	.summary-context {
		font-size: 0.625rem;
		color: rgba(0, 0, 0, 0.3);
	}

	.legend {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		margin-top: 0.5rem;
		padding-top: 0.5rem;
		border-top: 1px solid rgba(0, 0, 0, 0.04);
	}

	.legend-label {
		font-size: 0.5rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.25);
		flex-shrink: 0;
	}

	.legend-bar {
		display: flex;
		flex: 1;
		gap: 1px;
		height: 0.375rem;
		border-radius: 0.125rem;
		overflow: hidden;
	}

	.legend-stop {
		flex: 1;
	}
</style>
