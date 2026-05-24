<script lang="ts">
	import SectionHeader from './SectionHeader.svelte';
</script>

<section id="get-onboard" class="border-t border-cream-200 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<SectionHeader
			subtitle="Book a demo"
			title="See Superextra on a real restaurant decision"
			titleClass="mb-16 max-w-2xl"
		/>

		<div
			class="grid grid-cols-1 gap-0 border-t border-cream-200 md:grid-cols-3 md:divide-x md:divide-cream-200"
		>
			<div class="border-b border-cream-200 p-8 md:border-b-0 md:py-10 md:pr-10">
				<div class="mb-6 text-5xl font-black text-black/10 dark:text-white/10">1.</div>
				<h3 class="mb-3 text-lg font-medium text-black dark:text-white">Share business context</h3>
				<p class="text-sm leading-snug text-black/60 dark:text-white/60">
					A few details set the demo around the right market, format, and decision.
				</p>
			</div>
			<div class="border-b border-cream-200 p-8 md:border-b-0 md:px-10 md:py-10">
				<div class="mb-6 text-5xl font-black text-black/10 dark:text-white/10">2.</div>
				<h3 class="mb-3 text-lg font-medium text-black dark:text-white">Talk through the market</h3>
				<p class="text-sm leading-snug text-black/60 dark:text-white/60">
					The team maps the competitor, pricing, guest, delivery, and location signals that matter
					for the demo.
				</p>
			</div>
			<div class="p-8 md:py-10 md:pl-10">
				<div class="mb-6 text-5xl font-black text-black/10 dark:text-white/10">3.</div>
				<h3 class="mb-3 text-lg font-medium text-black dark:text-white">Leave with next steps</h3>
				<p class="text-sm leading-snug text-black/60 dark:text-white/60">
					Review a focused intelligence workflow and the reports or agent setup needed for ongoing
					monitoring.
				</p>
			</div>
		</div>
	</div>
</section>
