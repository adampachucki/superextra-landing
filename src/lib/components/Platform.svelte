<script lang="ts">
	const categories = [
		{
			title: 'Market & Competition',
			description:
				'Track restaurant openings and closings in real time. Assess closure risk, benchmark against competitors, and spot emerging cuisine trends. Identify market saturation and white space opportunities before anyone else.',
			features: ['Openings & Closings', 'Closure Risk', 'Competitor Benchmarking', 'Cuisine Trends', 'Market Saturation', 'White Space Mapping']
		},
		{
			title: 'Guest & Location',
			description:
				'Understand who your guests are and how they find you. Analyze review sentiment at scale, measure foot traffic patterns, map trade areas, and break down tourist vs. local mix to optimize your positioning.',
			features: ['Review Sentiment', 'Foot Traffic', 'Demographics', 'Trade Areas', 'Tourist vs Local Mix', 'Location Scoring']
		},
		{
			title: 'Menu & Pricing',
			description:
				'Know what to serve and what to charge. Track trending menu items across your market, monitor competitor pricing and positioning, analyze delivery markups, and stay ahead of dietary trend shifts.',
			features: ['Trending Items', 'Price Tracking', 'Competitor Menus', 'Delivery Markups', 'Dietary Trends', 'Price Positioning']
		},
		{
			title: 'Revenue & Financials',
			description:
				'See the numbers that matter. Get revenue estimates, average check size benchmarks, RevPAS calculations, occupancy rates, and food/labor cost comparisons — all benchmarked against your competitive set.',
			features: ['Revenue Estimates', 'Check Size', 'RevPAS', 'Occupancy', 'Food & Labor Costs', 'Margin Analysis']
		},
		{
			title: 'Delivery & Digital',
			description:
				'Master the digital landscape. Track platform market share across UberEats, DoorDash, and more. Monitor dynamic pricing, digital ordering adoption, social media performance, and competitor marketing spend.',
			features: ['Platform Market Share', 'Dynamic Pricing', 'Digital Ordering', 'Social Media', 'Marketing Spend', 'Delivery Analytics']
		},
		{
			title: 'Operations',
			description:
				'Optimize every operational lever. Understand workforce availability and labor costs in your market, evaluate real estate comps and opportunities, and track supply chain pricing shifts.',
			features: ['Workforce Availability', 'Labor Costs', 'Real Estate', 'Supply Chain Pricing', 'Operational Benchmarks', 'Cost Analysis']
		},
		{
			title: 'Research & Tools',
			description:
				'Go deeper with curated industry reports, custom research, and AI-powered market analysis agents that answer your most complex questions in seconds.',
			features: ['Report Library', 'AI Market Agents', 'Custom Analysis', 'Industry Research', 'Trend Reports', 'Market Briefs']
		}
	];

	let activeIndex = $state(0);
</script>

<section id="platform" class="border-t border-gray-200 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<p class="mb-6 text-sm font-medium uppercase tracking-widest text-black/40">
			Platform
		</p>
		<h2 class="mb-4 max-w-xl text-[clamp(2rem,4vw,3.25rem)] leading-[1.1] font-normal tracking-[-0.02em] text-black">
			Everything you need to understand your market
		</h2>
		<p class="mb-16 max-w-lg text-lg text-black/50">
			Seven intelligence layers, one platform. Built for every decision a restaurant makes.
		</p>

		<div class="grid grid-cols-1 gap-10 lg:grid-cols-[1fr_1.1fr] lg:gap-16">
			<!-- Accordion -->
			<div class="divide-y divide-gray-200 border-t border-gray-200">
				{#each categories as category, i}
					<button
						class="group w-full cursor-pointer text-left"
						onclick={() => (activeIndex = activeIndex === i ? -1 : i)}
					>
						<div class="flex items-center justify-between py-5">
							<h3 class="text-base font-semibold transition-colors {activeIndex === i ? 'text-black' : 'text-black/40 group-hover:text-black'}">
								{category.title}
							</h3>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								class="h-5 w-5 shrink-0 text-black/30 transition-transform duration-300 {activeIndex === i ? 'rotate-180' : ''}"
								fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"
							>
								<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
							</svg>
						</div>

						{#if activeIndex === i}
							<div class="pb-6">
								<p class="mb-4 text-sm leading-normal text-black/50">
									{category.description}
								</p>
								<div class="flex flex-wrap gap-2">
									{#each category.features as feature}
										<span class="rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-black/60">{feature}</span>
									{/each}
								</div>
							</div>
						{/if}
					</button>
				{/each}
			</div>

			<!-- Visual panel -->
			<div class="flex items-start justify-center">
				<div class="w-full overflow-hidden rounded-2xl bg-gray-50 border border-gray-200">
					<div class="relative aspect-[4/3] w-full p-8 md:p-10">
						{#if activeIndex >= 0}
							<div class="flex h-full flex-col justify-between">
								<div>
									<p class="mb-1 text-xs font-medium uppercase tracking-widest text-black/30">
										{categories[activeIndex].title}
									</p>
									<h3 class="text-2xl font-bold text-black">
										{categories[activeIndex].title}
									</h3>
								</div>

								<div class="space-y-3">
									{#each categories[activeIndex].features as feature, j}
										<div class="flex items-center gap-4">
											<span class="w-32 shrink-0 text-xs text-black/40">{feature}</span>
											<div class="h-2 flex-1 overflow-hidden rounded-full bg-gray-200">
												<div
													class="h-full rounded-full bg-black transition-all duration-700 ease-out"
													style="width: {90 - j * 12 + Math.sin(j * 2) * 5}%"
												></div>
											</div>
										</div>
									{/each}
								</div>

								<div class="flex items-center justify-between border-t border-gray-200 pt-4">
									<span class="text-xs text-black/30">{categories[activeIndex].features.length} metrics tracked</span>
									<span class="rounded-full bg-black px-3 py-1 text-xs font-medium text-white">Live Data</span>
								</div>
							</div>
						{:else}
							<div class="flex h-full items-center justify-center text-sm text-black/30">
								Click a category to explore
							</div>
						{/if}
					</div>
				</div>
			</div>
		</div>
	</div>
</section>
