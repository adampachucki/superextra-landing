<script lang="ts">
	import type { Snippet } from 'svelte';

	let { title, desc, mode = 'standard', children }: {
		title: string;
		desc: string;
		mode?: 'standard' | 'edge' | 'free';
		children: Snippet;
	} = $props();
</script>

<div class="card">
	<div class="card-text">
		<h3 class="title">{title}</h3>
		<p class="desc">{desc}</p>
	</div>

	{#if mode === 'free'}
		<div class="mockup-free">
			{@render children()}
		</div>
	{:else}
		<div class="mockup" class:mockup-edge={mode === 'edge'}>
			{@render children()}
		</div>
	{/if}
</div>

<style>
	.card {
		border-radius: 1rem;
		background: var(--color-cream-100);
		border: 1px solid rgba(0, 0, 0, 0.03);
		padding: 1.75rem 1.75rem;
		padding-bottom: 0;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		height: clamp(25rem, 30vw, 28rem);
	}

	.card-text {
		height: 6rem;
		margin-bottom: 2rem;
		overflow: hidden;
		flex-shrink: 0;
	}
	@media (max-width: 767px) {
		.card-text {
			height: auto;
			overflow: visible;
		}
	}

	.title {
		font-size: 1.25rem;
		font-weight: 500;
		color: #000;
	}

	.desc {
		font-size: 0.875rem;
		line-height: 1.5;
		margin-top: 0.25rem;
		color: rgba(0, 0, 0, 0.6);
	}

	.mockup {
		border-radius: 0.75rem 0.75rem 0 0;
		background: #fff;
		border: 1px solid rgba(0, 0, 0, 0.08);
		border-bottom: none;
		margin-bottom: -3.5rem;
		display: flex;
		flex-direction: column;
		flex: 1;
	}

	.mockup-edge {
		border-radius: 0.75rem 0 0 0;
		margin-right: -1.75rem;
		border-right: none;
	}

	.mockup-free {
		flex: 1;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		margin: 0 -1.75rem;
	}
</style>
