<script lang="ts">
	import { page } from '$app/state';
	import * as m from '$lib/paraglide/messages';
</script>

<div class="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
	<p class="mb-2 text-6xl font-semibold tracking-tight text-black/10 dark:text-white/10">
		{page.status}
	</p>
	<h1 class="mb-3 text-xl font-medium tracking-tight">
		{page.status === 404 ? m.err_404_title() : m.err_500_title()}
	</h1>
	<p class="mb-8 max-w-sm text-sm leading-relaxed text-black/40 dark:text-white/40">
		{page.status === 404 ? m.err_404_body() : page.error?.message || m.err_500_body()}
	</p>
	<a href="/" class="btn-primary px-7 py-2.5 text-sm">{m.err_go_home()}</a>
</div>
