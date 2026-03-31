<script lang="ts">
	import { formState } from '$lib/form-state.svelte';
</script>

<section class="border-t border-cream-200 py-16">
	<div
		class="mx-auto flex max-w-[1200px] flex-col items-center justify-between gap-6 px-6 md:flex-row"
	>
		<p class="text-center text-lg font-medium text-black md:text-left dark:text-white">
			Early access is now open. Limited spots available.
		</p>
		<div class="flex items-center gap-3">
			<a
				href="/login"
				class="cursor-pointer rounded-full border border-black/10 px-6 py-2.5 text-sm font-medium text-black/70 transition-all hover:border-black/15 hover:text-black/90 dark:border-white/10 dark:text-white/70 dark:hover:border-white/15 dark:hover:text-white/90"
				>Log In</a
			>
			<button
				onclick={() => formState.open()}
				class="cursor-pointer btn-primary px-6 py-2.5 text-sm">Contact Us</button
			>
		</div>
	</div>
</section>
