<script lang="ts">
	import MockupBar from './MockupBar.svelte';
	const categories = ['Food Quality', 'Service', 'Ambiance', 'Value'];
	const months = ['Nov', 'Dec', 'Jan', 'Feb'];

	const scores: number[][] = [
		[4.2, 4.5, 4.6, 4.7],
		[3.9, 4.0, 4.1, 4.2],
		[4.5, 4.4, 4.6, 4.5],
		[3.6, 3.7, 3.9, 4.0]
	];

	function cellColor(score: number): string {
		if (score >= 4.5) return 'rgba(99, 102, 241, 0.55)';
		if (score >= 4.2) return 'rgba(99, 102, 241, 0.35)';
		if (score >= 4.0) return 'rgba(6, 182, 212, 0.35)';
		if (score >= 3.7) return 'rgba(6, 182, 212, 0.2)';
		if (score >= 3.4) return 'rgba(244, 114, 182, 0.3)';
		return 'rgba(244, 114, 182, 0.5)';
	}

	function textColor(_score: number): string {
		return 'rgba(0, 0, 0, 0.65)';
	}

	const legendStops = [
		{ label: '2.0', color: 'rgba(244, 114, 182, 0.5)' },
		{ label: '3.0', color: 'rgba(244, 114, 182, 0.3)' },
		{ label: '3.5', color: 'rgba(6, 182, 212, 0.2)' },
		{ label: '4.0', color: 'rgba(6, 182, 212, 0.35)' },
		{ label: '4.5', color: 'rgba(99, 102, 241, 0.35)' },
		{ label: '5.0', color: 'rgba(99, 102, 241, 0.55)' }
	];
</script>

<div class="wrapper">
	<MockupBar label="Guest Sentiment" compact>
		<div class="range-pills">
			<span class="range-pill">3m</span>
			<span class="range-pill active">6m</span>
			<span class="range-pill">1y</span>
		</div>
	</MockupBar>

	<div class="body">
		<div class="heatmap">
			<div class="heatmap-header">
				<div class="row-label-spacer"></div>
				{#each months as month}
					<div class="col-header">{month}</div>
				{/each}
			</div>

			{#each categories as cat, rowIdx}
				<div class="heatmap-row">
					<div class="row-label">{cat}</div>
					{#each scores[rowIdx] as score}
						<div class="cell" style="background: {cellColor(score)}; color: {textColor(score)}">
							{score.toFixed(1)}
						</div>
					{/each}
				</div>
			{/each}
		</div>

		<div class="summary">
			<div class="summary-left">
				<span class="summary-value">4.2</span>
				<span class="summary-denominator">/ 5.0</span>
			</div>
			<div class="summary-right">
				<span class="summary-change">+0.3</span>
				<span class="summary-context">vs prior quarter</span>
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

	/* ── Body ── */
	.body {
		padding: 1rem 1rem;
	}

	/* ── Heatmap ── */
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
		line-height: 1;
	}

	/* ── Summary ── */
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

	/* ── Legend ── */
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
