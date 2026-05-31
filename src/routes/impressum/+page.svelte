<script lang="ts">
	import Navbar from '$lib/components/Navbar.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import Seo from '$lib/components/Seo.svelte';
	import * as m from '$lib/paraglide/messages';

	// Company identification for PP2 Studio sp. z o.o. — the entity that
	// operates Superextra. Registry-fixed values are language-independent and
	// kept as constants; localized labels/values come from the message catalog.
	const rows = [
		{ label: m.imprint_label_seat, value: m.imprint_seat_value() },
		{ label: m.imprint_label_register, value: m.imprint_register_value() },
		{ label: m.imprint_label_nip, value: '5862419337' },
		{ label: m.imprint_label_regon, value: '542150062' },
		{ label: m.imprint_label_vat, value: 'PL5862419337' },
		{ label: m.imprint_label_capital, value: m.imprint_capital_value() }
	];
</script>

<Seo title={m.imprint_seo_title()} description={m.imprint_seo_desc()} canonicalPath="/impressum" />

<Navbar minimal />

<article class="mx-auto max-w-[720px] px-6 pt-32 pb-20">
	<h1 class="text-3xl font-medium tracking-tight text-black dark:text-white">
		{m.imprint_heading()}
	</h1>

	<p class="mt-6 text-sm text-black/60 dark:text-white/60">{m.imprint_intro()}</p>

	<p class="mt-4 text-base font-medium text-black dark:text-white">PP2 Studio sp. z o.o.</p>

	<dl class="mt-8 space-y-4 text-sm">
		{#each rows as row (row.value)}
			<div class="flex flex-col gap-1 sm:flex-row sm:gap-4">
				<dt class="shrink-0 text-black/40 sm:w-48 dark:text-white/40">{row.label()}</dt>
				<dd class="text-black/70 dark:text-white/70">{row.value}</dd>
			</div>
		{/each}
		<div class="flex flex-col gap-1 sm:flex-row sm:gap-4">
			<dt class="shrink-0 text-black/40 sm:w-48 dark:text-white/40">{m.imprint_label_email()}</dt>
			<dd class="text-black/70 dark:text-white/70">
				<a href="mailto:hello@superextra.ai" class="text-black underline dark:text-white"
					>hello@superextra.ai</a
				>
			</dd>
		</div>
	</dl>
</article>

<Footer />
