<script lang="ts">
	import { chatState } from '$lib/chat-state.svelte';

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
		return text
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
			.replace(/\*(.+?)\*/g, '<em>$1</em>')
			.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
			.replace(/^### (.+)$/gm, '<h3>$1</h3>')
			.replace(/^## (.+)$/gm, '<h2>$1</h2>')
			.replace(/^# (.+)$/gm, '<h1>$1</h1>')
			.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>')
			.replace(/^[-*]\s+(.+)$/gm, '<li>$1</li>')
			.replace(/(<li>.*<\/li>)/gs, (match) => {
				if (match.includes('1.')) return `<ol>${match}</ol>`;
				return `<ul>${match}</ul>`;
			})
			.replace(/\n{2,}/g, '</p><p>')
			.replace(/\n/g, '<br>')
			.replace(/^(.+)$/, '<p>$1</p>');
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
					<div class="max-w-[85%] rounded-2xl rounded-br-md bg-cream-100 px-4 py-3 text-[14px] leading-relaxed text-black dark:text-white">
						{msg.text}
					</div>
				{:else}
					<div class="agent-msg max-w-[95%] rounded-2xl rounded-bl-md border border-black/[0.04] bg-white px-5 py-4 dark:border-white/[0.04] dark:bg-cream-50">
						<div class="prose prose-sm max-w-none text-black/80 prose-headings:text-black prose-strong:text-black prose-a:text-black prose-a:underline dark:text-white/80 dark:prose-headings:text-white dark:prose-strong:text-white dark:prose-a:text-white">
							{@html renderMarkdown(msg.text)}
						</div>
					</div>
				{/if}
			</div>
		{/each}

		{#if chatState.loading}
			<div class="msg-appear flex justify-start">
				<div class="flex items-center gap-2 rounded-2xl rounded-bl-md border border-black/[0.04] bg-white px-5 py-4 dark:border-white/[0.04] dark:bg-cream-50">
					<span class="text-[13px] text-black/40 dark:text-white/40">Researching</span>
					<span class="loading-dots flex gap-0.5">
						<span class="h-1 w-1 rounded-full bg-black/30 dark:bg-white/30"></span>
						<span class="h-1 w-1 rounded-full bg-black/30 dark:bg-white/30"></span>
						<span class="h-1 w-1 rounded-full bg-black/30 dark:bg-white/30"></span>
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
		animation: dotPulse 1.4s ease-in-out infinite;
	}
	.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
	.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

	@keyframes dotPulse {
		0%, 80%, 100% { opacity: 0.3; transform: scale(1); }
		40% { opacity: 1; transform: scale(1.3); }
	}
</style>
