<script lang="ts">
	const categories = [
		{
			title: 'Market & Competition',
			description:
				'Track restaurant openings and closings in real time. Assess closure risk, benchmark against competitors, and spot emerging cuisine trends.',
			features: ['Openings & Closings', 'Closure Risk', 'Competitor Benchmarking', 'Cuisine Trends', 'Market Saturation', 'White Space Mapping']
		},
		{
			title: 'Guest & Location',
			description:
				'Understand who your guests are and how they find you. Analyze review sentiment, measure foot traffic, and map trade areas to optimize positioning.',
			features: ['Review Sentiment', 'Foot Traffic', 'Demographics', 'Trade Areas', 'Tourist vs Local Mix', 'Location Scoring']
		},
		{
			title: 'Menu & Pricing',
			description:
				'Know what to serve and what to charge. Track trending items, monitor competitor pricing, analyze delivery markups, and spot dietary trend shifts.',
			features: ['Trending Items', 'Price Tracking', 'Competitor Menus', 'Delivery Markups', 'Dietary Trends', 'Price Positioning']
		},
		{
			title: 'Revenue & Financials',
			description:
				'See the numbers that matter. Revenue estimates, check sizes, RevPAS, occupancy rates, and cost benchmarks — all compared to your competitive set.',
			features: ['Revenue Estimates', 'Check Size', 'RevPAS', 'Occupancy', 'Food & Labor Costs', 'Margin Analysis']
		},
		{
			title: 'Delivery & Digital',
			description:
				'Master the digital landscape. Track platform market share, monitor dynamic pricing, and analyze social media performance across your market.',
			features: ['Platform Market Share', 'Dynamic Pricing', 'Digital Ordering', 'Social Media', 'Marketing Spend', 'Delivery Analytics']
		},
		{
			title: 'Operations',
			description:
				'Optimize every operational lever. Understand workforce availability, evaluate real estate opportunities, and track supply chain pricing shifts.',
			features: ['Workforce Availability', 'Labor Costs', 'Real Estate', 'Supply Chain Pricing', 'Operational Benchmarks', 'Cost Analysis']
		},
		{
			title: 'Research & Tools',
			description:
				'Go deeper with curated industry reports, AI-driven market analysis agents, and custom research that answers complex questions in seconds.',
			features: ['Report Library', 'AI Market Agents', 'Custom Analysis', 'Industry Research', 'Trend Reports', 'Market Briefs']
		}
	];

	let activeIndex = $state(0);
</script>

<section id="platform" class="border-t border-gray-200 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<p class="mb-6 text-sm font-medium uppercase tracking-widest text-black/40">
			Extra Clarity
		</p>
		<h2 class="mb-4 max-w-2xl text-[clamp(2rem,4vw,3.25rem)] leading-[1.1] font-normal tracking-[-0.02em] text-black">
			The intelligence behind every restaurant decision
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
						onclick={() => (activeIndex = i)}
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
								<p class="mb-4 text-sm leading-snug text-black/50">
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
			<div class="hidden lg:flex items-start justify-center">
				<div class="w-full overflow-hidden rounded-2xl bg-gray-50 border border-gray-200">
					<div class="relative aspect-[4/3] w-full p-8 md:p-10">

						{#if activeIndex === 0}
							<!-- Market & Competition: Activity dashboard -->
							<div class="flex h-full flex-col">
								<p class="mb-4 text-[11px] font-medium uppercase tracking-widest text-black/30">Market Activity — Downtown</p>

								<div class="grid grid-cols-3 gap-3 mb-5">
									<div class="rounded-xl bg-white p-3 border border-gray-100">
										<p class="text-xl font-bold text-emerald-600">+12</p>
										<p class="text-[10px] text-black/40 mt-0.5">Openings</p>
									</div>
									<div class="rounded-xl bg-white p-3 border border-gray-100">
										<p class="text-xl font-bold text-red-500">-4</p>
										<p class="text-[10px] text-black/40 mt-0.5">Closures</p>
									</div>
									<div class="rounded-xl bg-white p-3 border border-gray-100">
										<p class="text-xl font-bold text-black">82<span class="text-sm font-normal text-black/40">%</span></p>
										<p class="text-[10px] text-black/40 mt-0.5">Saturation</p>
									</div>
								</div>

								<!-- Net monthly openings chart -->
								<div class="mb-5">
									<p class="text-[10px] font-medium text-black/30 mb-2 uppercase tracking-wider">Net Openings — 6 Months</p>
									<div class="flex items-end gap-1.5 h-14">
										{#each [
											{ m: 'Oct', v: 3 },
											{ m: 'Nov', v: 5 },
											{ m: 'Dec', v: -1 },
											{ m: 'Jan', v: 2 },
											{ m: 'Feb', v: 6 },
											{ m: 'Mar', v: 8 }
										] as bar}
											<div class="flex-1 flex flex-col items-center gap-0.5">
												<span class="text-[8px] font-medium tabular-nums {bar.v > 0 ? 'text-emerald-600' : 'text-red-500'}">
													{bar.v > 0 ? '+' : ''}{bar.v}
												</span>
												<div
													class="w-full rounded-t-sm"
													style="height: {Math.max(Math.abs(bar.v) / 8 * 100, 12)}%; background: linear-gradient(to top, {bar.v > 0 ? 'rgb(6,182,212), rgb(110,231,183)' : 'rgb(244,114,182), rgb(251,191,36)'})"
												></div>
												<span class="text-[8px] text-black/25">{bar.m}</span>
											</div>
										{/each}
									</div>
								</div>

								<!-- Cuisine landscape with bars -->
								<div class="flex-1">
									<p class="text-[10px] font-medium text-black/30 mb-2.5 uppercase tracking-wider">Cuisine Landscape</p>
									<div class="space-y-2">
										{#each [
											{ name: 'Korean Fusion', change: '+34%', pct: 88, up: true },
											{ name: 'Mediterranean', change: '+22%', pct: 68, up: true },
											{ name: 'Fast Casual Pizza', change: '+18%', pct: 55, up: true },
											{ name: 'Fine Dining French', change: '-8%', pct: 22, up: false }
										] as item}
											<div>
												<div class="flex items-center justify-between mb-0.5">
													<span class="text-xs text-black/60">{item.name}</span>
													<span class="text-[10px] font-medium {item.up ? 'text-emerald-600' : 'text-red-500'}">{item.change}</span>
												</div>
												<div class="h-1.5 w-full rounded-full bg-gray-100">
													<div class="h-full rounded-full" style="width: {item.pct}%; background: linear-gradient(to right, {item.up ? 'rgb(110,231,183), rgb(167,139,250)' : 'rgb(244,114,182), rgb(251,191,36)'})"></div>
												</div>
											</div>
										{/each}
									</div>
								</div>

								<div class="border-t border-gray-200 pt-3 flex items-center justify-between">
									<div class="flex items-center gap-2">
										<span class="h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
										<span class="text-[10px] text-black/30">Live — updated 2h ago</span>
									</div>
									<span class="text-[10px] font-medium text-black/40">3 white space opportunities</span>
								</div>
							</div>

						{:else if activeIndex === 1}
							<!-- Guest & Location: Sentiment & traffic -->
							<div class="flex h-full flex-col">
								<p class="mb-4 text-[11px] font-medium uppercase tracking-widest text-black/30">Guest Intelligence</p>

								<div class="flex gap-5 mb-5">
									<div class="text-center">
										<p class="text-4xl font-bold text-black">4.6</p>
										<div class="flex gap-0.5 mt-1 justify-center">
											{#each Array(5) as _, i}
												<svg class="h-3.5 w-3.5 {i < 4 ? 'text-amber-400' : 'text-amber-400/40'}" fill="currentColor" viewBox="0 0 20 20">
													<path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
												</svg>
											{/each}
										</div>
										<p class="text-[10px] text-black/30 mt-1">2,847 reviews</p>
									</div>
									<div class="flex-1 space-y-2">
										{#each [
											{ label: 'Positive', pct: 73, grad: 'linear-gradient(to right, rgb(110,231,183), rgb(6,182,212))' },
											{ label: 'Neutral', pct: 19, grad: 'linear-gradient(to right, rgb(180,180,190), rgb(150,150,165))' },
											{ label: 'Negative', pct: 8, grad: 'linear-gradient(to right, rgb(244,114,182), rgb(251,191,36))' }
										] as s}
											<div>
												<div class="flex justify-between mb-0.5">
													<span class="text-[10px] text-black/40">{s.label}</span>
													<span class="text-[10px] font-medium text-black/50">{s.pct}%</span>
												</div>
												<div class="h-1.5 w-full rounded-full bg-gray-100">
													<div class="h-full rounded-full" style="width: {s.pct}%; background: {s.grad}"></div>
												</div>
											</div>
										{/each}
									</div>
								</div>

								<!-- Demographics split -->
								<div class="grid grid-cols-2 gap-3 mb-5">
									<div class="rounded-xl bg-white p-3 border border-gray-100">
										<p class="text-lg font-bold text-black">68<span class="text-xs font-normal text-black/30">%</span></p>
										<p class="text-[10px] text-black/40 mt-0.5">Local residents</p>
									</div>
									<div class="rounded-xl bg-white p-3 border border-gray-100">
										<p class="text-lg font-bold text-black">32<span class="text-xs font-normal text-black/30">%</span></p>
										<p class="text-[10px] text-black/40 mt-0.5">Tourists & visitors</p>
									</div>
								</div>

								<!-- Weekly foot traffic -->
								<div class="flex-1">
									<p class="text-[10px] font-medium text-black/30 mb-2 uppercase tracking-wider">Weekly Foot Traffic</p>
									<div class="flex items-end gap-1.5 h-16">
										{#each [
											{ day: 'Mon', h: 40 },
											{ day: 'Tue', h: 55 },
											{ day: 'Wed', h: 50 },
											{ day: 'Thu', h: 60 },
											{ day: 'Fri', h: 85 },
											{ day: 'Sat', h: 95 },
											{ day: 'Sun', h: 70 }
										] as bar}
											<div class="flex-1 flex flex-col items-center gap-1">
												<span class="text-[8px] font-medium text-black/30">{bar.h}%</span>
												<div class="w-full rounded-t-sm" style="height: {bar.h}%; background: linear-gradient(to top, rgb(99,102,241), rgb(167,139,250))"></div>
												<span class="text-[8px] text-black/25">{bar.day}</span>
											</div>
										{/each}
									</div>
								</div>

								<!-- Top mentioned keywords -->
								<div class="border-t border-gray-200 pt-3 mt-3">
									<p class="text-[10px] font-medium text-black/30 mb-2 uppercase tracking-wider">Top Mentions</p>
									<div class="flex flex-wrap gap-1.5">
										{#each [
											{ word: 'great service', size: 'text-xs' },
											{ word: 'cozy ambiance', size: 'text-[11px]' },
											{ word: 'slow wait', size: 'text-[10px]' },
											{ word: 'fresh ingredients', size: 'text-xs' },
											{ word: 'date night', size: 'text-[11px]' },
											{ word: 'parking', size: 'text-[10px]' }
										] as tag}
											<span class="rounded-full bg-white border border-gray-100 px-2 py-0.5 {tag.size} text-black/50">{tag.word}</span>
										{/each}
									</div>
								</div>
							</div>

						{:else if activeIndex === 2}
							<!-- Menu & Pricing: Trending items table -->
							<div class="flex h-full flex-col">
								<p class="mb-5 text-[11px] font-medium uppercase tracking-widest text-black/30">Menu Intelligence</p>

								<div class="rounded-xl bg-white border border-gray-100 overflow-hidden flex-1">
									<div class="grid grid-cols-[1fr_auto_auto] gap-x-4 px-4 py-2 border-b border-gray-100 text-[10px] font-medium uppercase tracking-wider text-black/30">
										<span>Item</span>
										<span>Avg Price</span>
										<span>Trend</span>
									</div>
									{#each [
										{ item: 'Smash Burger', price: '$18', trend: '+12%', up: true, hot: true },
										{ item: 'Matcha Latte', price: '$7', trend: '+28%', up: true, hot: true },
										{ item: 'Birria Tacos', price: '$16', trend: '+15%', up: true, hot: false },
										{ item: 'Caesar Salad', price: '$14', trend: '+3%', up: true, hot: false },
										{ item: 'Wagyu Steak', price: '$62', trend: '-5%', up: false, hot: false },
										{ item: 'Açaí Bowl', price: '$15', trend: '-11%', up: false, hot: false }
									] as row}
										<div class="grid grid-cols-[1fr_auto_auto] gap-x-4 items-center px-4 py-2.5 border-b border-gray-50 last:border-0">
											<span class="text-sm text-black/70 flex items-center gap-2">
												{row.item}
												{#if row.hot}
													<span class="rounded bg-orange-100 px-1.5 py-0.5 text-[9px] font-bold text-orange-600">HOT</span>
												{/if}
											</span>
											<span class="text-sm text-black/50 tabular-nums">{row.price}</span>
											<span class="text-xs font-medium tabular-nums {row.up ? 'text-emerald-600' : 'text-red-500'}">{row.trend}</span>
										</div>
									{/each}
								</div>

								<div class="border-t border-gray-200 pt-3 mt-4">
									<span class="text-[10px] text-black/30">Based on 1,240 menus in your market</span>
								</div>
							</div>

						{:else if activeIndex === 3}
							<!-- Revenue & Financials: KPI grid -->
							<div class="flex h-full flex-col">
								<p class="mb-5 text-[11px] font-medium uppercase tracking-widest text-black/30">Financial Benchmarks</p>

								<div class="grid grid-cols-2 gap-3 flex-1">
									{#each [
										{ value: '$1.2M', label: 'Avg Revenue', sub: 'per location / yr', change: '+8%', up: true },
										{ value: '$47', label: 'Avg Check', sub: 'dinner service', change: '+3%', up: true },
										{ value: '$892', label: 'RevPAS', sub: 'revenue per sqft', change: '+12%', up: true },
										{ value: '78%', label: 'Occupancy', sub: 'prime hours', change: '-2%', up: false }
									] as kpi}
										<div class="rounded-xl bg-white p-4 border border-gray-100 flex flex-col justify-between">
											<div>
												<p class="text-2xl font-bold text-black leading-none">{kpi.value}</p>
												<p class="text-[11px] text-black/50 mt-1">{kpi.label}</p>
												<p class="text-[9px] text-black/25">{kpi.sub}</p>
											</div>
											<span class="text-[10px] font-medium {kpi.up ? 'text-emerald-600' : 'text-red-500'} mt-2">{kpi.change} vs market</span>
										</div>
									{/each}
								</div>

								<div class="border-t border-gray-200 pt-3 mt-4 flex justify-between">
									<span class="text-[10px] text-black/30">Comp set: 24 restaurants</span>
									<span class="text-[10px] text-black/30">Q4 2025</span>
								</div>
							</div>

						{:else if activeIndex === 4}
							<!-- Delivery & Digital: Platform market share -->
							<div class="flex h-full flex-col">
								<p class="mb-5 text-[11px] font-medium uppercase tracking-widest text-black/30">Digital Landscape</p>

								<div class="mb-6">
									<div class="flex rounded-lg overflow-hidden h-8 mb-3">
										<div class="bg-[#06C167] flex items-center justify-center" style="width: 38%">
											<span class="text-[10px] font-bold text-white">38%</span>
										</div>
										<div class="bg-[#FF3008] flex items-center justify-center" style="width: 34%">
											<span class="text-[10px] font-bold text-white">34%</span>
										</div>
										<div class="bg-[#F63440] flex items-center justify-center" style="width: 18%">
											<span class="text-[10px] font-bold text-white">18%</span>
										</div>
										<div class="bg-black flex items-center justify-center" style="width: 10%">
											<span class="text-[10px] font-bold text-white">10%</span>
										</div>
									</div>
									<div class="flex gap-4 text-[10px]">
										<span class="flex items-center gap-1.5"><span class="h-2 w-2 rounded-full bg-[#06C167]"></span> UberEats</span>
										<span class="flex items-center gap-1.5"><span class="h-2 w-2 rounded-full bg-[#FF3008]"></span> DoorDash</span>
										<span class="flex items-center gap-1.5"><span class="h-2 w-2 rounded-full bg-[#F63440]"></span> GrubHub</span>
										<span class="flex items-center gap-1.5"><span class="h-2 w-2 rounded-full bg-black"></span> Direct</span>
									</div>
								</div>

								<div class="flex-1 space-y-3">
									{#each [
										{ label: 'Digital Order Rate', value: '34%', bar: 34 },
										{ label: 'Avg Delivery Markup', value: '22%', bar: 22 },
										{ label: 'Social Engagement', value: '4.2x', bar: 70 }
									] as metric}
										<div class="rounded-xl bg-white p-3.5 border border-gray-100">
											<div class="flex justify-between mb-1.5">
												<span class="text-[11px] text-black/50">{metric.label}</span>
												<span class="text-sm font-semibold text-black">{metric.value}</span>
											</div>
											<div class="h-1 w-full rounded-full bg-gray-100">
												<div class="h-full rounded-full" style="width: {metric.bar}%; background: linear-gradient(to right, rgb(99,102,241), rgb(167,139,250))"></div>
											</div>
										</div>
									{/each}
								</div>

								<div class="border-t border-gray-200 pt-3 mt-4">
									<span class="text-[10px] text-black/30">Your market: 2.4M monthly delivery orders</span>
								</div>
							</div>

						{:else if activeIndex === 5}
							<!-- Operations: Cost & workforce metrics -->
							<div class="flex h-full flex-col">
								<p class="mb-5 text-[11px] font-medium uppercase tracking-widest text-black/30">Operational Overview</p>

								<div class="grid grid-cols-2 gap-3 mb-5">
									<div class="rounded-xl bg-white p-4 border border-gray-100">
										<div class="flex items-end gap-1 mb-1">
											<span class="text-3xl font-bold text-black leading-none">32</span>
											<span class="text-sm text-black/30 mb-0.5">%</span>
										</div>
										<p class="text-[10px] text-black/40">Labor cost index</p>
									</div>
									<div class="rounded-xl bg-white p-4 border border-gray-100">
										<div class="flex items-end gap-1 mb-1">
											<span class="text-sm text-black/30 mb-0.5">$</span>
											<span class="text-3xl font-bold text-black leading-none">85</span>
											<span class="text-sm text-black/30 mb-0.5">/sqft</span>
										</div>
										<p class="text-[10px] text-black/40">Avg rent</p>
									</div>
								</div>

								<div class="flex-1 space-y-3">
									{#each [
										{ label: 'Workforce Availability', score: 'Moderate', pct: 55, grad: 'linear-gradient(to right, rgb(251,191,36), rgb(244,114,182))' },
										{ label: 'Supply Chain Stability', score: 'Strong', pct: 82, grad: 'linear-gradient(to right, rgb(110,231,183), rgb(6,182,212))' },
										{ label: 'Real Estate Supply', score: 'Tight', pct: 28, grad: 'linear-gradient(to right, rgb(244,114,182), rgb(167,139,250))' }
									] as op}
										<div>
											<div class="flex justify-between mb-1">
												<span class="text-[11px] text-black/50">{op.label}</span>
												<span class="text-[10px] font-medium text-black/40">{op.score}</span>
											</div>
											<div class="h-2 w-full rounded-full bg-gray-100">
												<div class="h-full rounded-full" style="width: {op.pct}%; background: {op.grad}"></div>
											</div>
										</div>
									{/each}
								</div>

								<div class="border-t border-gray-200 pt-3 mt-4">
									<span class="text-[10px] text-black/30">Market avg — your zip code</span>
								</div>
							</div>

						{:else if activeIndex === 6}
							<!-- Research & Tools: AI assistant preview -->
							<div class="flex h-full flex-col">
								<p class="mb-5 text-[11px] font-medium uppercase tracking-widest text-black/30">AI Research Agent</p>

								<div class="flex-1 rounded-xl bg-white border border-gray-100 p-4 flex flex-col">
									<div class="flex-1 space-y-4">
										<div class="flex justify-end">
											<div class="rounded-2xl rounded-br-md bg-black px-4 py-2.5 max-w-[80%]">
												<p class="text-sm text-white">What cuisines are underrepresented in Williamsburg?</p>
											</div>
										</div>

										<div class="flex justify-start">
											<div class="rounded-2xl rounded-bl-md bg-gray-100 px-4 py-3 max-w-[85%]">
												<p class="text-sm text-black/70 leading-relaxed">Based on analysis of 847 restaurants within 2mi:</p>
												<div class="mt-2 space-y-1.5">
													{#each [
														{ cuisine: 'Ethiopian', gap: 'High demand, 0 locations' },
														{ cuisine: 'Peruvian', gap: 'Growing 40%, only 2 spots' },
														{ cuisine: 'Georgian', gap: 'Trending in similar markets' }
													] as rec}
														<div class="flex items-start gap-2">
															<span class="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-black/40"></span>
															<p class="text-[12px] text-black/60"><strong class="text-black/80">{rec.cuisine}</strong> — {rec.gap}</p>
														</div>
													{/each}
												</div>
											</div>
										</div>
									</div>

									<div class="mt-4 flex items-center gap-2 rounded-xl bg-gray-50 px-4 py-2.5 border border-gray-100">
										<span class="text-sm text-black/25 flex-1">Ask anything about your market...</span>
										<svg class="h-4 w-4 text-black/20" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
											<path stroke-linecap="round" stroke-linejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
										</svg>
									</div>
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
