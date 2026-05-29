<script lang="ts">
	import { formState } from '$lib/form-state.svelte';
	import * as m from '$lib/paraglide/messages';
</script>

<section class="border-t border-cream-200 py-16">
	<div
		class="mx-auto flex max-w-[1200px] flex-col items-center justify-between gap-6 px-6 md:flex-row"
	>
		<p class="text-center text-lg font-medium text-black md:text-left dark:text-white">
			{m.cta_l_text()}
		</p>
		<div class="flex items-center">
			<button onclick={() => formState.open()} class="btn-primary px-6 py-2.5 text-sm"
				>{m.nav_book_demo()}</button
			>
		</div>
	</div>
</section>
