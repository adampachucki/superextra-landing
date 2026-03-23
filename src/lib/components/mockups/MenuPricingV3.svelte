<script lang="ts">
	const platforms = [
		{ key: 'uber', name: 'Uber Eats', color: '#f97316' },
		{ key: 'wolt', name: 'Wolt', color: '#3b82f6' },
		{ key: 'glovo', name: 'Glovo', color: '#22c55e' }
	];

	const items = [
		{ name: 'Margherita', base: 12.5, uber: 14.8, wolt: 15.5, glovo: 15.0 },
		{ name: 'Pad Thai', base: 14.0, uber: 16.2, wolt: 17.9, glovo: 17.1 },
		{ name: 'Smash Burger', base: 11.0, uber: 13.3, wolt: 13.5, glovo: 13.1 },
		{ name: 'Poke Bowl', base: 15.5, uber: 17.8, wolt: 19.5, glovo: 19.2 }
	];

	/* Scale from 0 to a bit past the highest delivery price */
	const maxDelivery = Math.max(
		...items.flatMap((i) => [i.uber, i.wolt, i.glovo])
	);
	const scale = maxDelivery * 1.05;

	function pct(v: number): number {
		return (v / scale) * 100;
	}
</script>

<div class="top-bar">
	<div class="bar-icon">
		<span></span><span></span>
	</div>
	<span class="bar-label">Delivery Markup</span>
</div>

<div class="body">
	{#each items as item, i}
		{@const markups = platforms.map((p) => ({
			...p,
			delivery: item[p.key as keyof typeof item] as number,
			amount: (item[p.key as keyof typeof item] as number) - item.base
		}))}
		<div class="row" class:row-border={i > 0}>
			<div class="row-header">
				<span class="item-name">{item.name}</span>
				<span class="item-base">&euro;{item.base.toFixed(1)}</span>
			</div>
			<div class="bars">
				{#each markups as m}
					<div class="bar-row">
						<div class="bar-track">
							<!-- Base portion (grey) -->
							<div class="bar-base" style="width: {pct(item.base)}%"></div>
							<!-- Markup extension (colored) -->
							<div
								class="bar-markup"
								style="left: {pct(item.base)}%; width: {pct(m.amount)}%; background: {m.color}"
							></div>
						</div>
						<span class="bar-price" style="color: {m.color}">+{m.amount.toFixed(1)}</span>
					</div>
				{/each}
			</div>
		</div>
	{/each}

	<div class="legend">
		{#each platforms as p}
			<span class="legend-item">
				<span class="legend-dot" style="background: {p.color}"></span>
				{p.name}
			</span>
		{/each}
	</div>
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
		padding: 0.75rem 1.25rem;
	}

	/* ── Row ── */
	.row {
		padding: 0.5rem 0;
	}

	.row-border {
		border-top: 1px solid rgba(0, 0, 0, 0.04);
	}

	.row-header {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		margin-bottom: 0.375rem;
	}

	.item-name {
		font-size: 0.8125rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.7);
		line-height: 1;
	}

	.item-base {
		font-size: 0.625rem;
		color: rgba(0, 0, 0, 0.28);
		font-weight: 500;
		line-height: 1;
	}

	/* ── Bars ── */
	.bars {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.bar-row {
		display: flex;
		align-items: center;
		gap: 0.3rem;
	}

	.bar-track {
		flex: 1;
		min-width: 0;
		height: 0.3125rem;
		position: relative;
		background: rgba(0, 0, 0, 0.025);
		border-radius: 0.15rem;
		overflow: hidden;
	}

	.bar-base {
		position: absolute;
		left: 0;
		top: 0;
		bottom: 0;
		background: rgba(0, 0, 0, 0.06);
		border-radius: 0.15rem 0 0 0.15rem;
	}

	.bar-markup {
		position: absolute;
		top: 0;
		bottom: 0;
		border-radius: 0 0.15rem 0.15rem 0;
		opacity: 0.6;
	}

	.bar-price {
		font-size: 0.5rem;
		font-weight: 600;
		white-space: nowrap;
		width: 1.5rem;
		text-align: right;
		flex-shrink: 0;
		line-height: 1;
	}

	/* ── Legend ── */
	.legend {
		display: flex;
		gap: 0.75rem;
		margin-top: 0.5rem;
		padding-top: 0.5rem;
		border-top: 1px solid rgba(0, 0, 0, 0.04);
	}

	.legend-item {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.5625rem;
		color: rgba(0, 0, 0, 0.35);
		font-weight: 500;
	}

	.legend-dot {
		width: 5px;
		height: 5px;
		border-radius: 50%;
		flex-shrink: 0;
	}
</style>
