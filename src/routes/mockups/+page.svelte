<script lang="ts">
	import MarketLandscapeV1 from '$lib/components/mockups/MarketLandscapeV1.svelte';
	import MarketLandscapeV2 from '$lib/components/mockups/MarketLandscapeV2.svelte';
	import MarketLandscapeV3 from '$lib/components/mockups/MarketLandscapeV3.svelte';
	import MenuPricingV1 from '$lib/components/mockups/MenuPricingV1.svelte';
	import MenuPricingV2 from '$lib/components/mockups/MenuPricingV2.svelte';
	import MenuPricingV4 from '$lib/components/mockups/MenuPricingV4.svelte';
	import RevenueSalesV1 from '$lib/components/mockups/RevenueSalesV1.svelte';
	import RevenueSalesV2 from '$lib/components/mockups/RevenueSalesV2.svelte';
	import RevenueSalesV3 from '$lib/components/mockups/RevenueSalesV3.svelte';
	import MarketingV1 from '$lib/components/mockups/MarketingV1.svelte';
	import MarketingV2 from '$lib/components/mockups/MarketingV2.svelte';
	import MarketingV4 from '$lib/components/mockups/MarketingV4.svelte';

	const cards = [
		{
			id: 'market-landscape',
			title: 'Market Landscape',
			desc: "Who's opening, closing, and gaining ground — benchmarked against relevant cohorts.",
			variants: [
				{ label: 'V1 — Line Chart + Activity', component: MarketLandscapeV1 },
				{ label: 'V2 — Category Trends', component: MarketLandscapeV2 },
				{ label: 'V3 — Category List + Sparklines', component: MarketLandscapeV3 }
			]
		},
		{
			id: 'menu-pricing',
			title: 'Menu & Pricing',
			desc: 'How the market positions menus, at what price point, and how delivery shapes the landscape.',
			variants: [
				{ label: 'V1 — Price Positioning Map', component: MenuPricingV1 },
				{ label: 'V2 — Item Price Comparison', component: MenuPricingV2 },
				{ label: 'V3 — Burger Price Index', component: MenuPricingV4 }
			]
		},
		{
			id: 'revenue-sales',
			title: 'Revenue & Sales',
			desc: 'Revenue estimates, seasonality patterns, and channel splits across the competitive set.',
			mockupEdge: true,
			variants: [
				{ label: 'V1 — Insight Cards', component: RevenueSalesV1 },
				{ label: 'V2 — Revenue Overview Chart', component: RevenueSalesV2 },
				{ label: 'V3 — Channel Breakdown', component: RevenueSalesV3 }
			]
		},
		{
			id: 'marketing-digital',
			title: 'Marketing & Digital',
			desc: 'Where budgets go, which channels drive results, and what tools the market relies on.',
			variants: [
				{ label: 'V1 — Instagram Post', component: MarketingV1, noMockup: false },
				{ label: 'V2 — Spread Cards', component: MarketingV2, noMockup: true },
				{ label: 'V3 — Floating Elements', component: MarketingV4, noMockup: true }
			]
		}
	];
</script>

<svelte:head>
	<title>Mockups — Superextra</title>
</svelte:head>

<div class="min-h-screen bg-[#fefdfb] py-12">
	<div class="mx-auto max-w-[1200px] px-6">
		<header class="mb-12">
			<a href="/" class="text-sm text-black/40 hover:text-black/60 transition-colors">&larr; Back to site</a>
			<h1 class="mt-4 text-3xl font-medium text-black">Card Mockup Variants</h1>
			<p class="mt-2 text-base text-black/50">Compare design directions for each platform card.</p>
		</header>

		{#each cards as card}
			<section class="mb-16">
				<h2 class="text-xl font-medium text-black mb-2">{card.title}</h2>
				<p class="text-sm text-black/50 mb-8">{card.desc}</p>

				<div class="grid grid-cols-1 gap-5 md:grid-cols-3">
					{#each card.variants as variant}
						<div class="card-wrapper">
							<p class="text-xs font-medium text-black/40 mb-3 uppercase tracking-wide">{variant.label}</p>
							<div class="card">
								<div class="card-text">
									<h3 class="title">{card.title}</h3>
									<p class="desc">{card.desc}</p>
								</div>
								{#if ('noMockup' in variant && variant.noMockup) || ('noMockup' in card && card.noMockup)}
									<div class="card-body">
										<variant.component />
									</div>
								{:else}
									<div class="mockup" class:mockup-edge={card.mockupEdge}>
										<variant.component />
									</div>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			</section>
		{/each}
	</div>
</div>

<style>
	.card-wrapper {
		display: flex;
		flex-direction: column;
	}

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

	.card-body {
		flex: 1;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		margin: 0 -1.75rem;
	}
</style>
