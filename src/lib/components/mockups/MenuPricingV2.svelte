<script lang="ts">
	const items = [
		{ name: 'Negroni', you: 12, avg: 14, min: 9, max: 18 },
		{ name: 'Espresso Martini', you: 15, avg: 16, min: 11, max: 21 },
		{ name: 'Aperol Spritz', you: 11, avg: 11, min: 8, max: 15 }
	];

	function pct(value: number, min: number, max: number): number {
		return ((value - min) / (max - min)) * 100;
	}

	function dotColor(you: number, avg: number): string {
		if (you < avg - 0.5) return '#10b981';
		if (you > avg + 0.5) return '#ef4444';
		return '#f59e0b';
	}

	let belowCount = $derived(items.filter((i) => i.you < i.avg - 0.5).length);
</script>

<div class="top-bar">
	<div class="bar-icon">
		<span></span><span></span>
	</div>
	<span class="bar-label">Price Positioning</span>
</div>

<div class="body">
	{#each items as item}
		<div class="row">
			<div class="row-header">
				<span class="item-name">{item.name}</span>
				<span class="item-avg">${item.avg} avg</span>
			</div>
			<div class="range-bar">
				<div class="track"></div>
				<div
					class="avg-tick"
					style="left: {pct(item.avg, item.min, item.max)}%"
				></div>
				<div
					class="you-dot"
					style="left: {pct(item.you, item.min, item.max)}%; background: {dotColor(item.you, item.avg)}"
				></div>
			</div>
		</div>
	{/each}

	<div class="narrative">
		<p>Negroni consistently underpriced relative to the local competitive set — the current gap suggests room for a 10–15% increase without impacting volume.</p>
		<p>Espresso Martini tracks just below the market median, while Aperol Spritz sits right at parity.</p>
		<p>Seasonal demand shifts in Q2 could widen the gap further as rooftop venues adjust upward.</p>
	</div>
</div>

<div class="footer">
	<span class="footer-text">{belowCount} of {items.length} items below market avg</span>
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

	/* ── Body ── */
	.body {
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		padding: 1.25rem 1.25rem;
	}

	/* ── Item row — stacked: header above spectrum ── */
	.row {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.row-header {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
	}

	.item-name {
		font-size: 0.8125rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.85);
		line-height: 1;
	}

	.item-avg {
		font-size: 0.6875rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.35);
		line-height: 1;
		white-space: nowrap;
	}

	/* ── Range bar ── */
	.range-bar {
		position: relative;
		height: 14px;
		width: 100%;
	}

	.track {
		position: absolute;
		top: 50%;
		left: 0;
		right: 0;
		height: 1px;
		background: rgba(0, 0, 0, 0.06);
		border-radius: 2px;
		transform: translateY(-50%);
	}

	.avg-tick {
		position: absolute;
		top: 50%;
		width: 2px;
		height: 12px;
		background: rgba(0, 0, 0, 0.8);
		border-radius: 1px;
		transform: translate(-50%, -50%);
	}

	.you-dot {
		position: absolute;
		top: 50%;
		width: 8px;
		height: 8px;
		border-radius: 50%;
		transform: translate(-50%, -50%);
		box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.9);
	}

	/* ── Narrative ── */
	.narrative {
		border-left: 2px solid rgba(0, 0, 0, 0.08);
		padding-left: 0.75rem;
		margin-top: 0.25rem;
	}

	.narrative p {
		font-size: 0.6875rem;
		line-height: 1.5;
		color: rgba(0, 0, 0, 0.85);
		margin: 0;
	}

	.narrative p + p {
		margin-top: 0.5rem;
	}

	/* ── Footer ── */
	.footer {
		padding: 0.5rem 1.25rem 0.75rem;
		border-top: 1px solid rgba(0, 0, 0, 0.04);
	}

	.footer-text {
		font-size: 0.6875rem;
		color: rgba(0, 0, 0, 0.35);
		font-weight: 500;
	}
</style>
