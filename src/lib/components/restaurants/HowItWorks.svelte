<script lang="ts">
	import SectionHeader from '$lib/components/SectionHeader.svelte';
</script>

<section class="bg-cream-100 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<div class="mx-auto max-w-2xl text-center">
			<SectionHeader subtitle="How it works" title="From question to answer" titleClass="mx-auto" />
		</div>

		<div
			class="mt-16 grid grid-cols-1 border-t border-cream-200 md:grid-cols-3 md:divide-x md:divide-cream-200"
		>
			<div class="border-b border-cream-200 p-8 md:border-b-0 md:py-10 md:pr-10">
				<div class="mb-6 text-5xl font-black text-black/10 dark:text-white/10">1.</div>
				<h3 class="mb-3 text-lg font-medium text-black dark:text-white">We gather everything</h3>
				<p class="text-sm leading-relaxed text-black/55 dark:text-white/55">
					Delivery apps, review sites, foot traffic data, job postings, social media. Hundreds of
					sources monitored around the clock so you never have to.
				</p>
			</div>
			<div class="border-b border-cream-200 p-8 md:border-b-0 md:px-10 md:py-10">
				<div class="mb-6 text-5xl font-black text-black/10 dark:text-white/10">2.</div>
				<h3 class="mb-3 text-lg font-medium text-black dark:text-white">AI finds the signal</h3>
				<p class="text-sm leading-relaxed text-black/55 dark:text-white/55">
					Purpose-built agents process millions of data points into competitive benchmarks, trend
					alerts, and market-level insights specific to your locations.
				</p>
			</div>
			<div class="p-8 md:py-10 md:pl-10">
				<div class="mb-6 text-5xl font-black text-black/10 dark:text-white/10">3.</div>
				<h3 class="mb-3 text-lg font-medium text-black dark:text-white">Analysts make it useful</h3>
				<p class="text-sm leading-relaxed text-black/55 dark:text-white/55">
					Human experts review every insight before it reaches you. What you get is a plain-language
					brief, not a dashboard you'll never open.
				</p>
			</div>
		</div>
	</div>
</section>
