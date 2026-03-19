<script lang="ts">
	let scrollContainer: HTMLDivElement;
	let activeIndex = $state(0);

	const useCases = [
		{
			title: 'Market Research',
			audience: 'Operators & Chains',
			description:
				'Understand market dynamics, competitive positioning, and emerging white spaces. Continuously monitor shifts so you spot opportunities before anyone else.',
			image: '/ppl/image1.webp'
		},
		{
			title: 'Marketing Strategy',
			audience: 'Operators & Agencies',
			description:
				'Benchmark your brand against local competitors. Know which campaigns, channels, and price points are driving results in your market.',
			image: '/ppl/image2.webp'
		},
		{
			title: 'Expansion Planning',
			audience: 'Chains & Investors',
			description:
				'Evaluate locations with foot traffic, demographics, competition density, and rent data side by side. De-risk every new site decision.',
			image: '/ppl/image3.webp'
		},
		{
			title: 'Financial Modelling',
			audience: 'Operators & Investors',
			description:
				'Build projections grounded in real revenue benchmarks, occupancy rates, labor costs, and seasonality patterns — not assumptions.',
			image: '/ppl/image4.webp'
		},
		{
			title: 'Ops & Workforce',
			audience: 'Operators & Chains',
			description:
				'Track how your costs, staffing, and channel performance compare to the local market. Spot inefficiencies before they hit margins.',
			image: '/ppl/image5.webp'
		},
		{
			title: 'Sales & Leads',
			audience: 'Suppliers & Distributors',
			description:
				'Find restaurants that match your ideal customer profile, track new openings in your territory, and time your outreach with real demand signals.',
			image: '/ppl/image6.webp'
		},
		{
			title: 'Due Diligence',
			audience: 'Investors & Advisors',
			description:
				'Verify partners and vet investment opportunities with independent market data — revenue benchmarks, competitive positioning, and local demand signals.',
			image: '/ppl/image7.webp'
		},
		{
			title: 'Enrichment',
			audience: 'Tech Platforms',
			description:
				'Integrate hyper-local restaurant intelligence into your platform via API. Add market context, venue data, and competitive insights to your product.',
			image: '/ppl/image3.webp'
		}
	];

	function scrollTo(index: number) {
		if (!scrollContainer) return;
		if (index === 0) {
			scrollContainer.scrollTo({ left: 0, behavior: 'smooth' });
			return;
		}
		const cards = scrollContainer.querySelectorAll<HTMLElement>('[data-card]');
		if (cards[index]) {
			const card = cards[index];
			const containerLeft = scrollContainer.getBoundingClientRect().left;
			const cardLeft = card.getBoundingClientRect().left;
			const offset = cardLeft - containerLeft + scrollContainer.scrollLeft;
			scrollContainer.scrollTo({ left: offset, behavior: 'smooth' });
		}
	}

	function next() {
		const newIndex = Math.min(activeIndex + 1, useCases.length - 1);
		activeIndex = newIndex;
		scrollTo(newIndex);
	}

	function prev() {
		const newIndex = Math.max(activeIndex - 1, 0);
		activeIndex = newIndex;
		scrollTo(newIndex);
	}

	function onScroll() {
		if (!scrollContainer) return;
		const cards = scrollContainer.querySelectorAll<HTMLElement>('[data-card]');
		const containerLeft = scrollContainer.getBoundingClientRect().left;
		let closest = 0;
		let closestDist = Infinity;
		cards.forEach((card, i) => {
			const dist = Math.abs(card.getBoundingClientRect().left - containerLeft);
			if (dist < closestDist) {
				closestDist = dist;
				closest = i;
			}
		});
		activeIndex = closest;
	}
</script>

{#snippet navButtons()}
	<button
		onclick={prev}
		disabled={activeIndex === 0}
		class="flex h-10 w-10 cursor-pointer items-center justify-center rounded-full border border-gray-200 transition-colors hover:bg-gray-50 disabled:cursor-default disabled:opacity-30"
		aria-label="Previous"
	>
		<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
			<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
		</svg>
	</button>
	<button
		onclick={next}
		disabled={activeIndex === useCases.length - 1}
		class="flex h-10 w-10 cursor-pointer items-center justify-center rounded-full border border-gray-200 transition-colors hover:bg-gray-50 disabled:cursor-default disabled:opacity-30"
		aria-label="Next"
	>
		<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
			<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
		</svg>
	</button>
{/snippet}

{#snippet useCaseGraphic(index: number)}
	{#if index === 0}
		<!-- Market Research: Orbital ellipses -->
		<svg viewBox="0 0 200 200" fill="none" class="w-3/5">
			<line x1="10" y1="100" x2="190" y2="100" stroke="black" stroke-width="0.5" stroke-dasharray="2,3"/>
			<line x1="100" y1="10" x2="100" y2="190" stroke="black" stroke-width="0.5" stroke-dasharray="2,3"/>
			<ellipse cx="100" cy="100" rx="82" ry="26" stroke="black" stroke-width="1" transform="rotate(-30 100 100)"/>
			<ellipse cx="100" cy="100" rx="64" ry="34" stroke="black" stroke-width="1" transform="rotate(25 100 100)"/>
			<ellipse cx="100" cy="100" rx="46" ry="20" stroke="black" stroke-width="0.7" stroke-dasharray="4,3" transform="rotate(75 100 100)"/>
			<circle cx="100" cy="100" r="2.5" fill="black"/>
			<circle cx="38" cy="78" r="1.5" fill="black"/>
			<circle cx="162" cy="122" r="1.5" fill="black"/>
			<circle cx="134" cy="36" r="1.5" fill="black"/>
			<circle cx="66" cy="164" r="1.5" fill="black"/>
		</svg>
	{:else if index === 1}
		<!-- Marketing Strategy: Signal arcs -->
		<svg viewBox="0 0 200 200" fill="none" class="w-3/5">
			<path d="M 60,170 A 30,30 0 0,1 30,140" stroke="black" stroke-width="1"/>
			<path d="M 90,170 A 60,60 0 0,1 30,110" stroke="black" stroke-width="1"/>
			<path d="M 120,170 A 90,90 0 0,1 30,80" stroke="black" stroke-width="0.8"/>
			<path d="M 150,170 A 120,120 0 0,1 30,50" stroke="black" stroke-width="0.6" stroke-dasharray="4,3"/>
			<path d="M 180,170 A 150,150 0 0,1 30,20" stroke="black" stroke-width="0.5" stroke-dasharray="2,3"/>
			<circle cx="30" cy="170" r="3" fill="black"/>
			<line x1="30" y1="170" x2="175" y2="35" stroke="black" stroke-width="0.4" stroke-dasharray="2,4"/>
			<line x1="30" y1="170" x2="185" y2="95" stroke="black" stroke-width="0.4" stroke-dasharray="2,4"/>
			<circle cx="78" cy="118" r="1.5" fill="black"/>
			<circle cx="118" cy="78" r="1.5" fill="black"/>
			<circle cx="152" cy="52" r="1.5" fill="black"/>
		</svg>
	{:else if index === 2}
		<!-- Expansion Planning: Growth rings -->
		<svg viewBox="0 0 200 200" fill="none" class="w-3/5">
			<rect x="88" y="88" width="24" height="24" stroke="black" stroke-width="1.2" rx="2"/>
			<rect x="68" y="68" width="64" height="64" stroke="black" stroke-width="1" rx="4"/>
			<rect x="45" y="45" width="110" height="110" stroke="black" stroke-width="0.8" stroke-dasharray="4,3" rx="6"/>
			<rect x="20" y="20" width="160" height="160" stroke="black" stroke-width="0.5" stroke-dasharray="2,3" rx="8"/>
			<circle cx="100" cy="100" r="2" fill="black"/>
			<line x1="100" y1="20" x2="100" y2="88" stroke="black" stroke-width="0.4" stroke-dasharray="2,3"/>
			<line x1="100" y1="112" x2="100" y2="180" stroke="black" stroke-width="0.4" stroke-dasharray="2,3"/>
			<line x1="20" y1="100" x2="88" y2="100" stroke="black" stroke-width="0.4" stroke-dasharray="2,3"/>
			<line x1="112" y1="100" x2="180" y2="100" stroke="black" stroke-width="0.4" stroke-dasharray="2,3"/>
			<circle cx="68" cy="68" r="1.5" fill="black"/>
			<circle cx="132" cy="68" r="1.5" fill="black"/>
			<circle cx="68" cy="132" r="1.5" fill="black"/>
			<circle cx="132" cy="132" r="1.5" fill="black"/>
		</svg>
	{:else if index === 3}
		<!-- Financial Modelling: Wave curves -->
		<svg viewBox="0 0 200 200" fill="none" class="w-3/5">
			<line x1="10" y1="110" x2="190" y2="110" stroke="black" stroke-width="0.5"/>
			<line x1="20" y1="110" x2="20" y2="40" stroke="black" stroke-width="0.5"/>
			<path d="M 20,110 C 55,55 75,55 110,110 S 165,165 190,110" stroke="black" stroke-width="1"/>
			<path d="M 20,125 C 60,75 90,75 120,110 S 170,145 190,100" stroke="black" stroke-width="0.7" stroke-dasharray="4,3"/>
			<line x1="65" y1="65" x2="65" y2="155" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/>
			<line x1="110" y1="65" x2="110" y2="155" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/>
			<line x1="155" y1="65" x2="155" y2="155" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/>
			<circle cx="65" cy="70" r="1.5" fill="black"/>
			<circle cx="110" cy="110" r="2" fill="black"/>
			<circle cx="155" cy="140" r="1.5" fill="black"/>
		</svg>
	{:else if index === 4}
		<!-- Ops & Workforce: Wireframe cube -->
		<svg viewBox="0 0 200 200" fill="none" class="w-3/5">
			<path d="M 50,75 L 150,75 L 150,175 L 50,175 Z" stroke="black" stroke-width="1"/>
			<path d="M 75,25 L 175,25 L 175,125 L 75,125 Z" stroke="black" stroke-width="0.7" stroke-dasharray="4,3"/>
			<line x1="50" y1="75" x2="75" y2="25" stroke="black" stroke-width="0.8"/>
			<line x1="150" y1="75" x2="175" y2="25" stroke="black" stroke-width="0.8"/>
			<line x1="150" y1="175" x2="175" y2="125" stroke="black" stroke-width="0.8"/>
			<line x1="50" y1="175" x2="75" y2="125" stroke="black" stroke-width="0.5" stroke-dasharray="3,3"/>
			<line x1="100" y1="75" x2="100" y2="175" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/>
			<line x1="50" y1="125" x2="150" y2="125" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/>
			<line x1="50" y1="75" x2="150" y2="175" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/>
			<circle cx="50" cy="75" r="1.5" fill="black"/>
			<circle cx="150" cy="75" r="1.5" fill="black"/>
			<circle cx="150" cy="175" r="1.5" fill="black"/>
			<circle cx="175" cy="25" r="1.5" fill="black"/>
		</svg>
	{:else if index === 5}
		<!-- Sales & Leads: Convergence funnel -->
		<svg viewBox="0 0 200 200" fill="none" class="w-3/5">
			<path d="M 25,30 C 45,85 75,135 100,175" stroke="black" stroke-width="1"/>
			<path d="M 65,22 C 75,70 88,120 100,175" stroke="black" stroke-width="0.8"/>
			<path d="M 108,18 C 106,65 103,115 100,175" stroke="black" stroke-width="0.7" stroke-dasharray="4,3"/>
			<path d="M 150,24 C 138,75 118,128 100,175" stroke="black" stroke-width="0.8"/>
			<path d="M 180,35 C 158,85 128,135 100,175" stroke="black" stroke-width="1"/>
			<circle cx="100" cy="175" r="3" fill="black"/>
			<circle cx="25" cy="30" r="1.5" fill="black"/>
			<circle cx="65" cy="22" r="1.5" fill="black"/>
			<circle cx="108" cy="18" r="1.5" fill="black"/>
			<circle cx="150" cy="24" r="1.5" fill="black"/>
			<circle cx="180" cy="35" r="1.5" fill="black"/>
			<line x1="35" y1="80" x2="165" y2="80" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/>
			<line x1="55" y1="130" x2="145" y2="130" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/>
		</svg>
	{:else if index === 6}
		<!-- Due Diligence: Concentric circles with sweep -->
		<svg viewBox="0 0 200 200" fill="none" class="w-3/5">
			<circle cx="100" cy="100" r="20" stroke="black" stroke-width="0.5" stroke-dasharray="2,3"/>
			<circle cx="100" cy="100" r="40" stroke="black" stroke-width="0.7"/>
			<circle cx="100" cy="100" r="60" stroke="black" stroke-width="0.7"/>
			<circle cx="100" cy="100" r="80" stroke="black" stroke-width="0.5" stroke-dasharray="3,3"/>
			<path d="M 100,20 A 80,80 0 0,1 174,68" stroke="black" stroke-width="2.5"/>
			<path d="M 100,40 A 60,60 0 0,1 152,72" stroke="black" stroke-width="1.8"/>
			<circle cx="100" cy="100" r="2" fill="black"/>
			<circle cx="100" cy="20" r="1.5" fill="black"/>
			<circle cx="174" cy="68" r="1.5" fill="black"/>
			<circle cx="140" cy="100" r="1.5" fill="black"/>
		</svg>
	{:else if index === 7}
		<!-- Enrichment: Merging data layers -->
		<svg viewBox="0 0 200 200" fill="none" class="w-3/5">
			<path d="M 20,45 C 65,45 125,50 175,92" stroke="black" stroke-width="1"/>
			<path d="M 20,75 C 65,75 125,78 175,96" stroke="black" stroke-width="0.8"/>
			<path d="M 20,105 C 65,105 125,104 175,100" stroke="black" stroke-width="0.7" stroke-dasharray="4,3"/>
			<path d="M 20,135 C 65,135 125,122 175,104" stroke="black" stroke-width="0.8"/>
			<path d="M 20,165 C 65,160 125,135 175,108" stroke="black" stroke-width="1"/>
			<circle cx="175" cy="100" r="3" fill="black"/>
			<circle cx="20" cy="45" r="1.5" fill="black"/>
			<circle cx="20" cy="75" r="1.5" fill="black"/>
			<circle cx="20" cy="105" r="1.5" fill="black"/>
			<circle cx="20" cy="135" r="1.5" fill="black"/>
			<circle cx="20" cy="165" r="1.5" fill="black"/>
			<line x1="65" y1="35" x2="65" y2="175" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/>
			<line x1="125" y1="35" x2="125" y2="175" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/>
		</svg>
	{/if}
{/snippet}

<section id="use-cases" class="border-t border-gray-200 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<div class="mb-12 flex items-end justify-between">
			<div>
				<p class="mb-6 text-sm font-medium uppercase tracking-widest text-black/40">Use Cases</p>
				<h2
					class="max-w-xl text-[clamp(2rem,4vw,3.25rem)] leading-[1.1] font-normal tracking-[-0.02em] text-black"
				>
					Supporting teams across all roles and functions
				</h2>
			</div>

			<div class="hidden items-center gap-2 md:flex">
				{@render navButtons()}
			</div>
		</div>
	</div>

	<div
		bind:this={scrollContainer}
		onscroll={onScroll}
		class="scrollbar-hide flex gap-5 overflow-x-auto scroll-smooth"
	>
		{#each useCases as useCase, i (useCase.title)}
			<div
				data-card
				class="w-[min(75vw,380px)] flex-shrink-0"
				style="{i === 0 ? 'margin-left: var(--content-inset)' : ''}{i === useCases.length - 1 ? 'margin-right: var(--content-inset)' : ''}"
			>
				<div
					class="mb-5 flex aspect-[4/3] items-center justify-center overflow-hidden rounded-2xl bg-[#f5f4f2]"
				>
					{@render useCaseGraphic(i)}
				</div>

				<p class="mb-1 text-xs font-medium text-black/30">{useCase.audience}</p>
				<h3 class="mb-2 text-lg font-semibold tracking-[-0.01em] text-black">
					{useCase.title}
				</h3>
				<p class="pr-4 text-sm leading-snug text-black/50">
					{useCase.description}
				</p>
			</div>
		{/each}
	</div>

	<div class="mt-8 flex items-center justify-center gap-2 md:hidden">
		{@render navButtons()}
	</div>
</section>

<style>
	section {
		--content-inset: max(24px, calc((100% - 1200px) / 2 + 24px));
	}
	.scrollbar-hide {
		-ms-overflow-style: none;
		scrollbar-width: none;
	}
	.scrollbar-hide::-webkit-scrollbar {
		display: none;
	}
</style>
