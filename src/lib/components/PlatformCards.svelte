<script lang="ts">
	import SectionHeader from './SectionHeader.svelte';
	import MarketLandscapeV2 from './mockups/MarketLandscapeV2.svelte';
	import MenuPricingV4 from './mockups/MenuPricingV4.svelte';
	import RevenueSalesV1 from './mockups/RevenueSalesV1.svelte';
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
					<MarketLandscapeV2 />
				</div>
			</div>

			<!-- 2 · Menu & Pricing -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Menu & Pricing</h3>
					<p class="desc">How the market positions menus, at what price point, and how delivery shapes the landscape.</p>
				</div>

				<div class="mockup">
					<MenuPricingV4 />
				</div>
			</div>

			<!-- 3 · Revenue & Sales -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Revenue & Sales</h3>
					<p class="desc">Revenue estimates, seasonality patterns, and channel splits across the competitive set.</p>
				</div>

				<div class="mockup mockup-edge">
					<RevenueSalesV1 />
				</div>
			</div>

			<!-- 4 · Marketing & Digital -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Marketing & Digital</h3>
					<p class="desc">Where budgets go, which channels drive results, and what tools the market relies on.</p>
				</div>

				<div class="mockup">
					<div class="mockup-body pt-4">
						<p class="select-header">Channel mix</p>

						{#each [
							{ name: 'Instagram', pct: '42%', grad: 'from-[#f472b6] to-[#a78bfa]' },
							{ name: 'Google Ads', pct: '31%', grad: 'from-[#06b6d4] to-[#6366f1]' },
							{ name: 'TikTok', pct: '18%', grad: 'from-[#6ee7b7] to-[#fbbf24]' },
							{ name: 'Email', pct: '9%', grad: 'from-[#fbbf24] to-[#f472b6]' },
							{ name: 'Referral', pct: '5%', grad: 'from-[#a78bfa] to-[#06b6d4]' }
						] as ch}
							<div class="list-row compact">
								<div class="circle-sm bg-gradient-to-br {ch.grad}"></div>
								<span class="list-name flex-1">{ch.name}</span>
								<span class="list-meta">{ch.pct}</span>
							</div>
						{/each}
					</div>
				</div>
			</div>

			<!-- 5 · Guest Intelligence -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Guest Intelligence</h3>
					<p class="desc">What guests think, want, and expect — from real reviews and behavioural data.</p>
				</div>

				<div class="mockup">
					<div class="mockup-body pt-4">
						<p class="select-header">Review sentiment</p>

						{#each [
							{ stars: '★★★★★', pct: 62 },
							{ stars: '★★★★☆', pct: 24 },
							{ stars: '★★★☆☆', pct: 9 },
							{ stars: '★★☆☆☆', pct: 3 },
							{ stars: '★☆☆☆☆', pct: 2 }
						] as r}
							<div class="rating-row">
								<span class="rating-stars">{r.stars}</span>
								<div class="rating-bar-track">
									<div class="rating-bar" style="width:{r.pct}%"></div>
								</div>
								<span class="rating-pct">{r.pct}%</span>
							</div>
						{/each}

						<div class="mt-4 pt-3 border-t border-black/[0.04]">
							<p class="text-[11px] text-black/35 mb-2">Average: 4.4 · ↑ 0.2 vs last quarter</p>
							<p class="text-[12px] font-medium text-black/55 mb-1">Top keywords</p>
							<p class="text-[11px] text-black/35">Great atmosphere · Slow service · Fresh ingredients</p>
						</div>
					</div>
				</div>
			</div>

			<!-- 6 · Location & Foot Traffic -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Location & Foot Traffic</h3>
					<p class="desc">Traffic patterns, demographics, purchasing power, and rent trends.</p>
				</div>

				<div class="mockup">
					<div class="mockup-body pt-4 pb-4">
						<p class="select-header">Traffic heatmap</p>

						<div class="grid grid-cols-7 gap-[5px] mb-3 px-1">
							{#each [
								[0.08, 0.15, 0.40, 0.22, 0.50, 0.12, 0.08],
								[0.10, 0.28, 0.60, 0.72, 0.58, 0.30, 0.10],
								[0.14, 0.38, 0.82, 0.95, 0.78, 0.42, 0.15],
								[0.10, 0.22, 0.52, 0.62, 0.48, 0.25, 0.10],
								[0.06, 0.12, 0.28, 0.35, 0.22, 0.10, 0.06],
								[0.04, 0.08, 0.15, 0.20, 0.12, 0.06, 0.04]
							] as row}
								{#each row as cell}
									<div class="aspect-square rounded-full" style="background:rgba(0,0,0,{cell * 0.55})"></div>
								{/each}
							{/each}
						</div>

						<div class="flex justify-between text-[9px] text-black/20 px-1">
							<span>M</span><span>T</span><span>W</span><span>T</span><span>F</span><span>S</span><span>S</span>
						</div>

						<div class="mt-3 pt-3 border-t border-black/[0.04] text-[11px] text-black/35">
							Peak: 12–2 PM weekdays
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
</style>
