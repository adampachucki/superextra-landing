<script lang="ts">
	import { fade } from 'svelte/transition';

	const GRAD_EMERALD_VIOLET = 'linear-gradient(to right, rgb(110,231,183), rgb(167,139,250))';
	const GRAD_INDIGO_VIOLET = 'linear-gradient(to right, rgb(99,102,241), rgb(167,139,250))';
	const GRAD_INDIGO_VIOLET_V = 'linear-gradient(to top, rgb(99,102,241), rgb(167,139,250))';
	const GRAD_PINK_AMBER = 'linear-gradient(to right, rgb(244,114,182), rgb(251,191,36))';
	const GRAD_PINK_AMBER_V = 'linear-gradient(to top, rgb(244,114,182), rgb(251,191,36))';
	const GRAD_CYAN_EMERALD = 'linear-gradient(to top, rgb(6,182,212), rgb(110,231,183))';
	const GRAD_CYAN_EMERALD_H = 'linear-gradient(to right, rgb(6,182,212), rgb(110,231,183))';
	const GRAD_EMERALD_CYAN = 'linear-gradient(to right, rgb(110,231,183), rgb(6,182,212))';
	const GRAD_AMBER_PINK = 'linear-gradient(to right, rgb(251,191,36), rgb(244,114,182))';
	const GRAD_PINK_VIOLET = 'linear-gradient(to right, rgb(244,114,182), rgb(167,139,250))';
	const GRAD_GRAY = 'linear-gradient(to right, rgb(180,180,190), rgb(150,150,165))';

	const netOpenings = [
		{ m: 'Oct', v: 3 },
		{ m: 'Nov', v: 5 },
		{ m: 'Dec', v: -1 },
		{ m: 'Jan', v: 2 },
		{ m: 'Feb', v: 6 },
		{ m: 'Mar', v: 8 }
	];

	const cuisineLandscape = [
		{ name: 'Korean Fusion', change: '+34%', pct: 88, up: true },
		{ name: 'Mediterranean', change: '+22%', pct: 68, up: true },
		{ name: 'Fast Casual Pizza', change: '+18%', pct: 55, up: true },
		{ name: 'Fine Dining French', change: '-8%', pct: 22, up: false }
	];

	const trendingItems = [
		{ item: 'Smash Burger', price: '$18', trend: '+12%', up: true, hot: true },
		{ item: 'Matcha Latte', price: '$7', trend: '+28%', up: true, hot: true },
		{ item: 'Birria Tacos', price: '$16', trend: '+15%', up: true, hot: false },
		{ item: 'Caesar Salad', price: '$14', trend: '+3%', up: true, hot: false },
		{ item: 'Wagyu Steak', price: '$62', trend: '-5%', up: false, hot: false }
	];

	const activePromos = [
		{ venue: 'Burger Joint', deal: '2-for-1 Tuesdays', type: 'Dine-in' },
		{ venue: 'Sakura Ramen', deal: '15% off delivery', type: 'Delivery' },
		{ venue: 'Taco Loco', deal: 'Free drink w/ combo', type: 'All channels' }
	];

	const revenueKpis = [
		{ value: '$1.2M', label: 'Avg Revenue', change: '+8%', up: true },
		{ value: '$47', label: 'Avg Check', change: '+3%', up: true },
		{ value: '78%', label: 'Occupancy', change: '-2%', up: false }
	];

	const monthlyRevenue = [
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
	];

	const adSpendByChannel = [
		{ name: 'Instagram', spend: '$2.4K/mo', pct: 85, grad: GRAD_INDIGO_VIOLET },
		{ name: 'Google Ads', spend: '$1.8K/mo', pct: 64, grad: GRAD_CYAN_EMERALD_H },
		{ name: 'TikTok', spend: '$800/mo', pct: 28, grad: GRAD_PINK_AMBER },
		{ name: 'Facebook', spend: '$600/mo', pct: 21, grad: GRAD_GRAY }
	];

	const commonTools = ['Square POS', 'Toast', 'OpenTable', 'Yelp', 'Mailchimp', 'Google Ads', 'Meta Business', 'Lightspeed'];

	const sentimentBreakdown = [
		{ label: 'Positive', pct: 73, grad: GRAD_EMERALD_CYAN },
		{ label: 'Neutral', pct: 19, grad: GRAD_GRAY },
		{ label: 'Negative', pct: 8, grad: GRAD_PINK_AMBER }
	];

	const topMentions = [
		{ word: 'great service', size: 'text-xs' },
		{ word: 'cozy ambiance', size: 'text-[11px]' },
		{ word: 'slow wait', size: 'text-[10px]' },
		{ word: 'fresh ingredients', size: 'text-xs' },
		{ word: 'date night', size: 'text-[11px]' },
		{ word: 'parking', size: 'text-[10px]' }
	];

	const weeklyTraffic = [
		{ day: 'Mon', h: 40 },
		{ day: 'Tue', h: 55 },
		{ day: 'Wed', h: 50 },
		{ day: 'Thu', h: 60 },
		{ day: 'Fri', h: 85 },
		{ day: 'Sat', h: 95 },
		{ day: 'Sun', h: 70 }
	];

	const operationalMetrics = [
		{ label: 'Labor Availability', score: 'Moderate', pct: 55, grad: GRAD_AMBER_PINK },
		{ label: 'Staff Turnover', score: '42% annual', pct: 42, grad: GRAD_PINK_VIOLET },
		{ label: 'Open Positions', score: '124 listed', pct: 65, grad: GRAD_INDIGO_VIOLET },
		{ label: 'Supplier Pricing', score: '+3.2% YoY', pct: 32, grad: GRAD_CYAN_EMERALD_H }
	];

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

{#snippet progressBar(pct: number, grad: string)}
	<div class="h-1.5 w-full rounded-full bg-gray-100">
		<div class="h-full rounded-full" style="width: {pct}%; background: {grad}"></div>
	</div>
{/snippet}

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
						onclick={() => (activeIndex = i)}
					>
						<div class="flex items-center justify-between py-5">
							<h3 class="text-base font-semibold transition-colors {activeIndex === i ? 'text-black' : 'text-black/40 group-hover:text-black'}">
								{category.title}
							</h3>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								class="h-5 w-5 shrink-0 text-black/25 transition-transform duration-300 {activeIndex === i ? 'rotate-180' : ''}"
								fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"
							>
								<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
							</svg>
						</div>

						{#if activeIndex === i}
							<div class="pb-6">
								<p class="mb-4 text-sm leading-snug text-black/60">
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

			<div class="hidden lg:block relative aspect-[1940/1799]">
				{#key activeIndex}
				<div class="w-full absolute inset-0" in:fade={{ duration: 400, delay: 100 }} out:fade={{ duration: 300 }}>
				{#if activeIndex === 0}
					<img src="/landscape.webp" alt="Market Landscape" class="w-full rounded-2xl overflow-hidden" />
				{:else if activeIndex === 1}
					<img src="/menu.webp" alt="Menu & Pricing" class="w-full rounded-2xl overflow-hidden" />
				{:else if activeIndex === 2}
					<img src="/revenue.webp" alt="Revenue & Sales" class="w-full rounded-2xl overflow-hidden" />
				{:else if activeIndex === 3}
					<img src="/marketing.webp" alt="Marketing & Digital" class="w-full rounded-2xl" />
				{:else if activeIndex === 4}
					<img src="/guest.webp" alt="Guest Intelligence" class="w-full rounded-2xl" />
				{:else if activeIndex === 5}
					<img src="/location.webp" alt="Location & Foot Traffic" class="w-full rounded-2xl" />
				{:else if activeIndex === 6}
					<img src="/ops.webp" alt="Operations" class="w-full rounded-2xl" />
				{/if}
				</div>
				{/key}
			</div>
		</div>
	</div>
</section>
