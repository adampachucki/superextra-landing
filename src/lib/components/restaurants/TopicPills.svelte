<script lang="ts">
	import { browser } from '$app/environment';
	import { pickPills, pickPillsWithCategory, type TopicPillItem } from '$lib/topic-pills-shuffle';
	import { campaignCategory } from '$lib/campaign';
	import * as m from '$lib/paraglide/messages';

	let {
		onPick,
		isMobile = false
	}: {
		onPick: (query: string) => void;
		isMobile?: boolean;
	} = $props();

	// Labels/queries come from the message catalog (localized). `id` is the
	// stable key used for shuffling and the deterministic initial set;
	// `category` maps to a hook pillar so ad clicks land on a matching set.
	const PILL_POOL: TopicPillItem[] = [
		// Market trends
		{
			id: 'sales_shifts',
			category: 'market_trends',
			label: m.pill_sales_shifts_label(),
			mobile: m.pill_sales_shifts_short(),
			color: '#818cf8',
			query: m.pill_sales_shifts_q()
		},
		{
			id: 'demand_cycles',
			category: 'market_trends',
			label: m.pill_demand_cycles_label(),
			mobile: m.pill_demand_cycles_short(),
			color: '#818cf8',
			query: m.pill_demand_cycles_q()
		},
		{
			id: 'market_pulse',
			category: 'market_trends',
			label: m.pill_market_pulse_label(),
			mobile: m.pill_market_pulse_short(),
			color: '#818cf8',
			query: m.pill_market_pulse_q()
		},
		// Site selection
		{
			id: 'foot_traffic',
			category: 'site_selection',
			label: m.pill_foot_traffic_label(),
			mobile: m.pill_foot_traffic_short(),
			color: '#a78bfa',
			query: m.pill_foot_traffic_q()
		},
		{
			id: 'best_streets',
			category: 'site_selection',
			label: m.pill_best_streets_label(),
			mobile: m.pill_best_streets_short(),
			color: '#a78bfa',
			query: m.pill_best_streets_q()
		},
		{
			id: 'competition',
			category: 'site_selection',
			label: m.pill_competition_label(),
			mobile: m.pill_competition_short(),
			color: '#a78bfa',
			query: m.pill_competition_q()
		},
		// Concept validation
		{
			id: 'cuisine_gaps',
			category: 'concept',
			label: m.pill_cuisine_gaps_label(),
			mobile: m.pill_cuisine_gaps_short(),
			color: '#f472b6',
			query: m.pill_cuisine_gaps_q()
		},
		{
			id: 'concepts_here',
			category: 'concept',
			label: m.pill_concepts_here_label(),
			mobile: m.pill_concepts_here_short(),
			color: '#f472b6',
			query: m.pill_concepts_here_q()
		},
		{
			id: 'delivery_trends',
			category: 'concept',
			label: m.pill_delivery_trends_label(),
			mobile: m.pill_delivery_trends_short(),
			color: '#f472b6',
			query: m.pill_delivery_trends_q()
		},
		// Wage benchmarking
		{
			id: 'salaries',
			category: 'wage',
			label: m.pill_salaries_label(),
			mobile: m.pill_salaries_short(),
			color: '#6ee7b3',
			query: m.pill_salaries_q()
		},
		{
			id: 'chef_pay',
			category: 'wage',
			label: m.pill_chef_pay_label(),
			mobile: m.pill_chef_pay_short(),
			color: '#6ee7b3',
			query: m.pill_chef_pay_q()
		},
		{
			id: 'server_wages',
			category: 'wage',
			label: m.pill_server_wages_label(),
			mobile: m.pill_server_wages_short(),
			color: '#6ee7b3',
			query: m.pill_server_wages_q()
		},
		// Price positioning
		{
			id: 'price_gaps',
			category: 'pricing',
			label: m.pill_price_gaps_label(),
			mobile: m.pill_price_gaps_short(),
			color: '#fbbf24',
			query: m.pill_price_gaps_q()
		},
		{
			id: 'lunch_pricing',
			category: 'pricing',
			label: m.pill_lunch_pricing_label(),
			mobile: m.pill_lunch_pricing_short(),
			color: '#fbbf24',
			query: m.pill_lunch_pricing_q()
		},
		{
			id: 'drinks_pricing',
			category: 'pricing',
			label: m.pill_drinks_pricing_label(),
			mobile: m.pill_drinks_pricing_short(),
			color: '#fbbf24',
			query: m.pill_drinks_pricing_q()
		},
		// Sentiment analysis
		{
			id: 'guest_reviews',
			category: 'sentiment',
			label: m.pill_guest_reviews_label(),
			mobile: m.pill_guest_reviews_short(),
			color: '#fb923c',
			query: m.pill_guest_reviews_q()
		},
		{
			id: 'complaints',
			category: 'sentiment',
			label: m.pill_complaints_label(),
			mobile: m.pill_complaints_short(),
			color: '#fb923c',
			query: m.pill_complaints_q()
		},
		{
			id: 'five_star',
			category: 'sentiment',
			label: m.pill_five_star_label(),
			mobile: m.pill_five_star_short(),
			color: '#fb923c',
			query: m.pill_five_star_q()
		},
		// Competitor tracking
		{
			id: 'menu_changes',
			category: 'competitor',
			label: m.pill_menu_changes_label(),
			mobile: m.pill_menu_changes_short(),
			color: '#06b6d4',
			query: m.pill_menu_changes_q()
		},
		{
			id: 'new_launches',
			category: 'competitor',
			label: m.pill_new_launches_label(),
			mobile: m.pill_new_launches_short(),
			color: '#06b6d4',
			query: m.pill_new_launches_q()
		},
		{
			id: 'new_openings',
			category: 'competitor',
			label: m.pill_new_openings_label(),
			mobile: m.pill_new_openings_short(),
			color: '#06b6d4',
			query: m.pill_new_openings_q()
		},
		// Market shifts
		{
			id: 'closures',
			category: 'market_shifts',
			label: m.pill_closures_label(),
			mobile: m.pill_closures_short(),
			color: '#f87171',
			query: m.pill_closures_q()
		},
		{
			id: 'format_shifts',
			category: 'market_shifts',
			label: m.pill_format_shifts_label(),
			mobile: m.pill_format_shifts_short(),
			color: '#f87171',
			query: m.pill_format_shifts_q()
		},
		{
			id: 'food_trends',
			category: 'market_shifts',
			label: m.pill_food_trends_label(),
			mobile: m.pill_food_trends_short(),
			color: '#f87171',
			query: m.pill_food_trends_q()
		}
	];

	const VISIBLE_COUNT = 6;
	const STAGGER = 50;

	function byId(id: string): TopicPillItem {
		const p = PILL_POOL.find((x) => x.id === id);
		if (!p) throw new Error(`TopicPills: no pill with id "${id}"`);
		return p;
	}

	// Deterministic, wrap-balanced initial set. Order follows the short/long
	// interleave that pickPills applies on reshuffle (shortest, longest,
	// 2nd-shortest, 2nd-longest, mid-short, mid-long) so flex-wrap rows stay
	// balanced.
	const DEFAULT_INITIAL: TopicPillItem[] = [
		'new_openings',
		'foot_traffic',
		'food_trends',
		'market_pulse',
		'guest_reviews',
		'lunch_pricing'
	].map(byId);

	// If the visitor arrived via a recognized ad campaign, seed the initial
	// pills with that hook's category so the click→prompt path is coherent.
	// Mobile-length interleave only applies to reshuffle; the initial render
	// is one-shot, so desktop wrap-balance is fine.
	const initialCategory = browser ? campaignCategory() : null;
	const INITIAL_TOPICS: TopicPillItem[] = initialCategory
		? pickPillsWithCategory(PILL_POOL, initialCategory, VISIBLE_COUNT)
		: DEFAULT_INITIAL;

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
				aria-label={m.pills_reshuffle()}
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
