<script lang="ts">
	import { chatState } from '$lib/chat-state.svelte';
	import { formatRelativeTime } from '$lib/format-time';

	let recent = $derived(chatState.sessionsList.slice(0, 4));
</script>

{#if recent.length > 0}
	<section class="py-8">
		<div class="mx-auto max-w-[1200px] px-6">
			<p
				class="mb-3 text-sm font-medium tracking-widest text-black/40 uppercase dark:text-white/40"
			>
				Pick up where you left off
			</p>
		</div>
		<div class="scrollbar-hide flex gap-3 overflow-x-auto scroll-smooth">
			{#each recent as sess, i (sess.sid)}
				<a
					href="/agent/chat?sid={sess.sid}"
					class="min-w-[200px] shrink-0 rounded-lg border border-black/[0.08] px-4 py-3 transition-colors hover:border-black/[0.16] hover:bg-black/[0.02] dark:border-white/[0.08] dark:hover:border-white/[0.16] dark:hover:bg-white/[0.03]"
					style="{i === 0 ? 'margin-left: var(--content-inset)' : ''}{i === recent.length - 1
						? 'margin-right: var(--content-inset)'
						: ''}"
				>
					<p class="truncate text-[13px] text-black/80 dark:text-white/80">
						{sess.title ?? 'Untitled chat'}
					</p>
					<p class="mt-0.5 truncate text-[11px] text-black/40 dark:text-white/40">
						{#if sess.placeContext}
							{sess.placeContext.name} &middot;
						{/if}
						{sess.updatedAtMs ? formatRelativeTime(sess.updatedAtMs) : ''}
					</p>
				</a>
			{/each}
		</div>
	</section>
{/if}

<style>
	section {
		--content-inset: max(24px, calc((100% - 1200px) / 2 + 24px));
	}
	.scrollbar-hide {
		-ms-overflow-style: none;
		scrollbar-width: none;
	}
	.scrollbar-hide::-webkit-scrollbar {
		display: none;
	}
</style>
