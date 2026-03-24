<script lang="ts">
	import SectionHeader from './SectionHeader.svelte';
	import MarketLandscapeV3 from './mockups/MarketLandscapeV3.svelte';
	import MenuPricingV1 from './mockups/MenuPricingV1.svelte';
	import RevenueSalesV2 from './mockups/RevenueSalesV2.svelte';
	import MarketingV2 from './mockups/MarketingV2.svelte';
	import GuestIntelligenceV2 from './mockups/GuestIntelligenceV2.svelte';
	import LocationTrafficV1 from './mockups/LocationTrafficV1.svelte';
	import OperationsV1 from './mockups/OperationsV1.svelte';
</script>

<section id="platform" class="border-t border-cream-200 py-24 md:py-32">
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
					<p class="desc">Restaurant openings and closings, cuisine trends, competitor benchmarking, and top-performing venues — continuously tracked across the market.</p>
				</div>

				<div class="mockup">
					<MarketLandscapeV3 />
				</div>
			</div>

			<!-- 2 · Menu & Pricing -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Menu & Pricing</h3>
					<p class="desc">Trending items, price tracking, competitor menus, delivery markups, and promotional activity across the market.</p>
				</div>

				<div class="mockup mockup-edge">
					<MenuPricingV1 />
				</div>
			</div>

			<!-- 3 · Revenue & Sales -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Revenue & Sales</h3>
					<p class="desc">Revenue estimates, margin and food cost analysis, seasonality patterns, channel splits, and delivery platform market share.</p>
				</div>

				<div class="mockup mockup-edge">
					<RevenueSalesV2 />
				</div>
			</div>

			<!-- 4 · Marketing & Digital -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Marketing & Digital</h3>
					<p class="desc">Social media activity, marketing channels, estimated ad spend, and tools and platforms in use across competitors.</p>
				</div>

				<div class="mockup-free">
					<MarketingV2 />
				</div>
			</div>

			<!-- 5 · Guest Intelligence -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Guest Intelligence</h3>
					<p class="desc">Review sentiment, local guest preferences, tourist vs local mix, and payment method trends, all derived from real guest data.</p>
				</div>

				<div class="mockup mockup-edge">
					<GuestIntelligenceV2 />
				</div>
			</div>

			<!-- 6 · Location & Foot Traffic -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Location & Foot Traffic</h3>
					<p class="desc">Measured and projected foot traffic, demographic profiles, purchasing power, and visit time distribution.</p>
				</div>

				<div class="mockup">
					<LocationTrafficV1 />
				</div>
			</div>

			<!-- 7 · Operations -->
			<div class="card">
				<div class="card-text">
					<h3 class="title">Operations</h3>
					<p class="desc">Labor pool availability, salary benchmarks, job market activity, staff turnover, commercial rent, and supplier pricing.</p>
				</div>

				<div class="mockup">
					<OperationsV1 />
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
		height: 6rem;
		margin-bottom: 2rem;
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

</style>
