<script lang="ts">
	type PromptIconName = 'attach' | 'close' | 'location' | 'mic' | 'send' | 'stop';

	let {
		name,
		class: className = ''
	}: {
		name: PromptIconName;
		class?: string;
	} = $props();

	let strokeWidth = $derived(
		name === 'stop' ? 0 : name === 'send' ? 2.5 : name === 'close' ? 2 : 1.75
	);
</script>

<svg
	class={className}
	xmlns="http://www.w3.org/2000/svg"
	fill="none"
	viewBox="0 0 24 24"
	stroke="currentColor"
	stroke-width={strokeWidth}
>
	{#if name === 'location'}
		<path stroke-linecap="square" stroke-linejoin="miter" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
		<path
			stroke-linecap="square"
			stroke-linejoin="miter"
			d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z"
		/>
	{:else if name === 'attach'}
		<path
			stroke-linecap="round"
			stroke-linejoin="round"
			d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"
		/>
	{:else if name === 'close'}
		<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
	{:else if name === 'mic'}
		<path
			stroke-linecap="square"
			stroke-linejoin="miter"
			d="M12 3a3 3 0 00-3 3v6a3 3 0 006 0V6a3 3 0 00-3-3z"
		/>
		<path stroke-linecap="square" stroke-linejoin="miter" d="M19 10v2a7 7 0 01-14 0v-2M12 19v4" />
	{:else if name === 'stop'}
		<rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor" stroke="none" />
	{:else}
		<path stroke-linecap="round" stroke-linejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
	{/if}
</svg>
