<script lang="ts">
	const heatData: number[][] = [
		[0.12, 0.20, 0.45, 0.28, 0.52, 0.18, 0.10],
		[0.15, 0.32, 0.65, 0.75, 0.60, 0.35, 0.12],
		[0.18, 0.42, 0.85, 0.92, 0.80, 0.45, 0.18],
		[0.12, 0.28, 0.55, 0.68, 0.52, 0.30, 0.12],
		[0.08, 0.18, 0.35, 0.40, 0.28, 0.15, 0.08],
		[0.05, 0.10, 0.20, 0.25, 0.15, 0.08, 0.05]
	];

	const days = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];
	const hours = ['6 AM', '9 AM', '12 PM', '3 PM', '6 PM', '9 PM'];

	function valueToColor(v: number): string {
		const lo = { r: 110, g: 231, b: 183 };
		const mid = { r: 6, g: 182, b: 212 };
		const hi = { r: 99, g: 102, b: 241 };
		let r: number, g: number, b: number;
		if (v <= 0.5) {
			const t = v / 0.5;
			r = Math.round(lo.r + (mid.r - lo.r) * t);
			g = Math.round(lo.g + (mid.g - lo.g) * t);
			b = Math.round(lo.b + (mid.b - lo.b) * t);
		} else {
			const t = (v - 0.5) / 0.5;
			r = Math.round(mid.r + (hi.r - mid.r) * t);
			g = Math.round(mid.g + (hi.g - mid.g) * t);
			b = Math.round(mid.b + (hi.b - mid.b) * t);
		}
		return `rgb(${r}, ${g}, ${b})`;
	}
</script>

<div class="mockup-inner">
	<p class="header">Traffic heatmap</p>

	<!-- Day labels row -->
	<div class="day-row">
		<span class="time-spacer"></span>
		{#each days as day}
			<span class="day-label">{day}</span>
		{/each}
	</div>

	<!-- Grid with hour labels -->
	<div class="grid-wrapper">
		{#each heatData as row, rowIdx}
			<div class="grid-row">
				<span class="time-label">{hours[rowIdx]}</span>
				{#each row as cell}
					<div class="cell" style="background: {valueToColor(cell)}"></div>
				{/each}
			</div>
		{/each}
	</div>

	</div>

<style>
	.mockup-inner {
		padding: 1rem 1rem 0 1.25rem;
		transform: scale(1.2);
		transform-origin: top left;
	}

	.header {
		font-size: 0.9375rem;
		font-weight: 600;
		color: rgba(0, 0, 0, 0.75);
		margin-bottom: 0.625rem;
	}

	.day-row {
		display: flex;
		gap: 5px;
		margin-bottom: 4px;
	}

	.time-spacer {
		width: 2.25rem;
		flex-shrink: 0;
	}

	.day-label {
		flex: 1;
		text-align: center;
		font-size: 0.5rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.25);
	}

	.grid-wrapper {
		display: flex;
		flex-direction: column;
		gap: 5px;
	}

	.grid-row {
		display: flex;
		gap: 5px;
		align-items: center;
	}

	.time-label {
		width: 2.25rem;
		flex-shrink: 0;
		font-size: 0.4375rem;
		color: rgba(0, 0, 0, 0.25);
		text-align: right;
		padding-right: 0.375rem;
		white-space: nowrap;
	}

	.cell {
		flex: 1;
		aspect-ratio: 1;
		border-radius: 50%;
	}

</style>
