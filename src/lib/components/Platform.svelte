<script lang="ts">
	import { fade } from 'svelte/transition';
	import HeroCanvas from './HeroCanvas.svelte';

	const categories = [
		{
			title: 'Market Landscape',
			description:
				'Restaurant openings and closings, cuisine trends, competitor benchmarking, and top-performing venues — continuously tracked across the market.',
			features: ['Openings & Closings', 'Cuisine Trends', 'Competitor Ranking', 'Best-Sellers', 'Market Distribution']
		},
		{
			title: 'Menu & Pricing',
			description:
				'Trending items, price tracking, competitor menus, delivery markups, and promotional activity across the market.',
			features: ['Trending Items', 'Price Tracking', 'Competitor Menus', 'Delivery Markups', 'Deals & Promos']
		},
		{
			title: 'Revenue & Sales',
			description:
				'Revenue estimates, margin and food cost analysis, seasonality patterns, channel splits, and delivery platform market share.',
			features: ['Revenue Estimates', 'Seasonality', 'Channel Split', 'Occupancy', 'Platform Market Share']
		},
		{
			title: 'Marketing & Digital',
			description:
				'Social media activity, marketing channels, estimated ad spend, and tools and platforms in use across competitors.',
			features: ['Social Media', 'Ad Spend', 'Marketing Channels', 'Tools & Platforms']
		},
		{
			title: 'Guest Intelligence',
			description:
				'Review sentiment, local guest preferences, tourist vs local mix, and payment method trends, all derived from real guest data.',
			features: ['Review Sentiment', 'Guest Preferences', 'Tourist vs Local', 'Payment Methods']
		},
		{
			title: 'Location & Foot Traffic',
			description:
				'Measured and projected foot traffic, demographic profiles, purchasing power, and visit time distribution.',
			features: ['Foot Traffic', 'Projections', 'Demographics', 'Purchasing Power', 'Visit Patterns']
		},
		{
			title: 'Operations',
			description:
				'Labor pool availability, salary benchmarks, job market activity, staff turnover, commercial rent, and supplier pricing.',
			features: ['Labor Availability', 'Salaries', 'Turnover', 'Rent Trends', 'Supplier Pricing']
		}
	];

	const panelImages = [
		'/landscape.webp',
		'/menu.webp',
		'/revenue.webp',
		'/marketing.webp',
		'/guest.webp',
		'/location.webp',
		'/ops.webp'
	];

	let activeIndex = $state(0);
	let mobileOpen = $state(new Set<number>([0]));
	$effect(() => {
		panelImages.forEach((src) => {
			const img = new Image();
			img.src = src;
		});
	});
</script>

<section id="platform" class="border-t border-gray-200 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<p class="mb-6 text-sm font-medium uppercase tracking-widest text-black/40">
			Extra Clarity
		</p>
		<h2 class="mb-4 max-w-2xl text-[clamp(2rem,4vw,3.25rem)] leading-[1.1] font-normal tracking-[-0.02em] text-black">
			Data and insights behind every restaurant decision
		</h2>
		<p class="mb-16 max-w-lg text-lg text-black/60">
			Seven intelligence layers, one platform. Built for every decision a restaurant makes.
		</p>

		<div class="grid grid-cols-1 gap-10 lg:grid-cols-[1fr_1.1fr] lg:items-start lg:gap-16">
			<div class="divide-y divide-gray-200 border-t border-gray-200">
				{#each categories as category, i}
					<button
						class="group w-full cursor-pointer text-left"
						onclick={() => {
						activeIndex = i;
						if (mobileOpen.has(i)) {
							mobileOpen.delete(i);
						} else {
							mobileOpen.add(i);
						}
						mobileOpen = new Set(mobileOpen);
					}}
					>
						<div class="flex items-center justify-between py-5">
							<h3 class="text-base font-semibold transition-colors
								{mobileOpen.has(i) ? 'max-lg:text-black' : 'text-black/40 group-hover:text-black'}
								{activeIndex === i ? 'lg:text-black' : 'lg:text-black/40 lg:group-hover:text-black'}">
								{category.title}
							</h3>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								class="h-5 w-5 shrink-0 text-black/25 transition-transform duration-300
									{mobileOpen.has(i) ? 'rotate-180 lg:rotate-0' : ''}
									{activeIndex === i ? 'lg:rotate-180' : ''}"
								fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"
							>
								<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
							</svg>
						</div>

						<div class="pb-6
							{mobileOpen.has(i) ? '' : 'max-lg:hidden'}
							{activeIndex === i ? '' : 'lg:hidden'}">
							<p class="mb-4 text-sm leading-snug text-black/60">
								{category.description}
							</p>
							<div class="flex flex-wrap gap-2">
								{#each category.features as feature}
									<span class="rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-black/60">{feature}</span>
								{/each}
							</div>
							<div class="mt-4 max-w-sm overflow-hidden rounded-xl lg:hidden">
								<img src={panelImages[i]} alt={category.title} class="w-full" />
							</div>
						</div>
					</button>
				{/each}
			</div>

			<div class="hidden lg:block relative aspect-[1940/1799] rounded-2xl overflow-hidden">
				<HeroCanvas class="absolute inset-0 w-full h-full" width={580} height={540} />
				<img src="/container-empty.png" alt="" class="absolute bottom-0 right-0 w-[93%]" />
				{#key activeIndex}
				<div class="absolute bottom-0 right-0 w-[93%]" in:fade={{ duration: 400, delay: 100 }} out:fade={{ duration: 300 }}>
					<img src={panelImages[activeIndex]} alt={categories[activeIndex].title} class="w-full" />
				</div>
				{/key}
			</div>
		</div>
	</div>
</section>
