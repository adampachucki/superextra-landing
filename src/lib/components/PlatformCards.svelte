<script lang="ts">
	import SectionHeader from './SectionHeader.svelte';
	import PlatformCard from './PlatformCard.svelte';
	import MarketLandscapeV3 from './mockups/MarketLandscapeV3.svelte';
	import MarketLandscapeWideV1 from './mockups/MarketLandscapeWideV1.svelte';
	import MenuPricingV1 from './mockups/MenuPricingV1.svelte';
	import RevenueSalesV2 from './mockups/RevenueSalesV2.svelte';
	import MarketingV2 from './mockups/MarketingV2.svelte';
	import GuestIntelligenceV2 from './mockups/GuestIntelligenceV2.svelte';
	import LocationTrafficV1 from './mockups/LocationTrafficV1.svelte';
	import OperationsV1 from './mockups/OperationsV1.svelte';

	let expanded = $state(false);
</script>

<section id="intelligence" class="border-t border-cream-200 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<SectionHeader subtitle="Extra Clarity" title="Data and insights behind every restaurant decision" titleClass="mb-4 max-w-2xl" />
		<p class="mb-16 max-w-lg text-lg text-black/60">
			Seven intelligence layers, combined.
		</p>

		<div class="grid grid-cols-1 gap-5 md:grid-cols-[repeat(auto-fill,minmax(18rem,1fr))]">

			<PlatformCard title="Market Landscape" desc="Restaurant openings and closings, cuisine trends and top-performing venues continuously tracked and benchmarked. With deep narrative reports that turn raw signals into actionable insights." wide mode="edge">
				<MarketLandscapeWideV1 />
			</PlatformCard>

			<!-- <PlatformCard title="Market Landscape" desc="Restaurant openings and closings, cuisine trends, competitor benchmarking, and top-performing venues — continuously tracked across the market.">
				<MarketLandscapeV3 />
			</PlatformCard> -->

			<PlatformCard title="Menu & Pricing" desc="Trending items, price tracking, competitor menus, delivery markups, and promotional activity across the market.">
				<MenuPricingV1 />
			</PlatformCard>

			<PlatformCard title="Revenue & Sales" desc="Revenue estimates, margin and food cost analysis, seasonality patterns, channel splits, and delivery platform markups." mode="edge">
				<RevenueSalesV2 />
			</PlatformCard>

			<PlatformCard title="Marketing & Digital" desc="Social media activity, marketing channels, estimated ad spend, and tools and platforms in use across competitors." mode="free">
				<MarketingV2 />
			</PlatformCard>

			<PlatformCard title="Guest Intelligence" desc="Review sentiment, local guest preferences, tourist vs local mix, and payment method trends, all derived from real guest data." mode="edge">
				<GuestIntelligenceV2 />
			</PlatformCard>

		</div>

		<div class="mt-5 grid grid-cols-1 gap-5 overflow-hidden transition-all duration-500 ease-out md:grid-cols-[repeat(auto-fill,minmax(18rem,1fr))]"
			class:max-h-0={!expanded}
			class:max-h-[55rem]={expanded}
			class:md:max-h-[40rem]={expanded}
			class:opacity-0={!expanded}
			class:opacity-100={expanded}
			class:mt-0={!expanded}
		>
			<PlatformCard title="Location & Foot Traffic" desc="Measured and projected foot traffic, demographic profiles, purchasing power, and visit time distribution." mode="free">
				<LocationTrafficV1 />
			</PlatformCard>

			<PlatformCard title="Operations" desc="Labor pool availability, salary benchmarks, job market activity, staff turnover, commercial rent, and supplier pricing.">
				<OperationsV1 />
			</PlatformCard>
		</div>

		<div class="mt-10 flex justify-center">
			<button
				onclick={() => expanded = !expanded}
				class="cursor-pointer rounded-full border border-black/10 px-6 py-2.5 text-sm font-medium text-black/70 transition-all hover:border-black/15 hover:text-black/90"
			>
				{expanded ? 'Show less' : 'Show more'}
			</button>
		</div>
	</div>
</section>
