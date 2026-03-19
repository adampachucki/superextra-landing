<script lang="ts">
	import { formState } from '$lib/form-state.svelte';
</script>

<section class="py-16">
	<div class="mx-auto flex max-w-[1200px] flex-col items-center justify-between gap-6 px-6 md:flex-row">
		<p class="text-center text-lg font-medium text-black md:text-left">
			Early access is now open. Limited spots available.
		</p>
		<div class="flex items-center gap-3">
			<a href="mailto:hello@superextra.ai" class="rounded-full border border-gray-200 px-6 py-2.5 text-sm text-black transition-colors hover:bg-gray-50">Contact Us</a>
			<button onclick={() => formState.open()} class="cursor-pointer rounded-full bg-black px-6 py-2.5 text-sm text-white transition-colors hover:bg-black/80">Get Access</button>
		</div>
	</div>
</section>
