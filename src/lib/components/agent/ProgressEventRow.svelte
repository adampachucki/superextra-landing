<script lang="ts">
	let {
		label,
		detail
	}: {
		label: string;
		detail?: string;
	} = $props();
</script>

<div class="relative flex items-start text-[14px] leading-snug">
	<span class="relative mt-[7px] flex h-[7px] w-[7px] shrink-0 items-center justify-center">
		<span class="h-[7px] w-[7px] rounded-full bg-emerald-500 dark:bg-emerald-400"></span>
	</span>
	<span class="ml-2.5 min-w-0 flex-1 break-words text-black/65 dark:text-white/65">
		<span class="font-medium text-black/80 dark:text-white/80">{label}</span>
		{#if detail}
			<span class="ml-1 text-black/55 dark:text-white/55">{detail}</span>
		{/if}
	</span>
</div>
