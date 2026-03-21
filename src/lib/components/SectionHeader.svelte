<script lang="ts">
	let { subtitle, title, titleClass = '' }: { subtitle: string; title: string; titleClass?: string } = $props();
</script>

<p class="mb-6 text-sm font-medium uppercase tracking-widest text-black/40">
	{subtitle}
</p>
<h2 class="text-[clamp(2rem,4vw,3.25rem)] leading-[1.1] font-normal tracking-[-0.02em] text-black {titleClass}">
	{title}
</h2>
