<script lang="ts">
	let { domain, label }: { domain: string; label: string } = $props();

	let attempt = $state(0);
	let loaded = $state(false);

	const hostname = $derived(normalizeDomain(domain));
	const fallbackLetter = $derived((label || hostname || '?').trim().slice(0, 1).toUpperCase());
	const iconUrls = $derived(
		hostname
			? [
					`https://www.google.com/s2/favicons?sz=32&domain=${encodeURIComponent(hostname)}`,
					`https://icons.duckduckgo.com/ip3/${encodeURIComponent(hostname)}.ico`
				]
			: []
	);
	const iconSrc = $derived(iconUrls[attempt] ?? '');

	$effect(() => {
		hostname;
		attempt = 0;
		loaded = false;
	});

	function normalizeDomain(value: string): string {
		const trimmed = value.trim();
		if (!trimmed) return '';
		try {
			const url = trimmed.includes('://') ? new URL(trimmed) : new URL(`https://${trimmed}`);
			return url.hostname.replace(/^www\./, '');
		} catch {
			return trimmed
				.replace(/^https?:\/\//, '')
				.split('/')[0]
				.replace(/^www\./, '');
		}
	}

	function handleError() {
		loaded = false;
		if (attempt < iconUrls.length - 1) attempt += 1;
	}
</script>

<span
	class="relative flex h-3.5 w-3.5 shrink-0 items-center justify-center overflow-hidden rounded-sm bg-black/[0.04] text-[8px] font-medium text-black/35 uppercase dark:bg-white/[0.06] dark:text-white/35"
	aria-hidden="true"
>
	{fallbackLetter}
	{#if iconSrc}
		{#key iconSrc}
			<img
				src={iconSrc}
				alt=""
				loading="eager"
				decoding="async"
				referrerpolicy="no-referrer"
				class="absolute inset-0 h-full w-full object-cover transition-opacity duration-150 {loaded
					? 'opacity-100'
					: 'opacity-0'}"
				onload={() => {
					loaded = true;
				}}
				onerror={handleError}
			/>
		{/key}
	{/if}
</span>
