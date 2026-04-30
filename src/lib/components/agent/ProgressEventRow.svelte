<script lang="ts">
	type Status = 'running' | 'done' | 'error';

	let {
		label,
		detail,
		status,
		showConnector = false
	}: {
		label: string;
		detail?: string;
		status: Status;
		showConnector?: boolean;
	} = $props();

	let dotClass = $derived(
		status === 'error'
			? 'bg-red-400 dark:bg-red-500'
			: status === 'done'
				? 'bg-emerald-500 dark:bg-emerald-400'
				: ''
	);
</script>

<div class="relative flex items-start text-[14px] leading-snug">
	{#if showConnector}
		<span
			class="absolute left-[3px] top-[15px] h-[calc(100%+10px)] w-px bg-black/12 dark:bg-white/15"
			aria-hidden="true"
		></span>
	{/if}
	<span class="relative mt-[7px] flex h-[7px] w-[7px] shrink-0 items-center justify-center">
		{#if status === 'running'}
			<span
				class="h-[7px] w-[7px] animate-spin rounded-full border border-black/45 border-t-transparent dark:border-white/55 dark:border-t-transparent"
			></span>
		{:else}
			<span class="h-[7px] w-[7px] rounded-full {dotClass}"></span>
		{/if}
	</span>
	<span class="ml-2.5 min-w-0 flex-1 break-words text-black/65 dark:text-white/65">
		<span class="font-medium text-black/80 dark:text-white/80">{label}</span>
		{#if detail}
			<span class="ml-1 text-black/55 dark:text-white/55">{detail}</span>
		{/if}
	</span>
</div>
