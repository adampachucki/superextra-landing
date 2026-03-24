<script lang="ts">
	import type { Snippet } from 'svelte';

	let { label, compact = false, icon = 'bars', children }: {
		label: string;
		compact?: boolean;
		icon?: 'bars' | 'trend' | 'list' | 'chart' | 'barchart' | 'chat' | 'pin' | 'user';
		children?: Snippet;
	} = $props();
</script>

<div class="top-bar" class:compact>
	{#if icon === 'trend'}
		<svg class="bar-svg" viewBox="0 0 12 12" fill="none">
			<polyline points="1,9 4,4 7,7 11,2" stroke="rgba(0,0,0,0.3)" stroke-width="1.5"/>
		</svg>
	{:else if icon === 'list'}
		<svg class="bar-svg" viewBox="0 0 12 12" fill="none">
			<path d="M1,1.5 H7 L11,6 L7,10.5 H1 Z" stroke="rgba(0,0,0,0.3)" stroke-width="1.2"/>
		</svg>
	{:else if icon === 'chart'}
		<svg class="bar-svg" viewBox="0 0 12 12" fill="none">
			<circle cx="6" cy="6" r="5" stroke="rgba(0,0,0,0.3)" stroke-width="1.2"/>
			<line x1="6" y1="6" x2="6" y2="1" stroke="rgba(0,0,0,0.3)" stroke-width="1.2"/>
			<line x1="6" y1="6" x2="10.33" y2="8.5" stroke="rgba(0,0,0,0.3)" stroke-width="1.2"/>
		</svg>
	{:else if icon === 'barchart'}
		<svg class="bar-svg" viewBox="0 0 12 12" fill="none">
			<rect x="1" y="7" width="2" height="4" fill="rgba(0,0,0,0.2)"/>
			<rect x="5" y="4" width="2" height="7" fill="rgba(0,0,0,0.25)"/>
			<rect x="9" y="1" width="2" height="10" fill="rgba(0,0,0,0.3)"/>
		</svg>
	{:else if icon === 'chat'}
		<svg class="bar-svg" viewBox="0 0 12 12" fill="none">
			<path d="M2,1 H10 Q11,1 11,2 V7 Q11,8 10,8 H5 L2.5,11 V8 H2 Q1,8 1,7 V2 Q1,1 2,1 Z" stroke="rgba(0,0,0,0.3)" stroke-width="1.1"/>
		</svg>
	{:else if icon === 'pin'}
		<svg class="bar-svg" viewBox="0 0 12 13" fill="none">
			<circle cx="6" cy="6" r="5.5" stroke="rgba(0,0,0,0.25)" stroke-width="1.2"/>
			<circle cx="6" cy="6" r="1.5" fill="rgba(0,0,0,0.3)"/>
		</svg>
	{:else if icon === 'user'}
		<svg class="bar-svg" viewBox="0 0 12 12">
			<path d="M6,0.5 C7.8,0.5 8.5,1.8 8.5,3.2 C8.5,4.6 7.8,5.5 6,5.5 C4.2,5.5 3.5,4.6 3.5,3.2 C3.5,1.8 4.2,0.5 6,0.5 Z M1,12 C1,8.5 3,6.5 6,6.5 C9,6.5 11,8.5 11,12 Z" fill="rgba(0,0,0,0.25)"/>
		</svg>
	{:else}
		<div class="bar-icon"><span></span><span></span></div>
	{/if}
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
		gap: 0.125rem;
	}
	.bar-icon span {
		display: block;
		width: 0.156rem;
		height: 0.75rem;
		background: rgba(0, 0, 0, 0.25);
	}
	.bar-svg {
		width: 0.8125rem;
		height: 0.8125rem;
	}
	.bar-label {
		font-size: 0.8125rem;
		font-weight: 500;
		color: rgba(0, 0, 0, 0.6);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		min-width: 0;
		flex: 1;
	}
</style>
