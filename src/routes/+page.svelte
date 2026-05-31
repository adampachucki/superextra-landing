<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { chatState } from '$lib/chat-state.svelte';
	import { auth } from '$lib/auth.svelte';
	import Navbar from '$lib/components/Navbar.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import Seo from '$lib/components/Seo.svelte';
	import RestaurantHero from '$lib/components/restaurants/RestaurantHero.svelte';
	import About from '$lib/components/About.svelte';

	import UseCases from '$lib/components/UseCases.svelte';
	import DataSources from '$lib/components/DataSources.svelte';
	import RestaurantCTA from '$lib/components/restaurants/RestaurantCTA.svelte';
	import * as m from '$lib/paraglide/messages';

	let leaving = $state(false);
	let heroQuery = $state('');

	// The composer clears its own query on submit; restore it from the saved
	// draft when the sign-in modal closes without completing sign-in so the
	// user doesn't lose what they typed.
	$effect(() => {
		if (!auth.modalVisible && !auth.user) {
			const draft = auth.peekDraft();
			if (draft) heroQuery = draft.prompt;
		}
	});

	onMount(() => {
		void auth.init();
		const q = new URLSearchParams(window.location.search).get('q');
		if (q) heroQuery = q;
	});

	function proceedToChat(
		query: string,
		place: { name: string; secondary: string; placeId: string } | null
	) {
		// Daily research-runs limits are enforced inside the agent's
		// research_pipeline (see agent/superextra_agent/quota_gate.py). Limit-
		// reached cases land as a normal agent reply in the chat thread.
		leaving = true;
		chatState.startNewChat(query, place);
		goto('/chat');
	}

	async function handleLeave({
		query,
		place
	}: {
		query: string;
		place: { name: string; secondary: string; placeId: string } | null;
	}) {
		await auth.init();
		if (auth.user) {
			proceedToChat(query, place);
			return;
		}
		auth.saveDraft({ prompt: query, placeContext: place });
		auth.openModal({
			afterSignIn: () => proceedToChat(query, place)
		});
	}

	const agentUseCases = [
		{ title: m.uc_market_trends_title(), graphicIndex: 2, description: m.uc_market_trends_desc() },
		{ title: m.uc_expansion_title(), graphicIndex: 1, description: m.uc_expansion_desc() },
		{ title: m.uc_concept_title(), graphicIndex: 7, description: m.uc_concept_desc() },
		{ title: m.uc_financial_title(), graphicIndex: 3, description: m.uc_financial_desc() },
		{ title: m.uc_price_title(), graphicIndex: 4, description: m.uc_price_desc() },
		{ title: m.uc_sentiment_title(), graphicIndex: 5, description: m.uc_sentiment_desc() },
		{ title: m.uc_competitor_title(), graphicIndex: 6, description: m.uc_competitor_desc() },
		{ title: m.uc_shifts_title(), graphicIndex: 0, description: m.uc_shifts_desc() }
	];
</script>

<Seo title={m.seo_home_title()} description={m.seo_home_desc()} />

<div class="page-exit" class:is-leaving={leaving}>
	<Navbar />

	<main>
		<RestaurantHero onleave={handleLeave} bind:userQuery={heroQuery} />
		<About
			headline={m.about_home_headline()}
			intro={m.about_home_intro()}
			description={m.about_home_desc()}
			class="border-t border-cream-200 md:border-t-0"
		/>
		<UseCases
			items={agentUseCases}
			title={m.uc_home_title()}
			titleClass="max-w-2xl"
			subtitleClass="text-xs"
		/>
		<DataSources title={m.ds_home_title()} subtitle={m.ds_home_sub()} />
		<RestaurantCTA />
	</main>

	<Footer borderless />
</div>

<style>
	.page-exit {
		transition:
			opacity 0.25s cubic-bezier(0.4, 0, 1, 1),
			transform 0.25s cubic-bezier(0.4, 0, 1, 1),
			filter 0.25s cubic-bezier(0.4, 0, 1, 1);
	}

	.page-exit.is-leaving {
		opacity: 0;
		transform: scale(0.98) translateY(-8px);
		filter: blur(4px);
		pointer-events: none;
	}
</style>
