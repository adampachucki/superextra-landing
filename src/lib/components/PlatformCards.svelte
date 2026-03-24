<script lang="ts">
	import SectionHeader from './SectionHeader.svelte';
	import MarketLandscapeV3 from './mockups/MarketLandscapeV3.svelte';
	import MenuPricingV1 from './mockups/MenuPricingV1.svelte';
	import RevenueSalesV2 from './mockups/RevenueSalesV2.svelte';
	import MarketingV2 from './mockups/MarketingV2.svelte';
	import GuestIntelligenceV2 from './mockups/GuestIntelligenceV2.svelte';
</script>

<section class="border-t border-cream-200 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<SectionHeader subtitle="Extra Clarity" title="Data and insights behind every restaurant decision" titleClass="mb-4 max-w-2xl" />
		<p class="mb-16 max-w-lg text-lg text-black/60">
			Seven intelligence layers, one platform. Built for every decision a restaurant makes.
		</p>

		<div class="grid grid-cols-1 gap-5 md:grid-cols-3">

			<!-- 1 · Market Landscape -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Market Landscape</h3>
					<p class="desc">Who's opening, closing, and gaining ground — benchmarked against relevant cohorts.</p>
				</div>

				<div class="mockup">
					<MarketLandscapeV3 />
				</div>
			</div>

			<!-- 2 · Menu & Pricing -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Menu & Pricing</h3>
					<p class="desc">How the market positions menus, at what price point, and how delivery shapes the landscape.</p>
				</div>

				<div class="mockup mockup-edge">
					<MenuPricingV1 />
				</div>
			</div>

			<!-- 3 · Revenue & Sales -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Revenue & Sales</h3>
					<p class="desc">Revenue estimates, seasonality patterns, and channel splits across the competitive set.</p>
				</div>

				<div class="mockup mockup-edge">
					<RevenueSalesV2 />
				</div>
			</div>

			<!-- 4 · Marketing & Digital -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Marketing & Digital</h3>
					<p class="desc">Where budgets go, which channels drive results, and what tools the market relies on.</p>
				</div>

				<div class="mockup-free">
					<MarketingV2 />
				</div>
			</div>

			<!-- 5 · Guest Intelligence -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Guest Intelligence</h3>
					<p class="desc">What guests think, want, and expect — from real reviews and behavioural data.</p>
				</div>

				<div class="mockup mockup-edge">
					<GuestIntelligenceV2 />
				</div>
			</div>

			<!-- 6 · Location & Foot Traffic -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Location & Foot Traffic</h3>
					<p class="desc">Traffic patterns, demographics, purchasing power, and rent trends.</p>
				</div>

				<div class="mockup mockup-edge">
					<div class="mockup-bar">
						<div class="bar-icon">
							<span></span><span></span>
						</div>
						<span class="bar-label">Foot Traffic Index</span>
					</div>

					<div class="mockup-body">
						<div class="ht-grid">
							<div class="ht-header">
								<div class="ht-row-spacer"></div>
								{#each ['Q1', 'Q2', 'Q3', 'Q4'] as period}
									<div class="ht-col-head">{period}</div>
								{/each}
							</div>

							{#each [
								{ zone: 'Kollwitzplatz', scores: [8.4, 9.1, 9.5, 9.2] },
								{ zone: 'Helmholtzpl.', scores: [6.8, 7.2, 7.5, 7.8] },
								{ zone: 'Kastanienallee', scores: [5.2, 5.0, 5.8, 6.1] },
								{ zone: 'Schönhauser', scores: [4.1, 4.5, 4.3, 4.8] }
							] as row}
								<div class="ht-row">
									<div class="ht-row-label">{row.zone}</div>
									{#each row.scores as s}
										<div class="ht-cell" style="background:{s >= 9 ? 'rgba(99,102,241,0.55)' : s >= 8 ? 'rgba(99,102,241,0.35)' : s >= 7 ? 'rgba(6,182,212,0.35)' : s >= 6 ? 'rgba(6,182,212,0.2)' : s >= 5 ? 'rgba(244,114,182,0.25)' : 'rgba(244,114,182,0.4)'}">
											{s.toFixed(1)}
										</div>
									{/each}
								</div>
							{/each}
						</div>

						<div class="ht-summary">
							<div class="ht-summary-left">
								<span class="ht-big">7.4</span>
								<span class="ht-denom">/ 10</span>
							</div>
							<div class="ht-summary-right">
								<span class="ht-change">+0.6</span>
								<span class="ht-ctx">vs prior year</span>
							</div>
						</div>
					</div>
				</div>
			</div>

			<!-- 7 · Operations -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Operations</h3>
					<p class="desc">The real cost of running a restaurant — from staffing to supplier pricing.</p>
				</div>

				<div class="mockup">
					<div class="mockup-bar">
						<div class="bar-icon">
							<span></span><span></span>
						</div>
						<span class="bar-label">Cost Benchmarks</span>
					</div>

					<div class="mockup-body">
						{#each [
							{ name: 'Labor', amount: '$8.2K' },
							{ name: 'Rent', amount: '$4.5K' },
							{ name: 'Supply Chain', amount: '$6.1K' },
							{ name: 'Marketing', amount: '$2.3K' },
							{ name: 'Utilities', amount: '$1.8K' },
							{ name: 'Insurance', amount: '$1.2K' }
						] as cost, i}
							{#if i > 0}
								<div class="border-t border-black/[0.04]"></div>
							{/if}
							<div class="cost-row">
								<span class="list-name">{cost.name}</span>
								<span class="cost-amount">{cost.amount}</span>
							</div>
						{/each}
					</div>
				</div>
			</div>

		</div>
	</div>
</section>

<style>
	/* ── Card shell ── */
	.card {
		border-radius: 1rem;
		background: var(--color-cream-100);
		border: 1px solid rgba(0, 0, 0, 0.03);
		padding: 1.75rem 1.75rem;
		padding-bottom: 0;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		height: clamp(25rem, 30vw, 28rem);
	}

	.card-text {
		height: 5.25rem;
		margin-bottom: 2.5rem;
		overflow: hidden;
		flex-shrink: 0;
	}
	@media (max-width: 767px) {
		.card-text {
			height: auto;
			overflow: visible;
		}
	}

	.title {
		font-size: 1.25rem;
		font-weight: 500;
		color: #000;
	}

	.desc {
		font-size: 0.875rem;
		line-height: 1.5;
		margin-top: 0.25rem;
		color: rgba(0, 0, 0, 0.6);
	}

	/* ── Mockup container ── */
	.mockup {
		border-radius: 0.75rem 0.75rem 0 0;
		background: #fff;
		border: 1px solid rgba(0, 0, 0, 0.08);
		border-bottom: none;
		margin-bottom: -3.5rem;
		display: flex;
		flex-direction: column;
		flex: 1;
	}

	.mockup-edge {
		border-radius: 0.75rem 0 0 0;
		margin-right: -1.75rem;
		border-right: none;
	}

	.mockup-free {
		flex: 1;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		margin: 0 -1.75rem;
	}

	/* Top bar inside mockup (the ‖ icon + label row) */
	.mockup-bar {
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

	/* Body area inside mockup */
	.mockup-body {
		padding: 0.625rem 1.25rem;
		flex: 1;
	}

	/* ── List rows (competitor, category) ── */
	.list-row {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		padding: 0.5rem 0;
	}
	.list-row.compact {
		padding: 0.375rem 0;
	}

	.list-name {
		font-size: 0.8125rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.75);
	}
	.list-meta {
		font-size: 0.6875rem;
		color: rgba(0, 0, 0, 0.35);
	}

	/* Gradient circles */
	.circle {
		width: 2rem;
		height: 2rem;
		border-radius: 50%;
		flex-shrink: 0;
	}
	.circle-lg {
		width: 2.25rem;
		height: 2.25rem;
		border-radius: 50%;
		flex-shrink: 0;
	}
	.circle-sm {
		width: 1.5rem;
		height: 1.5rem;
		border-radius: 50%;
		flex-shrink: 0;
	}

	/* "Select a ..." header inside mockup */
	.select-header {
		font-size: 0.9375rem;
		font-weight: 600;
		color: rgba(0, 0, 0, 0.7);
		margin-bottom: 0.25rem;
	}

	/* ── Revenue insights ── */
	.insight-row {
		display: flex;
		align-items: flex-start;
		gap: 0.625rem;
	}
	.insight-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
		margin-top: 4px;
	}
	.insight-text {
		font-size: 0.8125rem;
		line-height: 1.5;
		color: rgba(0, 0, 0, 0.6);
	}
	.insight-text strong {
		font-weight: 600;
		color: rgba(0, 0, 0, 0.8);
	}

	/* Revenue timeline */
	.revenue-timeline {
		border-top: 1px solid rgba(0, 0, 0, 0.04);
		padding: 0.75rem 1.25rem;
	}
	.timeline-track {
		display: flex;
		align-items: center;
		gap: 0;
		margin-bottom: 0.75rem;
	}
	.timeline-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: rgba(0, 0, 0, 0.15);
		flex-shrink: 0;
	}
	.timeline-dot.active {
		background: #6366f1;
	}
	.timeline-label {
		font-size: 0.625rem;
		color: rgba(0, 0, 0, 0.3);
		margin-left: 4px;
		margin-right: 4px;
	}
	.timeline-spacer {
		flex: 1;
		height: 1px;
		background: rgba(0, 0, 0, 0.06);
	}

	.channel-tabs {
		display: flex;
		gap: 0;
	}
	.channel-tab {
		flex: 1;
		text-align: center;
		font-size: 0.6875rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.3);
		padding: 0.375rem 0;
		border-radius: 0.375rem;
	}
	.channel-tab.active {
		background: rgba(0, 0, 0, 0.05);
		color: rgba(0, 0, 0, 0.6);
	}

	/* ── Rating rows (Guest Intelligence) ── */
	.rating-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.25rem 0;
	}
	.rating-stars {
		font-size: 0.5625rem;
		color: rgba(0, 0, 0, 0.25);
		flex-shrink: 0;
		width: 3rem;
		letter-spacing: 0.5px;
	}
	.rating-bar-track {
		flex: 1;
		height: 4px;
		background: rgba(0, 0, 0, 0.04);
		border-radius: 2px;
	}
	.rating-bar {
		height: 100%;
		background: linear-gradient(to right, #6366f1, #a78bfa);
		border-radius: 2px;
	}
	.rating-pct {
		font-size: 0.625rem;
		color: rgba(0, 0, 0, 0.3);
		width: 1.75rem;
		text-align: right;
		flex-shrink: 0;
	}

	/* ── Cost rows (Operations) ── */
	.cost-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.625rem 0;
	}
	.cost-amount {
		font-size: 0.8125rem;
		font-weight: 600;
		color: rgba(0, 0, 0, 0.6);
	}

	/* ── Foot Traffic heatmap table ── */
	.ht-grid {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}
	.ht-header {
		display: flex;
		align-items: flex-end;
		gap: 0.3rem;
		padding-bottom: 0.25rem;
	}
	.ht-row-spacer {
		width: 4.75rem;
		flex-shrink: 0;
	}
	.ht-col-head {
		flex: 1;
		text-align: center;
		font-size: 0.5625rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.35);
	}
	.ht-row {
		display: flex;
		align-items: center;
		gap: 0.3rem;
	}
	.ht-row-label {
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
	.ht-cell {
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
	.ht-summary {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		border-top: 1px solid rgba(0, 0, 0, 0.04);
		margin-top: 0.75rem;
		padding-top: 0.75rem;
	}
	.ht-summary-left {
		display: flex;
		align-items: baseline;
		gap: 0.25rem;
	}
	.ht-big {
		font-size: 1.5rem;
		font-weight: 700;
		color: rgba(0, 0, 0, 0.88);
		line-height: 1.1;
		letter-spacing: -0.02em;
	}
	.ht-denom {
		font-size: 0.75rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.3);
	}
	.ht-summary-right {
		display: flex;
		align-items: baseline;
		gap: 0.25rem;
	}
	.ht-change {
		font-size: 0.8125rem;
		font-weight: 600;
		color: #0d9488;
	}
	.ht-ctx {
		font-size: 0.625rem;
		color: rgba(0, 0, 0, 0.3);
	}
</style>
