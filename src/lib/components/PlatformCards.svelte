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
</script>

<section id="platform" class="border-t border-cream-200 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<SectionHeader subtitle="Extra Clarity" title="Data and insights behind every restaurant decision" titleClass="mb-4 max-w-2xl" />
		<p class="mb-16 max-w-lg text-lg text-black/60">
			Seven intelligence layers, one platform. Built for every decision a restaurant makes.
		</p>

		<div class="grid grid-cols-1 gap-5 md:grid-cols-3">

			<PlatformCard title="Market Landscape" desc="Restaurant openings and closings, cuisine trends, competitor benchmarking, and top-performing venues — continuously tracked across the market. Deep narrative reports that turn raw signals into actionable insights." wide mode="edge">
				<MarketLandscapeWideV1 />
			</PlatformCard>

			<PlatformCard title="Market Landscape" desc="Restaurant openings and closings, cuisine trends, competitor benchmarking, and top-performing venues — continuously tracked across the market.">
				<MarketLandscapeV3 />
			</PlatformCard>

			<PlatformCard title="Menu & Pricing" desc="Trending items, price tracking, competitor menus, delivery markups, and promotional activity across the market." mode="edge">
				<MenuPricingV1 />
			</PlatformCard>

			<PlatformCard title="Revenue & Sales" desc="Revenue estimates, margin and food cost analysis, seasonality patterns, channel splits, and delivery platform market share." mode="edge">
				<RevenueSalesV2 />
			</PlatformCard>

			<PlatformCard title="Marketing & Digital" desc="Social media activity, marketing channels, estimated ad spend, and tools and platforms in use across competitors." mode="free">
				<MarketingV2 />
			</PlatformCard>

			<PlatformCard title="Guest Intelligence" desc="Review sentiment, local guest preferences, tourist vs local mix, and payment method trends, all derived from real guest data." mode="edge">
				<GuestIntelligenceV2 />
			</PlatformCard>

			<PlatformCard title="Location & Foot Traffic" desc="Measured and projected foot traffic, demographic profiles, purchasing power, and visit time distribution.">
				<LocationTrafficV1 />
			</PlatformCard>

			<PlatformCard title="Operations" desc="Labor pool availability, salary benchmarks, job market activity, staff turnover, commercial rent, and supplier pricing.">
				<OperationsV1 />
			</PlatformCard>

		</div>
	</div>
</section>
