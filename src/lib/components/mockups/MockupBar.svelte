<script lang="ts">
	import type { Snippet } from 'svelte';

	let { label, compact = false, children }: {
		label: string;
		compact?: boolean;
		children?: Snippet;
	} = $props();
</script>

<div class="top-bar" class:compact>
	<div class="bar-icon"><span></span><span></span></div>
	<span class="bar-label">{label}</span>
	{#if children}{@render children()}{/if}
</div>

<style>
	.top-bar {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.75rem 1.25rem;
		border-bottom: 1px solid rgba(0, 0, 0, 0.04);
	}
	.top-bar.compact {
		padding: 0.75rem 0.875rem;
	}
	.bar-icon {
		display: flex;
		gap: 2px;
	}
	.bar-icon span {
		display: block;
		width: 2.5px;
		height: 12px;
		background: rgba(0, 0, 0, 0.25);
		border-radius: 1px;
	}
	.bar-label {
		font-size: 0.8125rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.6);
	}
</style>
