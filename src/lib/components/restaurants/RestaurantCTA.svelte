<script lang="ts">
	import { formState } from '$lib/form-state.svelte';
</script>

<section class="border-t border-cream-200 py-24 md:py-32">
	<div class="mx-auto max-w-2xl px-6 text-center">
		<h2 class="text-[clamp(1.75rem,3.5vw,2.75rem)] leading-[1.1] font-medium tracking-[-0.02em] text-black dark:text-white">
			Start with a question
		</h2>
		<p class="mt-4 text-lg text-black/50 dark:text-white/50">
			Limited early access is now open.
		</p>
		<button
			onclick={() => formState.open()}
			class="mt-8 inline-flex cursor-pointer items-center gap-2 btn-primary px-8 py-3.5 text-sm"
		>
			Get Started
		</button>
	</div>
</section>
