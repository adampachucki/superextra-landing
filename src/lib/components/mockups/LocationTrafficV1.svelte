<script lang="ts">
	const grid: number[][] = [
		[0, 1, 1, 2, 1, 0, 0],
		[1, 2, 3, 3, 2, 1, 0],
		[1, 3, 4, 4, 3, 2, 1],
		[0, 2, 3, 4, 3, 1, 1],
		[0, 1, 1, 2, 2, 1, 0]
	];

	const markers: [number, number][] = [
		[0, 3], [1, 2], [1, 3], [1, 4],
		[2, 1], [2, 2], [2, 3], [2, 4], [2, 5],
		[3, 2], [3, 3], [3, 4], [3, 6],
		[4, 3], [4, 4]
	];

	const markerSet = new Set(markers.map(([r, c]) => `${r}-${c}`));

	function cellBg(level: number): string {
		if (level === 0) return 'rgba(110, 231, 183, 0.15)';
		if (level === 1) return 'rgba(6, 182, 212, 0.35)';
		if (level === 2) return 'rgba(6, 182, 212, 0.55)';
		if (level === 3) return 'rgba(99, 102, 241, 0.65)';
		return 'rgba(99, 102, 241, 0.80)';
	}

	function dotColor(level: number): string {
		if (level <= 1) return 'rgba(0, 0, 0, 0.25)';
		if (level === 2) return 'rgba(0, 0, 0, 0.35)';
		return 'rgba(255, 255, 255, 0.8)';
	}
</script>

<div class="outer">

<div class="body">
	<div class="grid-map">
		{#each grid as row, rowIdx}
			{#each row as level, colIdx}
				<div class="cell" style="background: {cellBg(level)}">
					{#if markerSet.has(`${rowIdx}-${colIdx}`)}
						<span class="dot" style="background: {dotColor(level)}"></span>
					{/if}
				</div>
			{/each}
		{/each}
	</div>

	<div class="summary">
		<div class="summary-item">
			<span class="summary-num">147</span>
			<span class="summary-label">locations</span>
		</div>
		<div class="summary-sep"></div>
		<div class="summary-item">
			<span class="summary-num">12,4</span>
			<span class="summary-label">per km²</span>
		</div>
	</div>
</div>
</div>

<style>
	.outer {
		display: flex;
		flex-direction: column;
		flex: 1;
		overflow: hidden;
	}

	.body {
		padding: 0.875rem 1.25rem;
		transform: scale(1.25);
		transform-origin: top center;
		overflow: hidden;
		flex: 1;
	}

	@media (max-width: 767px) {
		.body {
			transform: scale(1.4);
		}
	}

	.grid-map {
		display: grid;
		grid-template-columns: repeat(7, 1fr);
		grid-template-rows: repeat(5, 1fr);
		gap: 4px;
	}

	.cell {
		aspect-ratio: 1;
		border-radius: 3px;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.dot {
		width: 5px;
		height: 5px;
		border-radius: 50%;
		display: block;
	}

	.summary {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-top: 0.75rem;
		padding-top: 0.625rem;
		border-top: 1px solid rgba(0, 0, 0, 0.04);
	}

	.summary-sep {
		width: 1px;
		height: 1.25rem;
		background: rgba(0, 0, 0, 0.08);
	}

	.summary-item {
		display: flex;
		flex-direction: column;
	}

	.summary-num {
		font-size: 0.875rem;
		font-weight: 600;
		color: rgba(0, 0, 0, 0.65);
		line-height: 1.1;
	}

	.summary-label {
		font-size: 0.5rem;
		color: rgba(0, 0, 0, 0.3);
		margin-top: 0.05rem;
	}
</style>
