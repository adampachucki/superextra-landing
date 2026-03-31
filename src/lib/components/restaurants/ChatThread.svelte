<script lang="ts">
	import { marked } from 'marked';
	import { chatState } from '$lib/chat-state.svelte';

	marked.setOptions({ breaks: true, gfm: true });

	let scrollEl: HTMLDivElement | undefined = $state();

	$effect(() => {
		chatState.messages.length;
		chatState.loading;
		if (scrollEl) {
			requestAnimationFrame(() => {
				scrollEl!.scrollTop = scrollEl!.scrollHeight;
			});
		}
	});

	function renderMarkdown(text: string): string {
		return marked.parse(text) as string;
	}

	function retryLast() {
		const lastUser = [...chatState.messages].reverse().find(m => m.role === 'user');
		if (lastUser) chatState.send(lastUser.text);
	}
</script>

<div bind:this={scrollEl} class="flex-1 overflow-y-auto px-4 py-6 md:px-6">
	<div class="mx-auto flex max-w-[700px] flex-col gap-5">
		{#each chatState.messages as msg}
			<div class="msg-appear flex {msg.role === 'user' ? 'justify-end' : 'justify-start'}">
				{#if msg.role === 'user'}
					<div class="max-w-[85%] rounded-2xl rounded-br-md bg-cream-100 px-4 py-3 text-[15px] leading-relaxed text-black dark:text-white">
						{msg.text}
					</div>
				{:else}
					<div class="max-w-[95%] px-1 py-1">
						<div class="prose max-w-none text-[15px] leading-relaxed text-black/80 prose-headings:text-black prose-strong:text-black prose-a:text-black prose-a:underline dark:text-white/80 dark:prose-headings:text-white dark:prose-strong:text-white dark:prose-a:text-white">
							{@html renderMarkdown(msg.text)}
						</div>
					</div>
				{/if}
			</div>
		{/each}

		{#if chatState.loading}
			<div class="msg-appear flex justify-start">
				<div class="flex items-center gap-2 px-1 py-1">
					<span class="shimmer-text text-[13px]">Researching</span>
					<span class="loading-dots flex gap-1">
						<span class="h-1 w-1 rounded-full bg-[#6ee7b3]"></span>
						<span class="h-1 w-1 rounded-full bg-[#a78bfa]"></span>
						<span class="h-1 w-1 rounded-full bg-[#f472b6]"></span>
					</span>
				</div>
			</div>
		{/if}

		{#if chatState.error}
			<div class="msg-appear flex justify-start">
				<div class="flex items-center gap-3 rounded-2xl border border-red-200/50 bg-red-50/50 px-5 py-3 dark:border-red-400/20 dark:bg-red-900/10">
					<span class="text-[13px] text-red-600/80 dark:text-red-400/80">{chatState.error}</span>
					<button onclick={retryLast} class="cursor-pointer whitespace-nowrap rounded-full border border-red-200/50 px-3 py-1 text-[12px] text-red-600/60 transition-colors hover:bg-red-100/50 dark:border-red-400/20 dark:text-red-400/60 dark:hover:bg-red-900/20">
						Try again
					</button>
				</div>
			</div>
		{/if}
	</div>
</div>

<style>
	.msg-appear {
		animation: msgIn 0.3s ease-out both;
	}

	@keyframes msgIn {
		from { opacity: 0; transform: translateY(6px); }
		to { opacity: 1; transform: translateY(0); }
	}

.loading-dots span {
		animation: dotWave 1.4s ease-in-out infinite;
	}
	.loading-dots span:nth-child(2) { animation-delay: 0.15s; }
	.loading-dots span:nth-child(3) { animation-delay: 0.3s; }

	@keyframes dotWave {
		0%, 80%, 100% { opacity: 0.4; transform: translateY(0); }
		40% { opacity: 1; transform: translateY(-3px); }
	}

	.shimmer-text {
		color: transparent;
		background: linear-gradient(
			90deg,
			rgba(0,0,0,0.3) 0%,
			rgba(0,0,0,0.6) 40%,
			rgba(0,0,0,0.3) 80%
		);
		background-size: 200% 100%;
		background-clip: text;
		-webkit-background-clip: text;
		animation: shimmer 2.5s ease-in-out infinite;
	}

	:global(.dark) .shimmer-text {
		background: linear-gradient(
			90deg,
			rgba(255,255,255,0.3) 0%,
			rgba(255,255,255,0.6) 40%,
			rgba(255,255,255,0.3) 80%
		);
		background-size: 200% 100%;
		background-clip: text;
		-webkit-background-clip: text;
	}

	@keyframes shimmer {
		0% { background-position: 200% 0; }
		100% { background-position: -200% 0; }
	}
</style>
