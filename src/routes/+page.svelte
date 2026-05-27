<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { chatState } from '$lib/chat-state.svelte';
	import { auth } from '$lib/auth.svelte';
	import Navbar from '$lib/components/Navbar.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import AccessForm from '$lib/components/AccessForm.svelte';
	import Seo from '$lib/components/Seo.svelte';
	import RestaurantHero from '$lib/components/restaurants/RestaurantHero.svelte';
	import About from '$lib/components/About.svelte';

	import UseCases from '$lib/components/UseCases.svelte';
	import DataSources from '$lib/components/DataSources.svelte';
	import RestaurantCTA from '$lib/components/restaurants/RestaurantCTA.svelte';

	let leaving = $state(false);
	let heroLeaving = $state(false);
	let heroQuery = $state('');
	let limitNotice = $state<string | null>(null);

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
		void auth.init().then(() => {
			// Touch the user-doc listener so `chatState.dailyChatLimitReached`
			// reflects the latest counter when the user has signed in already.
			if (auth.user) void chatState.sessionsList;
		});
	});

	function proceedToChat(
		query: string,
		place: { name: string; secondary: string; placeId: string } | null
	) {
		leaving = true;
		heroLeaving = true;
		chatState.startNewChat(query, place);
		goto('/chat');
	}

	function dailyLimitMessage() {
		return 'You’ve used your daily chat on the free plan. Come back tomorrow to start another.';
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
			// Wait for the first users/{uid} snapshot so the limit check sees
			// real state (not the brief pre-snapshot window where userDoc=null
			// and the getter would return false).
			await chatState.waitForUserDoc();
			if (chatState.dailyChatLimitReached) {
				limitNotice = dailyLimitMessage();
				return;
			}
			limitNotice = null;
			proceedToChat(query, place);
			return;
		}
		auth.saveDraft({ prompt: query, placeContext: place });
		auth.openModal({
			afterSignIn: async () => {
				await chatState.waitForUserDoc();
				if (chatState.dailyChatLimitReached) {
					limitNotice = dailyLimitMessage();
					return;
				}
				limitNotice = null;
				proceedToChat(query, place);
			}
		});
	}

	const agentUseCases = [
		{
			title: 'Market trends',
			graphicIndex: 2,
			description: `Track local demand cycles and competitor momentum. Separate venue performance from market movement, so decisions start from signal.`
		},
		{
			title: 'Expansion strategy',
			graphicIndex: 1,
			description: `Evaluate locations with foot traffic, demographics, competition density, and rent data mapped around each site.`
		},
		{
			title: 'Concept validation',
			graphicIndex: 7,
			description: `Validate new concepts against local signals. See what's working nearby and whether demand supports the idea before buildout.`
		},
		{
			title: 'Financial planning',
			graphicIndex: 3,
			description: `Project revenue, occupancy, and labor costs against local benchmarks. Spot spend and staffing gaps before they hit margins.`
		},
		{
			title: 'Price positioning',
			graphicIndex: 4,
			description: `Benchmark pricing against nearby competitors. See which price points, channels, and promos are driving results.`
		},
		{
			title: 'Sentiment analysis',
			graphicIndex: 5,
			description: `Connect review signals across venues. See which themes are growing, fading, or unique to a single location before they become ratings.`
		},
		{
			title: 'Competitor tracking',
			graphicIndex: 6,
			description:
				'Monitor competitor moves as they happen — menu changes, price shifts, new launches, and format pivots. Stay current without relying on word of mouth.'
		},
		{
			title: 'Market shifts',
			graphicIndex: 0,
			description: `Track openings, closures, and format changes across the local market. Spot white spaces where demand meets thin competition early.`
		}
	];
</script>

<Seo
	title="Superextra - Restaurant Market Intelligence"
	description="AI market intelligence for restaurants, synthesizing competitor, pricing, guest, delivery, and local market signals into operator-ready answers."
/>

<div class="page-exit" class:is-leaving={leaving}>
	<Navbar minimal />

	<main>
		<RestaurantHero onleave={handleLeave} bind:leaving={heroLeaving} bind:userQuery={heroQuery} />
		{#if limitNotice}
			<div
				class="mx-auto mt-2 max-w-[800px] px-6 text-center text-[13px] text-black/65 dark:text-white/65"
				role="alert"
			>
				{limitNotice}
			</div>
		{/if}
		<About
			headline="The market view your restaurant has been missing"
			intro="Restaurant operators make critical decisions every day — where to open, how to price, when to hire — too often without a clear view of the market around them at all. Superextra changes that."
			description="Our AI models synthesize competitor, pricing, guest, delivery, and market signals into an external intelligence layer for your restaurant. Better context behind better decisions."
			class="border-t border-cream-200 md:border-t-0"
		/>
		<UseCases
			items={agentUseCases}
			title="The questions you've been asking – answered"
			titleClass="max-w-2xl"
			subtitleClass="text-xs"
		/>
		<DataSources
			title="Only credible data sources"
			subtitle="Reviewed and validated information you can rely on."
		/>
		<RestaurantCTA />
	</main>

	<Footer borderless />
	<AccessForm />
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
