<script lang="ts">
	let {
		subtitle,
		title,
		titleClass = '',
		subtitleClass = ''
	}: { subtitle: string; title: string; titleClass?: string; subtitleClass?: string } = $props();
</script>

<p
	class="mb-6 text-sm font-medium tracking-widest text-black/40 uppercase dark:text-white/40 {subtitleClass}"
>
	{subtitle}
</p>
<h2
	class="text-[clamp(2rem,4vw,3.25rem)] leading-[1.1] font-normal tracking-[-0.02em] text-black dark:text-white {titleClass}"
>
	{title}
</h2>
