<script lang="ts">
	import type { Snippet } from 'svelte';

	let { title, desc, mode = 'standard', wide = false, separator = false, end = false, children }: {
		title: string;
		desc: string;
		mode?: 'standard' | 'edge' | 'free';
		wide?: boolean;
		separator?: boolean;
		end?: boolean;
		children: Snippet;
	} = $props();
</script>

<div class="card border-t border-cream-200{separator ? ' md:border-l' : ''}{end ? ' md:border-r' : ''} px-4 md:px-8" class:card-wide={wide}>
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
		padding-top: 2.25rem;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		height: clamp(25rem, 30vw, 28rem);
	}

	@media (min-width: 768px) {
		.card-wide {
			grid-column: span 2;
		}
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
		color: var(--color-text);
	}

	.desc {
		font-size: 0.875rem;
		line-height: 1.5;
		margin-top: 0.25rem;
		color: rgba(var(--mockup-text), 0.6);
		max-width: 36rem;
	}

	.mockup {
		border-radius: 0.75rem 0.75rem 0 0;
		background: rgb(var(--mockup-bg));
		border: 0.5px solid rgba(var(--mockup-text), 0.08);
		border-bottom: none;
		margin-bottom: -3.5rem;
		display: flex;
		flex-direction: column;
		flex: 1;
		overflow: hidden;
	}

	.mockup-edge {
		border-radius: 0.75rem 0 0 0;
		border-right: none;
	}

	@media (min-width: 768px) {
		.mockup-edge {
			margin-right: -2rem;
		}
	}

	.mockup-free {
		flex: 1;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	@media (min-width: 768px) {
		.mockup-free {
			margin-left: -2rem;
			margin-right: -2rem;
		}
	}
</style>
