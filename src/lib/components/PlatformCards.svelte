<script lang="ts">
	import SectionHeader from './SectionHeader.svelte';
	import PlatformCard from './PlatformCard.svelte';
	import MarketLandscapeWideV1 from './mockups/MarketLandscapeWideV1.svelte';
	import MenuPricingV1 from './mockups/MenuPricingV1.svelte';
	import RevenueSalesV2 from './mockups/RevenueSalesV2.svelte';
	import MarketingV2 from './mockups/MarketingV2.svelte';
	import GuestIntelligenceV2 from './mockups/GuestIntelligenceV2.svelte';
	import LocationTrafficV1 from './mockups/LocationTrafficV1.svelte';
	import OperationsV1 from './mockups/OperationsV1.svelte';
	import * as m from '$lib/paraglide/messages';

	let expanded = $state(false);
</script>

<section id="intelligence" class="border-t border-cream-200 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<SectionHeader subtitle={m.pc_subtitle()} title={m.pc_title()} titleClass="mb-4 max-w-2xl" />
		<p class="mb-16 max-w-lg text-lg text-black/60 dark:text-white/60">
			{m.pc_lead()}
		</p>

		<div class="relative grid grid-cols-1 md:grid-cols-3" class:cards-grid={!expanded}>
			<PlatformCard title={m.pc_market_title()} desc={m.pc_market_desc()} wide>
				<MarketLandscapeWideV1 />
			</PlatformCard>

			<!-- <PlatformCard title="Market Landscape" desc="Restaurant openings and closings, cuisine trends, competitor benchmarking, and top-performing venues — continuously tracked across the market.">
				<MarketLandscapeV3 />
			</PlatformCard> -->

			<PlatformCard title={m.pc_menu_title()} desc={m.pc_menu_desc()} separator>
				<MenuPricingV1 />
			</PlatformCard>

			<PlatformCard title={m.pc_revenue_title()} desc={m.pc_revenue_desc()} mode="edge">
				<RevenueSalesV2 />
			</PlatformCard>

			<PlatformCard title={m.pc_guest_title()} desc={m.pc_guest_desc()} mode="edge" separator>
				<GuestIntelligenceV2 />
			</PlatformCard>

			<PlatformCard title={m.pc_ops_title()} desc={m.pc_ops_desc()} separator>
				<OperationsV1 />
			</PlatformCard>
		</div>

		<div
			class="relative grid grid-cols-1 overflow-hidden transition-all duration-500 ease-out md:grid-cols-3"
			class:max-h-0={!expanded}
			class:max-h-[55rem]={expanded}
			class:md:max-h-[40rem]={expanded}
			class:opacity-0={!expanded}
			class:opacity-100={expanded}
		>
			<PlatformCard title={m.pc_location_title()} desc={m.pc_location_desc()} mode="free">
				<LocationTrafficV1 />
			</PlatformCard>

			<PlatformCard
				title={m.pc_marketing_title()}
				desc={m.pc_marketing_desc()}
				mode="free"
				separator
			>
				<MarketingV2 />
			</PlatformCard>

			<div class="border-t border-l border-cream-200 max-md:hidden"></div>
		</div>

		<div class="mt-10 flex justify-center">
			<button onclick={() => (expanded = !expanded)} class="btn-ghost px-6 py-2.5">
				{expanded ? m.pc_show_less() : m.pc_show_more()}
			</button>
		</div>
	</div>
</section>

<style>
	@media (min-width: 768px) {
		.cards-grid::after {
			content: '';
			position: absolute;
			left: 0;
			right: 0;
			bottom: 0;
			height: 3.5rem;
			background: linear-gradient(
				to bottom,
				transparent,
				color-mix(in srgb, var(--color-cream) 80%, transparent)
			);
			pointer-events: none;
			z-index: 1;
		}
	}
</style>
