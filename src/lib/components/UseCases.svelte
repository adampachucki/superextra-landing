<script lang="ts">
	import UseCaseGraphics from './UseCaseGraphics.svelte';
	import CardCanvas from './CardCanvas.svelte';
	import SectionHeader from './SectionHeader.svelte';
	import * as m from '$lib/paraglide/messages';

	let {
		items,
		subtitle = m.uc_def_subtitle(),
		title = m.uc_def_title(),
		titleClass = 'max-w-2xl',
		subtitleClass = ''
	}: {
		items?: { title: string; audience?: string; description: string; graphicIndex?: number }[];
		subtitle?: string;
		title?: string;
		titleClass?: string;
		subtitleClass?: string;
	} = $props();

	let scrollContainer: HTMLDivElement;
	let activeIndex = $state(0);
	let hoveredIndex = $state(-1);
	let isMobile = $state(false);

	$effect(() => {
		const mq = window.matchMedia('(max-width: 767px)');
		isMobile = mq.matches;
		const handler = (e: MediaQueryListEvent) => (isMobile = e.matches);
		mq.addEventListener('change', handler);
		return () => mq.removeEventListener('change', handler);
	});

	let effectiveHovered = $derived(isMobile && hoveredIndex === -1 ? activeIndex : hoveredIndex);

	const defaultUseCases: {
		title: string;
		audience?: string;
		description: string;
		graphicIndex?: number;
	}[] = [
		{
			title: m.ucd_marketing_title(),
			audience: m.ucd_marketing_audience(),
			description: m.ucd_marketing_desc()
		},
		{
			title: m.ucd_expansion_title(),
			audience: m.ucd_expansion_audience(),
			description: m.ucd_expansion_desc()
		},
		{
			title: m.ucd_research_title(),
			audience: m.ucd_research_audience(),
			description: m.ucd_research_desc()
		},
		{ title: m.ucd_ops_title(), audience: m.ucd_ops_audience(), description: m.ucd_ops_desc() },
		{
			title: m.ucd_financial_title(),
			audience: m.ucd_financial_audience(),
			description: m.ucd_financial_desc()
		},
		{
			title: m.ucd_sales_title(),
			audience: m.ucd_sales_audience(),
			description: m.ucd_sales_desc()
		},
		{
			title: m.ucd_diligence_title(),
			audience: m.ucd_diligence_audience(),
			description: m.ucd_diligence_desc()
		},
		{
			title: m.ucd_enrich_title(),
			audience: m.ucd_enrich_audience(),
			description: m.ucd_enrich_desc()
		}
	];

	let useCases = $derived(items ?? defaultUseCases);

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
		class="flex h-10 w-10 items-center justify-center rounded-full border border-cream-200 transition-colors hover:bg-cream-50 disabled:opacity-30"
		aria-label={m.uc_prev()}
	>
		<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
			<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
		</svg>
	</button>
	<button
		onclick={next}
		disabled={activeIndex === useCases.length - 1}
		class="flex h-10 w-10 items-center justify-center rounded-full border border-cream-200 transition-colors hover:bg-cream-50 disabled:opacity-30"
		aria-label={m.uc_next()}
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
				<SectionHeader {subtitle} {title} {titleClass} {subtitleClass} />
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
				role="presentation"
				class="w-[min(75vw,380px)] flex-shrink-0"
				style="{i === 0 ? 'margin-left: var(--content-inset)' : ''}{i === useCases.length - 1
					? 'margin-right: var(--content-inset)'
					: ''}"
				onmouseenter={() => (hoveredIndex = i)}
				onmouseleave={() => (hoveredIndex = -1)}
			>
				<div
					class="relative mb-5 flex aspect-[4/3] items-center justify-center overflow-hidden rounded-2xl border-[0.5px] border-black/[0.03] bg-cream-100 dark:border-white/[0.03]"
				>
					<CardCanvas
						active={effectiveHovered === i}
						seed={i}
						class="absolute inset-0 h-full w-full transition-opacity duration-500 {effectiveHovered ===
						i
							? 'opacity-100'
							: 'opacity-0'}"
					/>
					<UseCaseGraphics index={useCase.graphicIndex ?? i} hovered={effectiveHovered === i} />
				</div>

				{#if useCase.audience}<p class="mb-1 text-xs font-medium text-black/25 dark:text-white/25">
						{useCase.audience}
					</p>{/if}
				<h3 class="mb-2 text-lg font-medium tracking-[-0.01em] text-black dark:text-white">
					{useCase.title}
				</h3>
				<p class="pr-4 text-sm leading-snug text-black/60 dark:text-white/60">
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
