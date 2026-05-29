<script lang="ts">
	import * as m from '$lib/paraglide/messages';

	let {
		headline = m.about_def_headline(),
		intro = m.about_def_intro(),
		description = m.about_def_desc(),
		class: className = ''
	}: {
		headline?: string;
		intro?: string;
		description?: string;
		class?: string;
	} = $props();
</script>

<section class="py-24 md:py-32 {className}">
	<div class="mx-auto max-w-[1200px] px-6">
		<p class="mb-6 text-sm font-medium tracking-widest text-black/40 uppercase dark:text-white/40">
			{m.about_label()}
		</p>

		<div class="grid grid-cols-1 gap-12 lg:grid-cols-2 lg:gap-20">
			<h2 class="heading-display text-black dark:text-white">
				{headline}
			</h2>

			<div class="space-y-6">
				<p class="text-lg leading-snug text-black/60 dark:text-white/60">
					{intro}
				</p>
				<p class="text-lg leading-snug text-black/60 dark:text-white/60">
					{description}
				</p>
				<p class="text-lg leading-snug font-medium text-black dark:text-white">
					{m.about_tagline()}
				</p>
			</div>
		</div>
	</div>
</section>
