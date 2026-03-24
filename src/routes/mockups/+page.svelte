<script lang="ts">
	import PlatformCard from '$lib/components/PlatformCard.svelte';
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
	import GuestIntelligenceV1 from '$lib/components/mockups/GuestIntelligenceV1.svelte';
	import GuestIntelligenceV2 from '$lib/components/mockups/GuestIntelligenceV2.svelte';
	import GuestIntelligenceV3 from '$lib/components/mockups/GuestIntelligenceV3.svelte';
	import LocationTrafficV1 from '$lib/components/mockups/LocationTrafficV1.svelte';
	import LocationTrafficV2 from '$lib/components/mockups/LocationTrafficV2.svelte';
	import LocationTrafficV3 from '$lib/components/mockups/LocationTrafficV3.svelte';
	import OperationsV1 from '$lib/components/mockups/OperationsV1.svelte';
	import OperationsV2 from '$lib/components/mockups/OperationsV2.svelte';

	type CardMode = 'standard' | 'edge' | 'free';

	interface Variant {
		label: string;
		component: typeof MarketLandscapeV1;
		mockupEdge?: boolean;
		noMockup?: boolean;
	}

	interface Card {
		id: string;
		title: string;
		desc: string;
		mockupEdge?: boolean;
		noMockup?: boolean;
		variants: Variant[];
	}

	const cards: Card[] = [
		{
			id: 'market-landscape',
			title: 'Market Landscape',
			desc: "Restaurant openings and closings, cuisine trends and top-performing venues continuously tracked and benchmarked.",
			variants: [
				{ label: 'V1 — Line Chart + Activity', component: MarketLandscapeV1 },
				{ label: 'V2 — Category Trends', component: MarketLandscapeV2 },
				{ label: 'V3 — Category List + Sparklines', component: MarketLandscapeV3 }
			]
		},
		{
			id: 'menu-pricing',
			title: 'Menu & Pricing',
			desc: 'Trending items, price tracking, competitor menus, delivery markups, and promotional activity across the market.',
			variants: [
				{ label: 'V1 — Insight Cards', component: MenuPricingV1, mockupEdge: true },
				{ label: 'V2 — Item Price Comparison', component: MenuPricingV2 },
				{ label: 'V3 — Burger Price Index', component: MenuPricingV4 }
			]
		},
		{
			id: 'revenue-sales',
			title: 'Revenue & Sales',
			desc: 'Revenue estimates, margin and food cost analysis, seasonality patterns, channel splits, and delivery platform market share.',
			mockupEdge: true,
			variants: [
				{ label: 'V1 — Insight Cards', component: RevenueSalesV1 },
				{ label: 'V2 — Revenue Overview Chart', component: RevenueSalesV2 },
				{ label: 'V3 — Channel Breakdown', component: RevenueSalesV3 }
			]
		},
		{
			id: 'guest-intelligence',
			title: 'Guest Intelligence',
			desc: 'Review sentiment, local guest preferences, tourist vs local mix, and payment method trends, all derived from real guest data.',
			mockupEdge: true,
			variants: [
				{ label: 'V1 — Sentiment Heatmap', component: GuestIntelligenceV1 },
				{ label: 'V2 — Reviewer Profile', component: GuestIntelligenceV2 },
				{ label: 'V3 — Review Insights', component: GuestIntelligenceV3 }
			]
		},
		{
			id: 'location-traffic',
			title: 'Location & Foot Traffic',
			desc: 'Measured and projected foot traffic, demographic profiles, purchasing power, and visit time distribution.',
			variants: [
				{ label: 'V1 — Heat Map Grid', component: LocationTrafficV1 },
				{ label: 'V2 — Daily Patterns', component: LocationTrafficV2, mockupEdge: true },
				{ label: 'V3 — Traffic Heatmap', component: LocationTrafficV3, mockupEdge: true }
			]
		},
		{
			id: 'operations',
			title: 'Operations',
			desc: 'Labor pool availability, salary benchmarks, job market activity, staff turnover, commercial rent, and supplier pricing.',
			variants: [
				{ label: 'V1 — Workforce', component: OperationsV1 },
				{ label: 'V2 — Supplier Costs', component: OperationsV2 }
			]
		},
		{
			id: 'marketing-digital',
			title: 'Marketing & Digital',
			desc: 'Social media activity, marketing channels, estimated ad spend, and tools and platforms in use across competitors.',
			variants: [
				{ label: 'V1 — Instagram Post', component: MarketingV1, noMockup: false },
				{ label: 'V2 — Spread Cards', component: MarketingV2, noMockup: true },
				{ label: 'V3 — Floating Elements', component: MarketingV4, noMockup: true }
			]
		}
	];

	function variantMode(card: Card, variant: Variant): CardMode {
		if (variant.noMockup || card.noMockup) return 'free';
		if (variant.mockupEdge ?? card.mockupEdge) return 'edge';
		return 'standard';
	}
</script>

<svelte:head>
	<title>Mockups — Superextra</title>
</svelte:head>

<div class="min-h-screen bg-cream py-12">
	<div class="mx-auto max-w-[1200px] px-6">
		<header class="mb-12">
			<a href="/" class="text-sm text-black/40 dark:text-white/40 hover:text-black/60 dark:hover:text-white/60 transition-colors">&larr; Back to site</a>
			<h1 class="mt-4 text-3xl font-medium text-black dark:text-white">Card Mockup Variants</h1>
			<p class="mt-2 text-base text-black/50 dark:text-white/50">Compare design directions for each platform card.</p>
		</header>

		{#each cards as card}
			<section class="mb-16">
				<h2 class="text-xl font-medium text-black dark:text-white mb-2">{card.title}</h2>
				<p class="text-sm text-black/50 dark:text-white/50 mb-8">{card.desc}</p>

				<div class="grid grid-cols-1 gap-5 md:grid-cols-3">
					{#each card.variants as variant}
						<div class="card-wrapper">
							<p class="text-xs font-medium text-black/40 dark:text-white/40 mb-3 uppercase tracking-wide">{variant.label}</p>
							<PlatformCard title={card.title} desc={card.desc} mode={variantMode(card, variant)}>
								<variant.component />
							</PlatformCard>
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
</style>
