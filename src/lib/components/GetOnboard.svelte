<script lang="ts">
	import SectionHeader from './SectionHeader.svelte';
	import * as m from '$lib/paraglide/messages';
</script>

<section id="get-onboard" class="border-t border-cream-200 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<SectionHeader
			subtitle={m.onboard_subtitle()}
			title={m.onboard_title()}
			titleClass="mb-16 max-w-2xl"
		/>

		<div
			class="grid grid-cols-1 gap-0 border-t border-cream-200 md:grid-cols-3 md:divide-x md:divide-cream-200"
		>
			<div class="border-b border-cream-200 p-8 md:border-b-0 md:py-10 md:pr-10">
				<div class="mb-6 text-5xl font-black text-black/10 dark:text-white/10">1.</div>
				<h3 class="mb-3 text-lg font-medium text-black dark:text-white">
					{m.onboard_step1_title()}
				</h3>
				<p class="text-sm leading-snug text-black/60 dark:text-white/60">
					{m.onboard_step1_desc()}
				</p>
			</div>
			<div class="border-b border-cream-200 p-8 md:border-b-0 md:px-10 md:py-10">
				<div class="mb-6 text-5xl font-black text-black/10 dark:text-white/10">2.</div>
				<h3 class="mb-3 text-lg font-medium text-black dark:text-white">
					{m.onboard_step2_title()}
				</h3>
				<p class="text-sm leading-snug text-black/60 dark:text-white/60">
					{m.onboard_step2_desc()}
				</p>
			</div>
			<div class="p-8 md:py-10 md:pl-10">
				<div class="mb-6 text-5xl font-black text-black/10 dark:text-white/10">3.</div>
				<h3 class="mb-3 text-lg font-medium text-black dark:text-white">
					{m.onboard_step3_title()}
				</h3>
				<p class="text-sm leading-snug text-black/60 dark:text-white/60">
					{m.onboard_step3_desc()}
				</p>
			</div>
		</div>
	</div>
</section>
