<script lang="ts">
	import { fade } from 'svelte/transition';

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

	let activeIndex = $state(0);
</script>

<section id="platform" class="border-t border-gray-200 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<p class="mb-6 text-sm font-medium uppercase tracking-widest text-black/40">
			Extra Clarity
		</p>
		<h2 class="mb-4 max-w-2xl text-[clamp(2rem,4vw,3.25rem)] leading-[1.1] font-normal tracking-[-0.02em] text-black">
			Data and insights behind every restaurant decision
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
					<div class="aspect-[4/3] w-full p-8 md:p-10">
						{#key activeIndex}
						<div class="h-full" in:fade={{ duration: 200 }}>
						{#if activeIndex === 0}
							<!-- Market Landscape -->
							<div class="flex h-full flex-col">
								<p class="mb-4 text-[11px] font-medium uppercase tracking-widest text-black/30">Market Landscape</p>

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
							<!-- Menu & Pricing -->
							<div class="flex h-full flex-col">
								<p class="mb-5 text-[11px] font-medium uppercase tracking-widest text-black/30">Menu & Pricing</p>

								<div class="rounded-xl bg-white border border-gray-100 overflow-hidden mb-4">
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
										{ item: 'Wagyu Steak', price: '$62', trend: '-5%', up: false, hot: false }
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

								<!-- Deals & Promos -->
								<div class="flex-1">
									<p class="text-[10px] font-medium text-black/30 mb-2.5 uppercase tracking-wider">Active Promotions</p>
									<div class="space-y-2">
										{#each [
											{ venue: 'Burger Joint', deal: '2-for-1 Tuesdays', type: 'Dine-in' },
											{ venue: 'Sakura Ramen', deal: '15% off delivery', type: 'Delivery' },
											{ venue: 'Taco Loco', deal: 'Free drink w/ combo', type: 'All channels' }
										] as promo}
											<div class="flex items-center justify-between rounded-lg bg-white border border-gray-100 px-3 py-2">
												<div>
													<span class="text-xs text-black/70 font-medium">{promo.venue}</span>
													<p class="text-[10px] text-black/40">{promo.deal}</p>
												</div>
												<span class="rounded-full bg-gray-100 px-2 py-0.5 text-[9px] text-black/40">{promo.type}</span>
											</div>
										{/each}
									</div>
								</div>

								<div class="border-t border-gray-200 pt-3 mt-4">
									<span class="text-[10px] text-black/30">Based on 1,240 menus across the market</span>
								</div>
							</div>

						{:else if activeIndex === 2}
							<!-- Revenue & Sales -->
							<div class="flex h-full flex-col">
								<p class="mb-5 text-[11px] font-medium uppercase tracking-widest text-black/30">Revenue & Sales</p>

								<div class="grid grid-cols-3 gap-3 mb-5">
									{#each [
										{ value: '$1.2M', label: 'Avg Revenue', sub: 'per location / yr', change: '+8%', up: true },
										{ value: '$47', label: 'Avg Check', sub: 'dinner service', change: '+3%', up: true },
										{ value: '78%', label: 'Occupancy', sub: 'prime hours', change: '-2%', up: false }
									] as kpi}
										<div class="rounded-xl bg-white p-3 border border-gray-100">
											<p class="text-xl font-bold text-black leading-none">{kpi.value}</p>
											<p class="text-[10px] text-black/50 mt-1">{kpi.label}</p>
											<span class="text-[9px] font-medium {kpi.up ? 'text-emerald-600' : 'text-red-500'}">{kpi.change}</span>
										</div>
									{/each}
								</div>

								<!-- Channel Split -->
								<div class="mb-5">
									<p class="text-[10px] font-medium text-black/30 mb-2 uppercase tracking-wider">Revenue by Channel</p>
									<div class="flex rounded-lg overflow-hidden h-7 mb-2">
										<div class="bg-black flex items-center justify-center" style="width: 58%">
											<span class="text-[10px] font-bold text-white">58%</span>
										</div>
										<div class="flex items-center justify-center" style="width: 28%; background: linear-gradient(to right, rgb(99,102,241), rgb(167,139,250))">
											<span class="text-[10px] font-bold text-white">28%</span>
										</div>
										<div class="bg-gray-300 flex items-center justify-center" style="width: 14%">
											<span class="text-[10px] font-bold text-white">14%</span>
										</div>
									</div>
									<div class="flex gap-4 text-[10px]">
										<span class="flex items-center gap-1.5"><span class="h-2 w-2 rounded-full bg-black"></span> Dine-in</span>
										<span class="flex items-center gap-1.5"><span class="h-2 w-2 rounded-full bg-indigo-500"></span> Delivery</span>
										<span class="flex items-center gap-1.5"><span class="h-2 w-2 rounded-full bg-gray-300"></span> Takeaway</span>
									</div>
								</div>

								<!-- Seasonality -->
								<div class="flex-1">
									<p class="text-[10px] font-medium text-black/30 mb-2 uppercase tracking-wider">Monthly Revenue Index</p>
									<div class="flex items-end gap-1.5 h-16">
										{#each [
											{ m: 'Jan', v: 65 },
											{ m: 'Feb', v: 60 },
											{ m: 'Mar', v: 72 },
											{ m: 'Apr', v: 78 },
											{ m: 'May', v: 85 },
											{ m: 'Jun', v: 92 },
											{ m: 'Jul', v: 95 },
											{ m: 'Aug', v: 88 },
											{ m: 'Sep', v: 82 },
											{ m: 'Oct', v: 78 },
											{ m: 'Nov', v: 85 },
											{ m: 'Dec', v: 100 }
										] as bar}
											<div class="flex-1 flex flex-col items-center gap-1">
												<div class="w-full rounded-t-sm" style="height: {bar.v}%; background: linear-gradient(to top, rgb(99,102,241), rgb(167,139,250))"></div>
												<span class="text-[7px] text-black/25">{bar.m}</span>
											</div>
										{/each}
									</div>
								</div>

								<div class="border-t border-gray-200 pt-3 mt-4">
									<span class="text-[10px] text-black/30">Based on 186 comparable venues</span>
								</div>
							</div>

						{:else if activeIndex === 3}
							<!-- Marketing & Digital -->
							<div class="flex h-full flex-col">
								<p class="mb-5 text-[11px] font-medium uppercase tracking-widest text-black/30">Marketing & Digital</p>

								<!-- Social Media Overview -->
								<div class="grid grid-cols-3 gap-3 mb-5">
									<div class="rounded-xl bg-white p-3 border border-gray-100">
										<p class="text-xl font-bold text-black">8.4K</p>
										<p class="text-[10px] text-black/40 mt-0.5">Avg followers</p>
									</div>
									<div class="rounded-xl bg-white p-3 border border-gray-100">
										<p class="text-xl font-bold text-black">2.8<span class="text-sm font-normal text-black/40">%</span></p>
										<p class="text-[10px] text-black/40 mt-0.5">Engagement rate</p>
									</div>
									<div class="rounded-xl bg-white p-3 border border-gray-100">
										<p class="text-xl font-bold text-black">4.2</p>
										<p class="text-[10px] text-black/40 mt-0.5">Posts / week</p>
									</div>
								</div>

								<!-- Ad Spend by Channel -->
								<div class="mb-5">
									<p class="text-[10px] font-medium text-black/30 mb-2.5 uppercase tracking-wider">Estimated Ad Spend — Market Avg</p>
									<div class="space-y-2">
										{#each [
											{ name: 'Instagram', spend: '$2.4K/mo', pct: 85, grad: 'linear-gradient(to right, rgb(99,102,241), rgb(167,139,250))' },
											{ name: 'Google Ads', spend: '$1.8K/mo', pct: 64, grad: 'linear-gradient(to right, rgb(6,182,212), rgb(110,231,183))' },
											{ name: 'TikTok', spend: '$800/mo', pct: 28, grad: 'linear-gradient(to right, rgb(244,114,182), rgb(251,191,36))' },
											{ name: 'Facebook', spend: '$600/mo', pct: 21, grad: 'linear-gradient(to right, rgb(180,180,190), rgb(150,150,165))' }
										] as channel}
											<div>
												<div class="flex items-center justify-between mb-0.5">
													<span class="text-xs text-black/60">{channel.name}</span>
													<span class="text-[10px] font-medium text-black/40">{channel.spend}</span>
												</div>
												<div class="h-1.5 w-full rounded-full bg-gray-100">
													<div class="h-full rounded-full" style="width: {channel.pct}%; background: {channel.grad}"></div>
												</div>
											</div>
										{/each}
									</div>
								</div>

								<!-- Tools & Platforms -->
								<div class="flex-1">
									<p class="text-[10px] font-medium text-black/30 mb-2 uppercase tracking-wider">Common Tools & Platforms</p>
									<div class="flex flex-wrap gap-1.5">
										{#each ['Square POS', 'Toast', 'OpenTable', 'Yelp', 'Mailchimp', 'Google Ads', 'Meta Business', 'Lightspeed'] as tool}
											<span class="rounded-full bg-white border border-gray-100 px-2.5 py-1 text-[11px] text-black/50">{tool}</span>
										{/each}
									</div>
								</div>

								<div class="border-t border-gray-200 pt-3 mt-4">
									<span class="text-[10px] text-black/30">Across 320 tracked competitors</span>
								</div>
							</div>

						{:else if activeIndex === 4}
							<!-- Guest Intelligence -->
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

								<!-- Tourist vs Local -->
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

								<!-- Payment Methods -->
								<div class="mb-4">
									<p class="text-[10px] font-medium text-black/30 mb-2 uppercase tracking-wider">Payment Preferences</p>
									<div class="flex rounded-lg overflow-hidden h-6">
										<div class="flex items-center justify-center" style="width: 62%; background: linear-gradient(to right, rgb(99,102,241), rgb(167,139,250))">
											<span class="text-[9px] font-bold text-white">Card 62%</span>
										</div>
										<div class="bg-black flex items-center justify-center" style="width: 24%">
											<span class="text-[9px] font-bold text-white">Cash 24%</span>
										</div>
										<div class="bg-gray-300 flex items-center justify-center" style="width: 14%">
											<span class="text-[9px] font-bold text-black/50">Mobile 14%</span>
										</div>
									</div>
								</div>

								<!-- Top Mentions -->
								<div class="border-t border-gray-200 pt-3 flex-1">
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

						{:else if activeIndex === 5}
							<!-- Location & Foot Traffic -->
							<div class="flex h-full flex-col">
								<p class="mb-4 text-[11px] font-medium uppercase tracking-widest text-black/30">Location & Foot Traffic</p>

								<!-- Weekly foot traffic chart -->
								<div class="mb-5">
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

								<!-- Visit Time Distribution -->
								<div class="mb-5">
									<p class="text-[10px] font-medium text-black/30 mb-2 uppercase tracking-wider">Visit Time Distribution</p>
									<div class="flex rounded-lg overflow-hidden h-7 mb-2">
										<div class="flex items-center justify-center" style="width: 15%; background: rgb(180,180,190)">
											<span class="text-[8px] font-bold text-white">15%</span>
										</div>
										<div class="flex items-center justify-center" style="width: 32%; background: linear-gradient(to right, rgb(99,102,241), rgb(167,139,250))">
											<span class="text-[9px] font-bold text-white">32%</span>
										</div>
										<div class="flex items-center justify-center" style="width: 12%; background: rgb(200,200,210)">
											<span class="text-[8px] font-bold text-white">12%</span>
										</div>
										<div class="flex items-center justify-center" style="width: 35%; background: linear-gradient(to right, rgb(6,182,212), rgb(110,231,183))">
											<span class="text-[9px] font-bold text-white">35%</span>
										</div>
										<div class="flex items-center justify-center" style="width: 6%; background: rgb(160,160,170)">
										</div>
									</div>
									<div class="flex gap-3 text-[9px] text-black/40">
										<span>Morning</span>
										<span>Lunch</span>
										<span>Afternoon</span>
										<span>Dinner</span>
										<span>Late</span>
									</div>
								</div>

								<!-- Demographics -->
								<div class="grid grid-cols-2 gap-3 mb-4">
									<div class="rounded-xl bg-white p-3 border border-gray-100">
										<p class="text-lg font-bold text-black">34</p>
										<p class="text-[10px] text-black/40 mt-0.5">Median age</p>
									</div>
									<div class="rounded-xl bg-white p-3 border border-gray-100">
										<p class="text-lg font-bold text-emerald-600">High</p>
										<p class="text-[10px] text-black/40 mt-0.5">Purchasing power</p>
									</div>
								</div>

								<div class="flex-1 grid grid-cols-2 gap-3">
									<div class="rounded-xl bg-white p-3 border border-gray-100">
										<p class="text-lg font-bold text-black">12.4K</p>
										<p class="text-[10px] text-black/40 mt-0.5">People / sq mi</p>
									</div>
									<div class="rounded-xl bg-white p-3 border border-gray-100">
										<p class="text-lg font-bold text-emerald-600">+8%</p>
										<p class="text-[10px] text-black/40 mt-0.5">Projected growth</p>
									</div>
								</div>

								<div class="border-t border-gray-200 pt-3 mt-4 flex items-center justify-between">
									<span class="text-[10px] text-black/30">Downtown district — 1mi radius</span>
									<span class="text-[10px] font-medium text-black/40">68% local / 32% tourist</span>
								</div>
							</div>

						{:else if activeIndex === 6}
							<!-- Operations -->
							<div class="flex h-full flex-col">
								<p class="mb-5 text-[11px] font-medium uppercase tracking-widest text-black/30">Operations</p>

								<div class="grid grid-cols-2 gap-3 mb-5">
									<div class="rounded-xl bg-white p-4 border border-gray-100">
										<div class="flex items-end gap-1 mb-1">
											<span class="text-sm text-black/30 mb-0.5">$</span>
											<span class="text-3xl font-bold text-black leading-none">18.50</span>
											<span class="text-sm text-black/30 mb-0.5">/hr</span>
										</div>
										<p class="text-[10px] text-black/40">Avg salary</p>
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
										{ label: 'Labor Availability', score: 'Moderate', pct: 55, grad: 'linear-gradient(to right, rgb(251,191,36), rgb(244,114,182))' },
										{ label: 'Staff Turnover', score: '42% annual', pct: 42, grad: 'linear-gradient(to right, rgb(244,114,182), rgb(167,139,250))' },
										{ label: 'Open Positions', score: '124 listed', pct: 65, grad: 'linear-gradient(to right, rgb(99,102,241), rgb(167,139,250))' },
										{ label: 'Supplier Pricing', score: '+3.2% YoY', pct: 32, grad: 'linear-gradient(to right, rgb(6,182,212), rgb(110,231,183))' }
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
									<span class="text-[10px] text-black/30">Market avg — Downtown district</span>
								</div>
							</div>

						{:else}
							<div class="flex h-full items-center justify-center text-sm text-black/30">
								Click a category to explore
							</div>
						{/if}
						</div>
						{/key}
					</div>
				</div>
			</div>
		</div>
	</div>
</section>
