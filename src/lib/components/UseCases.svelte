<script lang="ts">
	import UseCaseGraphics from './UseCaseGraphics.svelte';
	import CardCanvas from './CardCanvas.svelte';
	import SectionHeader from './SectionHeader.svelte';

	let scrollContainer: HTMLDivElement;
	let activeIndex = $state(0);
	let hoveredIndex = $state(-1);

	const useCases = [
		{
			title: 'Market Research',
			audience: 'Operators & Chains',
			description:
				'Understand market dynamics, competitive positioning, and emerging white spaces. Continuously monitor shifts so you spot opportunities before anyone else.'
		},
		{
			title: 'Marketing Strategy',
			audience: 'Operators & Agencies',
			description:
				'Benchmark your brand against local competitors. Know which campaigns, channels, and price points are driving results in your market.'
		},
		{
			title: 'Expansion Planning',
			audience: 'Chains & Investors',
			description:
				'Evaluate locations with foot traffic, demographics, competition density, and rent data side by side. De-risk every new site decision.'
		},
		{
			title: 'Financial Modelling',
			audience: 'Operators & Investors',
			description:
				'Build projections grounded in real revenue benchmarks, occupancy rates, labor costs, and seasonality patterns — not assumptions.'
		},
		{
			title: 'Ops & Workforce',
			audience: 'Operators & Chains',
			description:
				'Track how your costs, staffing, and channel performance compare to the local market. Spot inefficiencies before they hit margins.'
		},
		{
			title: 'Sales & Leads',
			audience: 'Suppliers & Distributors',
			description:
				'Find restaurants that match your ideal customer profile, track new openings in your territory, and time your outreach with real demand signals.'
		},
		{
			title: 'Due Diligence',
			audience: 'Investors & Advisors',
			description:
				'Verify partners and vet investment opportunities with independent market data — revenue benchmarks, competitive positioning, and local demand signals.'
		},
		{
			title: 'Enrichment',
			audience: 'Tech Platforms',
			description:
				'Integrate hyper-local restaurant intelligence into your platform via API. Add market context, venue data, and competitive insights to your product.'
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
		class="flex h-10 w-10 cursor-pointer items-center justify-center rounded-full border border-cream-200 transition-colors hover:bg-cream-50 disabled:cursor-default disabled:opacity-30"
		aria-label="Previous"
	>
		<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
			<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
		</svg>
	</button>
	<button
		onclick={next}
		disabled={activeIndex === useCases.length - 1}
		class="flex h-10 w-10 cursor-pointer items-center justify-center rounded-full border border-cream-200 transition-colors hover:bg-cream-50 disabled:cursor-default disabled:opacity-30"
		aria-label="Next"
	>
		<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
			<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
		</svg>
	</button>
{/snippet}

<section id="use-cases" class="border-t border-cream-200 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<div class="mb-12 flex items-end justify-between">
			<div>
				<SectionHeader subtitle="Use Cases" title="Supporting decisions across all roles and functions" titleClass="max-w-2xl" />
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
				onmouseenter={() => hoveredIndex = i}
				onmouseleave={() => hoveredIndex = -1}
			>
				<div
					class="relative mb-5 flex aspect-[4/3] items-center justify-center overflow-hidden rounded-2xl bg-cream-100"
				>
					<CardCanvas
						active={hoveredIndex === i}
						seed={i}
						class="absolute inset-0 h-full w-full transition-opacity duration-500 {hoveredIndex === i ? 'opacity-100' : 'opacity-0'}"
					/>
					<UseCaseGraphics index={i} hovered={hoveredIndex === i} />
				</div>

				<p class="mb-1 text-xs font-medium text-black/25">{useCase.audience}</p>
				<h3 class="mb-2 text-lg font-medium tracking-[-0.01em] text-black">
					{useCase.title}
				</h3>
				<p class="pr-4 text-sm leading-snug text-black/60">
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
