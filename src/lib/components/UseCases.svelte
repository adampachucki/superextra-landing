<script lang="ts">
	let scrollContainer: HTMLDivElement;
	let activeIndex = $state(0);

	const useCases = [
		{
			title: 'Market Research',
			description:
				'Map your competitive landscape. Track openings, closings, and emerging concepts to understand where your market is heading.',
			image: '/ppl/image1.webp'
		},
		{
			title: 'Marketing Strategy',
			description:
				'Benchmark competitor campaigns and social presence. Allocate spend with confidence using real local market data.',
			image: '/ppl/image2.webp'
		},
		{
			title: 'Site Selection',
			description:
				'Evaluate foot traffic, demographics, rent trends, and competition density to pinpoint your next winning location.',
			image: '/ppl/image3.webp'
		},
		{
			title: 'Pricing Strategy',
			description:
				'Monitor competitor menus and track price positioning across channels. Find the sweet spot between margin and volume.',
			image: '/ppl/image4.webp'
		},
		{
			title: 'Financial Modeling',
			description:
				'Build projections grounded in real revenue estimates, occupancy benchmarks, and market-derived cost assumptions.',
			image: '/ppl/image5.webp'
		},
		{
			title: 'Operations',
			description:
				'Benchmark labor costs, supplier pricing, and channel performance to run leaner and more profitably.',
			image: '/ppl/image6.webp'
		},
		{
			title: 'Workforce Planning',
			description:
				'Access local salary benchmarks, labor availability, and turnover rates to build and retain the right team.',
			image: '/ppl/image7.webp'
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

<section id="use-cases" class="border-t border-gray-200 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<div class="mb-12 flex items-end justify-between">
			<div>
				<p class="mb-6 text-sm font-medium uppercase tracking-widest text-black/40">Use Cases</p>
				<h2
					class="max-w-xl text-[clamp(2rem,4vw,3.25rem)] leading-[1.1] font-normal tracking-[-0.02em] text-black"
				>
					Built to support every role and function
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
					class="relative mb-5 flex aspect-[4/3] items-end overflow-hidden rounded-2xl bg-[#c8c5ca]"
				>
					<img
						src={useCase.image}
						alt={useCase.title}
						class="absolute inset-0 h-full w-full object-cover object-top"
					/>
					<div class="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-transparent"></div>

					<h3
						class="relative z-10 p-5 text-[clamp(1.5rem,3vw,2rem)] leading-[1.05] font-semibold tracking-[-0.02em] text-white md:p-6"
					>
						{useCase.title}
					</h3>
				</div>

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
