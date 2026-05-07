<script lang="ts">
	import { pickPills, type TopicPillItem } from '$lib/topic-pills-shuffle';

	let {
		onPick,
		isMobile = false
	}: {
		onPick: (query: string) => void;
		isMobile?: boolean;
	} = $props();

	const PILL_POOL: TopicPillItem[] = [
		// Market context
		{
			label: 'Market sales shifts',
			mobile: 'Sales shifts',
			color: '#818cf8',
			query: 'Is a slow month just us or is the whole neighbourhood pulling back?'
		},
		{
			label: 'Seasonal demand patterns',
			mobile: 'Demand cycles',
			color: '#818cf8',
			query: 'How does demand in my area shift across seasons — and how should I plan for it?'
		},
		{
			label: 'Local market performance',
			mobile: 'Market pulse',
			color: '#818cf8',
			query: 'How is the local food and drink market performing compared to six months ago?'
		},
		// Site selection
		{
			label: "Who's getting the traffic",
			mobile: 'Foot traffic',
			color: '#a78bfa',
			query: 'What are the foot traffic patterns in my neighbourhood by day and daypart?'
		},
		{
			label: 'Best streets to open on',
			mobile: 'Best streets',
			color: '#a78bfa',
			query: 'Which streets or blocks near me have the highest foot traffic for hospitality?'
		},
		{
			label: 'Competition density',
			mobile: 'Competition',
			color: '#a78bfa',
			query: 'How saturated is the food and drink market within 1 km of this location?'
		},
		// Concept validation
		{
			label: 'Cuisine gaps in the area',
			mobile: 'Cuisine gaps',
			color: '#f472b6',
			query: 'What cuisine types are underrepresented near me that locals are searching for?'
		},
		{
			label: 'What concepts work here',
			mobile: 'Concepts here',
			color: '#f472b6',
			query: 'Which formats and cuisines are thriving in this neighbourhood?'
		},
		{
			label: 'Delivery demand signals',
			mobile: 'Delivery trends',
			color: '#f472b6',
			query: 'What delivery categories are growing fastest in my area right now?'
		},
		// Wage benchmarking
		{
			label: 'Salary benchmarks',
			mobile: 'Salaries',
			color: '#6ee7b3',
			query: 'What are restaurants near us actually paying for every role?'
		},
		{
			label: 'Chef pay in my area',
			mobile: 'Chef pay',
			color: '#6ee7b3',
			query: 'What are head chefs and sous chefs earning at comparable restaurants nearby?'
		},
		{
			label: 'Server wage trends',
			mobile: 'Server wages',
			color: '#6ee7b3',
			query: 'How have front-of-house wages changed in my area over the past year?'
		},
		// Price positioning
		{
			label: 'Menu price gaps',
			mobile: 'Price gaps',
			color: '#fbbf24',
			query: 'How does our menu pricing compare to competitors within 1 km?'
		},
		{
			label: 'Lunch price positioning',
			mobile: 'Lunch pricing',
			color: '#fbbf24',
			query: 'Where does my lunch menu sit price-wise compared to nearby competitors?'
		},
		{
			label: 'Drinks pricing landscape',
			mobile: 'Drinks pricing',
			color: '#fbbf24',
			query: 'How do my cocktail and wine prices compare to similar bars in the area?'
		},
		// Sentiment trends
		{
			label: 'What guests are saying',
			mobile: 'Guest reviews',
			color: '#fb923c',
			query: 'What are the real sentiment themes across our reviews and competitors?'
		},
		{
			label: 'Service complaint trends',
			mobile: 'Complaints',
			color: '#fb923c',
			query: 'What service issues keep coming up in reviews of places like mine?'
		},
		{
			label: 'What earns 5 stars nearby',
			mobile: '5-star formula',
			color: '#fb923c',
			query: 'What do the top-rated cafes near me have in common according to reviews?'
		},
		// Competitor tracking
		{
			label: 'Competitor menu changes',
			mobile: 'Menu changes',
			color: '#06b6d4',
			query: 'Have any competitors near me changed their menu or pricing recently?'
		},
		{
			label: 'New launches nearby',
			mobile: 'New launches',
			color: '#06b6d4',
			query: 'What new concepts have launched in my area in the last 3 months?'
		},
		{
			label: 'Who opened nearby',
			mobile: 'New openings',
			color: '#06b6d4',
			query: 'What has opened or closed in my area recently?'
		},
		// Market shifts
		{
			label: 'Closures in the area',
			mobile: 'Closures',
			color: '#f87171',
			query: 'What has closed nearby recently and what can I learn from it?'
		},
		{
			label: 'Format shifts happening',
			mobile: 'Format shifts',
			color: '#f87171',
			query:
				'Are restaurants in my area shifting formats — dine-in to fast-casual, adding delivery?'
		},
		{
			label: 'Emerging food trends',
			mobile: 'Food trends',
			color: '#f87171',
			query: 'What food trends are gaining traction in my market right now?'
		}
	];

	const VISIBLE_COUNT = 6;
	const STAGGER = 50;

	function byLabel(label: string): TopicPillItem {
		const p = PILL_POOL.find((x) => x.label === label);
		if (!p) throw new Error(`TopicPills: no pill with label "${label}"`);
		return p;
	}

	// Deterministic, wrap-balanced initial set. Order follows the short/long
	// interleave that pickPills applies on reshuffle (shortest, longest,
	// 2nd-shortest, 2nd-longest, mid-short, mid-long) so flex-wrap rows stay
	// balanced.
	const INITIAL_TOPICS: TopicPillItem[] = [
		'Who opened nearby',
		"Who's getting the traffic",
		'Emerging food trends',
		'Local market performance',
		'What guests are saying',
		'Lunch price positioning'
	].map(byLabel);

	let pillGen = $state(0);
	let topics = $state<TopicPillItem[]>(INITIAL_TOPICS);

	const firstDelay = $derived(pillGen === 0 ? 350 : 150);
	const buttonDelay = $derived(firstDelay + (VISIBLE_COUNT + 1) * STAGGER);

	function reshuffle() {
		pillGen++;
		topics = pickPills(PILL_POOL, VISIBLE_COUNT, isMobile);
	}
</script>

{#key pillGen}
	<!--
		max-width: 680px is load-bearing. Below ~673 the reshuffle button drops to
		its own row; above ~682 row 1 can fit 4 pills (the original 4+2 bug).
		Calibrated to current PILL_POOL label widths at 13px font — re-measure if
		pool, font size, or pill padding changes.
	-->
	<div class="mx-auto mt-12 flex flex-wrap justify-center gap-2 md:mt-12" style="max-width: 680px;">
		{#each topics as topic, i (topic.label)}
			<div
				class={pillGen === 0 ? 'pill-fade-slide' : 'pill-fade'}
				style="animation-delay: {firstDelay + i * STAGGER}ms"
			>
				<button
					onclick={() => onPick(topic.query)}
					class="topic-pill inline-flex items-center gap-2 rounded-full border border-black/[0.12] px-3.5 py-2 text-[13px] whitespace-nowrap text-black/55 transition-all duration-200 hover:border-black/[0.30] hover:text-black/75 active:border-black/[0.30] active:text-black/75 dark:border-white/[0.12] dark:text-white/55 dark:hover:border-white/[0.30] dark:hover:text-white/75 dark:active:border-white/[0.30] dark:active:text-white/75"
				>
					<span class="h-1.5 w-1.5 shrink-0 rounded-full" style="background-color: {topic.color}"
					></span>
					{isMobile ? topic.mobile : topic.label}
				</button>
			</div>
		{/each}
		<div
			class={pillGen === 0 ? 'pill-fade-slide' : 'pill-fade'}
			style="animation-delay: {buttonDelay}ms"
		>
			<button
				onclick={reshuffle}
				aria-label="Show different suggestions"
				class="shuffle-btn group inline-flex h-[34px] w-[34px] items-center justify-center rounded-full border border-black/[0.12] dark:border-white/[0.12]"
			>
				<svg
					class="h-3.5 w-3.5 text-black opacity-30 transition-opacity duration-200 group-hover:opacity-55 dark:text-white"
					xmlns="http://www.w3.org/2000/svg"
					fill="none"
					viewBox="0 0 24 24"
					stroke="currentColor"
					stroke-width="2"
					stroke-linecap="square"
					stroke-linejoin="miter"
				>
					<polyline points="23 4 23 10 17 10" />
					<path d="M21.17 8A9 9 0 0012 3 9 9 0 003 12a9 9 0 0016.5 5" />
				</svg>
			</button>
		</div>
	</div>
{/key}

<style>
	.pill-fade-slide {
		animation: fadeInSlide 0.7s ease-out both;
	}

	.pill-fade {
		animation: fadeIn 0.6s ease-out both;
	}

	@keyframes fadeInSlide {
		from {
			opacity: 0;
			transform: translateY(8px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	@keyframes fadeIn {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}

	.shuffle-btn svg {
		transition: transform 0.35s ease;
	}

	.shuffle-btn:active svg {
		transform: rotate(180deg);
	}
</style>
