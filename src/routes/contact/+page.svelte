<script lang="ts">
	import Navbar from '$lib/components/Navbar.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import Seo from '$lib/components/Seo.svelte';
	import { localizeHref } from '$lib/paraglide/runtime';
	import * as m from '$lib/paraglide/messages';
</script>

<Seo
	title={m.contact_seo_title()}
	description={m.contact_seo_desc()}
	canonicalPath="/contact"
	origin="https://landing.superextra.ai"
/>

<Navbar />

<article class="mx-auto max-w-[720px] px-6 pt-32 pb-20">
	<h1 class="text-3xl font-medium tracking-tight text-black dark:text-white">
		{m.contact_heading()}
	</h1>

	<p class="mt-6 text-sm text-black/60 dark:text-white/60">{m.contact_intro()}</p>

	<dl class="mt-8 space-y-6 text-sm">
		<div class="flex flex-col gap-1 sm:flex-row sm:gap-4">
			<dt class="shrink-0 text-black/40 sm:w-48 dark:text-white/40">
				{m.contact_general_label()}
			</dt>
			<dd>
				<a href="mailto:hello@superextra.ai" class="text-black underline dark:text-white"
					>hello@superextra.ai</a
				>
			</dd>
		</div>
		<div class="flex flex-col gap-1 sm:flex-row sm:gap-4">
			<dt class="shrink-0 text-black/40 sm:w-48 dark:text-white/40">
				{m.contact_privacy_label()}
			</dt>
			<dd>
				<a href="mailto:privacy@superextra.ai" class="text-black underline dark:text-white"
					>privacy@superextra.ai</a
				>
			</dd>
		</div>
		<div class="flex flex-col gap-1 sm:flex-row sm:gap-4">
			<dt class="shrink-0 text-black/40 sm:w-48 dark:text-white/40">
				{m.contact_operator_label()}
			</dt>
			<dd class="text-black/70 dark:text-white/70">
				PP2 Studio sp. z o.o.<br />
				{m.imprint_seat_value()}<br />
				<a href={localizeHref('/impressum')} class="text-black underline dark:text-white"
					>{m.contact_imprint_link()}</a
				>
			</dd>
		</div>
	</dl>
</article>

<Footer />
