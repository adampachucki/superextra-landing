<script lang="ts">
	import MarketLandscapeV1 from '$lib/components/mockups/MarketLandscapeV1.svelte';
	import MarketLandscapeV2 from '$lib/components/mockups/MarketLandscapeV2.svelte';
	import MarketLandscapeV3 from '$lib/components/mockups/MarketLandscapeV3.svelte';

	const cards = [
		{
			id: 'market-landscape',
			title: 'Market Landscape',
			desc: "Who's opening, closing, and gaining ground — benchmarked against relevant cohorts.",
			variants: [
				{ label: 'V1 — Ranked Bar Chart', component: MarketLandscapeV1 },
				{ label: 'V2 — Bubble Position Map', component: MarketLandscapeV2 },
				{ label: 'V3 — Movement Tracker', component: MarketLandscapeV3 }
			]
		}
	];
</script>

<svelte:head>
	<title>Mockups — Superextra</title>
</svelte:head>

<div class="min-h-screen bg-[#f0efed] py-12">
	<div class="mx-auto max-w-[1400px] px-6">
		<header class="mb-12">
			<a href="/" class="text-sm text-black/40 hover:text-black/60 transition-colors">&larr; Back to site</a>
			<h1 class="mt-4 text-3xl font-medium text-black">Card Mockup Variants</h1>
			<p class="mt-2 text-base text-black/50">Compare design directions for each platform card.</p>
		</header>

		{#each cards as card}
			<section class="mb-16">
				<h2 class="text-xl font-medium text-black mb-2">{card.title}</h2>
				<p class="text-sm text-black/50 mb-8">{card.desc}</p>

				<div class="grid grid-cols-1 gap-6 md:grid-cols-3">
					{#each card.variants as variant}
						<div>
							<p class="text-xs font-medium text-black/40 mb-3 uppercase tracking-wide">{variant.label}</p>
							<div class="card">
								<div class="card-text">
									<h3 class="title">{card.title}</h3>
									<p class="desc">{card.desc}</p>
								</div>
								<div class="mockup">
									<variant.component />
								</div>
							</div>
						</div>
					{/each}
				</div>
			</section>
		{/each}
	</div>
</div>

<style>
	.card {
		border-radius: 1rem;
		background: var(--color-cream-100);
		border: 1px solid rgba(0, 0, 0, 0.03);
		padding: 1.75rem 1.75rem;
		padding-bottom: 0;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.card-text {
		height: 5.25rem;
		margin-bottom: 2.5rem;
		overflow: hidden;
		flex-shrink: 0;
	}
	@media (max-width: 767px) {
		.card-text {
			height: auto;
			overflow: visible;
		}
	}

	.title {
		font-size: 1.25rem;
		font-weight: 500;
		color: #000;
	}

	.desc {
		font-size: 0.875rem;
		line-height: 1.5;
		margin-top: 0.25rem;
		color: rgba(0, 0, 0, 0.6);
	}

	.mockup {
		border-radius: 0.75rem 0.75rem 0 0;
		background: #fff;
		border: 1px solid rgba(0, 0, 0, 0.08);
		border-bottom: none;
		margin-bottom: -3.5rem;
		display: flex;
		flex-direction: column;
		flex: 1;
	}
</style>
