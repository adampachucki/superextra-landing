<script lang="ts">
	import type { PlaceSuggestion } from '$lib/place-search.svelte';
	import TopicPills from './TopicPills.svelte';
	import RestaurantPromptComposer from './RestaurantPromptComposer.svelte';

	let isMobile = $state(false);
	$effect(() => {
		const mq = window.matchMedia('(max-width: 767px)');
		isMobile = mq.matches;
		const handler = (e: MediaQueryListEvent) => {
			isMobile = e.matches;
		};
		mq.addEventListener('change', handler);
		return () => mq.removeEventListener('change', handler);
	});

	let {
		onleave,
		userQuery = $bindable('')
	}: {
		onleave?: (detail: { query: string; place: PlaceSuggestion | null }) => void;
		userQuery?: string;
	} = $props();

	function handleSubmit(detail: { query: string; place: PlaceSuggestion | null }) {
		onleave?.(detail);
	}

	function selectTopic(query: string) {
		userQuery = query;
	}
</script>

<section class="pt-32 md:pt-40">
	<div class="mx-auto max-w-[1200px] px-6">
		<!-- Headline -->
		<h1
			class="hero-fade mx-auto text-center font-semibold tracking-[-0.04em] text-black md:max-w-none dark:text-white"
			style="font-size: clamp(3rem, 6vw, 5.25rem); line-height: 1.02; animation-delay: 100ms;"
		>
			AI consultant <br class="max-md:hidden" />for every restaurant
		</h1>

		<!-- Subheadline -->
		<p
			class="hero-fade mx-auto mt-6 text-center text-lg leading-snug text-black/60 md:text-xl dark:text-white/60"
			style="max-width: 540px; animation-delay: 170ms;"
		>
			Stop relying on gossip and gut feel. Get clear answers about your competitors, pricing, and
			demand in minutes.
		</p>

		<!-- Prompt card -->
		<div
			class="prompt-fade relative z-20 mx-auto mt-10 md:mt-12"
			style="max-width: 650px; animation-delay: 280ms;"
		>
			<RestaurantPromptComposer
				bind:query={userQuery}
				{isMobile}
				autofocusMode="desktop"
				focusOnQueryChange
				onSubmit={handleSubmit}
			/>
		</div>

		<!-- Topic suggestion pills -->
		<TopicPills onPick={selectTopic} {isMobile} />
	</div>
</section>

<div class="h-24 md:h-36"></div>

<style>
	.hero-fade {
		animation: fadeIn 0.7s ease-out both;
	}

	@keyframes fadeIn {
		from {
			opacity: 0;
			transform: translateY(8px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.prompt-fade {
		animation: fadeIn 0.6s ease-out both;
	}
</style>
