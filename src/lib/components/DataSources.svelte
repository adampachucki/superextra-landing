<script lang="ts">
	let {
		title = 'Powered by dozens of data sources',
		subtitle = 'We aggregate, cross-reference, and validate data from public platforms, proprietary databases, and official registries across every market we cover.'
	}: { title?: string; subtitle?: string } = $props();

	const sources = [
		{ name: 'TripAdvisor', logo: 'tripadvisor' },
		{ name: 'OpenTable', logo: 'opentable' },
		{ name: 'Yelp', logo: 'yelp' },
		{ name: 'TheFork', logo: 'thefork' },
		{ name: 'Michelin Guide', logo: 'michelin' },
		{ name: 'Zomato', logo: 'zomato' },
		{ name: 'Google Maps', logo: 'googlemaps' },
		{ name: 'OpenStreetMap', logo: 'openstreetmap' },
		{ name: 'Foursquare', logo: 'foursquare' },
		{ name: 'Finebite', logo: 'finebite' },
		{ name: 'Instagram', logo: 'instagram' },
		{ name: 'Facebook', logo: 'facebook' },
		{ name: 'TikTok', logo: 'tiktok' },
		{ name: 'Uber Eats', logo: 'ubereats' },
		{ name: 'Wolt', logo: 'wolt' },
		{ name: 'Just Eat', logo: 'justeat' },
		{ name: 'Glovo', logo: 'glovo' },
		{ name: 'CEIDG / KRS', logo: 'ceidg' },
		{ name: 'Handelsregister', logo: 'handelsregister' },
		{ name: 'Companies House', logo: 'companieshouse' },
		{ name: 'SEC / EDGAR', logo: 'sec' },
		{ name: 'Statista', logo: 'statista' },
		{ name: 'Deloitte', logo: 'deloitte' },
		{ name: 'NielsenIQ', logo: 'nielseniq' },
		{ name: 'Eurostat', logo: 'eurostat' },
		{ name: 'IBISWorld', logo: 'ibisworld' },
		{ name: 'Krajowy Rejestr Długów', logo: 'krd' },
		{ name: 'Dun & Bradstreet', logo: 'dnb' },
		{ name: 'Creditreform', logo: 'creditreform' }
	];
</script>

<section class="border-t border-cream-200 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<div class="mb-16 text-center">
			<h2
				class="text-[clamp(2rem,4vw,3.25rem)] leading-[1.1] font-normal tracking-[-0.02em] text-black dark:text-white"
			>
				{title}
			</h2>
			{#if subtitle}
				<p
					class="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-black/60 dark:text-white/60"
				>
					{subtitle}
				</p>
			{/if}
		</div>

		<div
			class="grid grid-cols-3 gap-px overflow-hidden border-t border-cream-200 bg-cream-200 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6"
		>
			{#each sources as source}
				<div
					class="group flex items-center justify-center bg-cream px-3 py-5 sm:px-5 sm:py-8"
					title={source.name}
				>
					<img
						src="/logos/{source.logo}.svg"
						alt={source.name}
						class="h-5 max-w-[80px] object-contain opacity-50 transition-opacity group-hover:opacity-90 sm:h-6 sm:max-w-[100px] md:h-7 md:max-w-[120px] dark:invert"
					/>
				</div>
			{/each}

			<!-- "And more" cell -->
			<div class="flex items-center justify-center bg-cream px-3 py-5 sm:px-5 sm:py-8">
				<span class="text-sm text-black/40 dark:text-white/40">And more</span>
			</div>
		</div>
	</div>
</section>
