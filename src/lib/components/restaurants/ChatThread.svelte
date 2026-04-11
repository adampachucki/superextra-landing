<script lang="ts">
	import { marked } from 'marked';
	import { chatState } from '$lib/chat-state.svelte';
	import { tts } from '$lib/tts.svelte';
	import StreamingProgress from './StreamingProgress.svelte';

	marked.setOptions({ breaks: true, gfm: true });

	let scrollEl: HTMLDivElement | undefined = $state();

	$effect(() => {
		chatState.messages.length;
		chatState.loading;
		chatState.streamingText;
		chatState.streamingProgress;
		chatState.streamingActivities;
		if (scrollEl) {
			requestAnimationFrame(() => {
				window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' });
			});
		}
	});

	function renderMarkdown(text: string): string {
		return marked.parse(text) as string;
	}

	let hasStreamingContent = $derived(
		chatState.streamingProgress.length > 0 ||
			chatState.streamingText.length > 0 ||
			chatState.streamingActivities.length > 0
	);

	// Elapsed timer — ticks while any step is "running"
	let elapsedMs = $state(0);
	let elapsedInterval: ReturnType<typeof setInterval> | null = null;

	$effect(() => {
		const hasRunning = chatState.streamingProgress.some((s) => s.status === 'running');
		if (hasRunning && !elapsedInterval) {
			elapsedMs = 0;
			elapsedInterval = setInterval(() => {
				elapsedMs += 1000;
			}, 1000);
		} else if (!hasRunning && elapsedInterval) {
			clearInterval(elapsedInterval);
			elapsedInterval = null;
		}
		return () => {
			if (elapsedInterval) clearInterval(elapsedInterval);
			elapsedInterval = null;
		};
	});

	// Typewriter — drains streamingText at a steady rate
	let displayText = $state('');
	let typewriterRaf: number | null = null;

	function drain() {
		const target = chatState.streamingText;
		if (displayText.length >= target.length) {
			typewriterRaf = null;
			return;
		}
		let nextLen = Math.min(displayText.length + 3, target.length);
		// Skip data URI images in one frame — they can be 200KB+ of base64
		const upcoming = target.slice(displayText.length);
		if (upcoming.startsWith('![')) {
			const end = upcoming.indexOf(')\n');
			if (end > 0) nextLen = displayText.length + end + 2;
		}
		displayText = target.slice(0, nextLen);
		typewriterRaf = requestAnimationFrame(drain);
	}

	$effect(() => {
		const target = chatState.streamingText;
		if (!target) {
			displayText = '';
			if (typewriterRaf) {
				cancelAnimationFrame(typewriterRaf);
				typewriterRaf = null;
			}
			return;
		}
		if (displayText.length < target.length && !typewriterRaf) {
			drain();
		}
	});

	const SOURCES_LIMIT = 19;
	let expandedSources: Record<number, boolean> = $state({});

	async function retryLast() {
		const recovered = await chatState.recover();
		if (recovered) return;
		const lastUser = [...chatState.messages].reverse().find((m) => m.role === 'user');
		if (lastUser) chatState.send(lastUser.text);
	}
</script>

<div bind:this={scrollEl} class="px-5 py-6 md:px-6">
	<div class="mx-auto flex max-w-[700px] flex-col gap-5">
		{#each chatState.messages as msg, i}
			{#if i === chatState.messages.length - 1 && msg.role === 'agent' && chatState.streamingActivities.length > 0 && !chatState.loading}
				<div class="msg-appear flex justify-start">
					<div class="max-w-[95%] px-1 py-1">
						<StreamingProgress activities={chatState.streamingActivities} />
					</div>
				</div>
			{/if}
			<div class="msg-appear flex {msg.role === 'user' ? 'justify-end' : 'justify-start'}">
				{#if msg.role === 'user'}
					<div
						class="max-w-[85%] rounded-2xl rounded-br-md bg-cream-100 px-4 py-3 text-[15px] leading-relaxed text-black dark:text-white"
					>
						{msg.text}
					</div>
				{:else}
					<div class="max-w-[95%] px-1 py-1">
						<div
							class="prose max-w-none text-[15px] leading-relaxed text-black/80 dark:text-white/80 prose-headings:text-black dark:prose-headings:text-white prose-a:text-black prose-a:underline dark:prose-a:text-white prose-strong:text-black dark:prose-strong:text-white"
						>
							{@html renderMarkdown(msg.text)}
						</div>
						<div class="mt-2 flex justify-end">
							<button
								onclick={() => tts.play(i, msg.text)}
								disabled={tts.loading === i}
								class="group inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] transition-colors {tts.loading ===
									i || tts.playingIndex === i
									? 'border-black/15 bg-black/[0.03] text-black/70 hover:border-black/25 hover:bg-black/[0.06] hover:text-black/90 dark:border-white/15 dark:bg-white/[0.03] dark:text-white/70 dark:hover:border-white/25 dark:hover:bg-white/[0.06] dark:hover:text-white/90'
									: 'border-black/5 text-black/40 hover:border-black/10 hover:bg-black/[0.02] hover:text-black/60 dark:border-white/5 dark:text-white/40 dark:hover:border-white/10 dark:hover:bg-white/[0.02] dark:hover:text-white/60'}"
							>
								{#if tts.loading === i}
									<svg class="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
										<circle
											cx="12"
											cy="12"
											r="10"
											stroke="currentColor"
											stroke-width="2"
											opacity="0.25"
										/>
										<path
											d="M4 12a8 8 0 018-8"
											stroke="currentColor"
											stroke-width="2"
											stroke-linecap="round"
										/>
									</svg>
									<span>Loading…</span>
								{:else if tts.playingIndex === i}
									<svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor">
										<rect x="6" y="5" width="4" height="14" rx="1" />
										<rect x="14" y="5" width="4" height="14" rx="1" />
									</svg>
									<span>Stop</span>
								{:else}
									<svg
										class="h-3.5 w-3.5"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="2"
										stroke-linecap="round"
										stroke-linejoin="round"
									>
										<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
										<path d="M15.54 8.46a5 5 0 010 7.07" />
										<path d="M19.07 4.93a10 10 0 010 14.14" />
									</svg>
									<span>Read aloud</span>
								{/if}
							</button>
						</div>
						{#if msg.sources?.length}
							{@const showAll = expandedSources[i]}
							{@const visible = showAll ? msg.sources : msg.sources.slice(0, SOURCES_LIMIT)}
							{@const remaining = msg.sources.length - SOURCES_LIMIT}
							<div class="mt-5">
								<span class="mb-2 block text-[12px] font-medium text-black/40 dark:text-white/40"
									>Sources ({msg.sources.length})</span
								>
								<div class="flex flex-wrap gap-1.5">
									{#each visible as src}
										{@const domain =
											src.domain ||
											(() => {
												try {
													const h = new URL(src.url).hostname;
													return h.includes('vertexaisearch') ? '' : h;
												} catch {
													return '';
												}
											})() ||
											src.title ||
											''}
										<a
											href={src.url}
											target="_blank"
											rel="noopener noreferrer"
											class="group inline-flex items-center gap-1.5 rounded-full border border-black/5 px-2.5 py-1 no-underline transition-colors hover:border-black/10 hover:bg-black/[0.02] dark:border-white/5 dark:hover:border-white/10 dark:hover:bg-white/[0.02]"
										>
											<img
												src="https://www.google.com/s2/favicons?sz=32&domain={domain}"
												alt=""
												class="h-3.5 w-3.5 shrink-0 rounded-sm"
											/>
											<span
												class="text-[12px] leading-snug text-black/50 transition-colors group-hover:text-black/70 dark:text-white/50 dark:group-hover:text-white/70"
											>
												{domain || src.title}
											</span>
										</a>
									{/each}
									{#if remaining > 0 && !showAll}
										<button
											onclick={() => {
												expandedSources[i] = true;
											}}
											class="inline-flex cursor-pointer items-center rounded-full border border-black/5 px-2.5 py-1 text-[12px] leading-snug text-black/40 transition-colors hover:border-black/10 hover:bg-black/[0.02] hover:text-black/60 dark:border-white/5 dark:text-white/40 dark:hover:border-white/10 dark:hover:bg-white/[0.02] dark:hover:text-white/60"
										>
											+{remaining} more
										</button>
									{/if}
								</div>
							</div>
						{/if}
					</div>
				{/if}
			</div>
		{/each}

		{#if chatState.streamingActivities.length > 0 && chatState.loading}
			<div class="msg-appear flex justify-start">
				<div class="max-w-[95%] px-1 py-1">
					<StreamingProgress
						activities={chatState.streamingActivities}
						loading={chatState.loading}
					/>
				</div>
			</div>
		{/if}

		{#if chatState.loading && !chatState.recovering}
			<div class="msg-appear flex justify-start">
				<div class="max-w-[95%] px-1 py-1">
					{#if displayText}
						<div
							class="prose mt-4 max-w-none text-[15px] leading-relaxed text-black/80 dark:text-white/80 prose-headings:text-black dark:prose-headings:text-white prose-a:text-black prose-a:underline dark:prose-a:text-white prose-strong:text-black dark:prose-strong:text-white"
						>
							{@html renderMarkdown(displayText)}
						</div>
					{:else if hasStreamingContent && chatState.streamingActivities.length === 0}
						<div class="flex flex-col gap-1.5">
							{#each chatState.streamingProgress as step}
								<div class="flex items-center gap-2 text-[13px]">
									{#if step.status === 'complete'}
										<span class="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500"></span>
										<span class="text-black/40 dark:text-white/40">{step.label}</span>
									{:else}
										<span class="stage-pulse h-1.5 w-1.5 shrink-0 rounded-full bg-amber-300"></span>
										<span class="text-black/60 dark:text-white/60"
											>{step.label}{#if elapsedMs > 0}
												<span class="ml-1 text-black/25 dark:text-white/25"
													>{Math.floor(elapsedMs / 1000)}s</span
												>{/if}</span
										>
									{/if}
								</div>
							{/each}
						</div>
					{:else if chatState.streamingActivities.length === 0}
						<div class="flex items-center gap-2">
							<span class="loading-dots flex gap-1">
								<span class="h-1 w-1 rounded-full bg-[#6ee7b3]"></span>
								<span class="h-1 w-1 rounded-full bg-[#a78bfa]"></span>
								<span class="h-1 w-1 rounded-full bg-[#f472b6]"></span>
							</span>
							<span class="shimmer-text text-[13px]">Researching...</span>
						</div>
					{/if}
				</div>
			</div>
		{/if}

		{#if chatState.recovering && chatState.loading}
			<div class="msg-appear flex justify-start">
				<div
					class="flex items-center gap-2 rounded-2xl border border-amber-200/50 bg-amber-50/50 px-5 py-3 dark:border-amber-400/20 dark:bg-amber-900/10"
				>
					<span class="loading-dots flex gap-1">
						<span class="h-1 w-1 rounded-full bg-amber-400"></span>
						<span class="h-1 w-1 rounded-full bg-amber-500"></span>
						<span class="h-1 w-1 rounded-full bg-amber-400"></span>
					</span>
					<span class="text-[13px] text-amber-600/80 dark:text-amber-400/80"
						>Reconnecting to your session...</span
					>
				</div>
			</div>
		{/if}

		{#if chatState.error}
			{@const isTimeout = chatState.error === 'timeout'}
			<div class="msg-appear flex justify-start">
				<div
					class="flex items-center gap-3 rounded-2xl border px-5 py-3 {isTimeout
						? 'border-amber-200/50 bg-amber-50/50 dark:border-amber-400/20 dark:bg-amber-900/10'
						: 'border-red-200/50 bg-red-50/50 dark:border-red-400/20 dark:bg-red-900/10'}"
				>
					<span
						class="text-[13px] {isTimeout
							? 'text-amber-600/80 dark:text-amber-400/80'
							: 'text-red-600/80 dark:text-red-400/80'}"
					>
						{isTimeout
							? 'The analysis took longer than expected and was cut short.'
							: chatState.error}
					</span>
					<button
						onclick={retryLast}
						class="cursor-pointer rounded-full border px-3 py-1 text-[12px] whitespace-nowrap transition-colors {isTimeout
							? 'border-amber-200/50 text-amber-600/60 hover:bg-amber-100/50 dark:border-amber-400/20 dark:text-amber-400/60 dark:hover:bg-amber-900/20'
							: 'border-red-200/50 text-red-600/60 hover:bg-red-100/50 dark:border-red-400/20 dark:text-red-400/60 dark:hover:bg-red-900/20'}"
					>
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
		from {
			opacity: 0;
			transform: translateY(6px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.loading-dots span {
		animation: dotWave 1.4s ease-in-out infinite;
	}
	.loading-dots span:nth-child(2) {
		animation-delay: 0.15s;
	}
	.loading-dots span:nth-child(3) {
		animation-delay: 0.3s;
	}

	@keyframes dotWave {
		0%,
		80%,
		100% {
			opacity: 0.4;
			transform: translateY(0);
		}
		40% {
			opacity: 1;
			transform: translateY(-3px);
		}
	}

	.shimmer-text {
		color: transparent;
		background: linear-gradient(
			90deg,
			rgba(0, 0, 0, 0.35) 0%,
			rgba(0, 0, 0, 0.5) 40%,
			rgba(0, 0, 0, 0.35) 80%
		);
		background-size: 200% 100%;
		background-clip: text;
		-webkit-background-clip: text;
		animation: shimmer 5s ease-in-out infinite;
	}

	:global(.dark) .shimmer-text {
		background: linear-gradient(
			90deg,
			rgba(255, 255, 255, 0.35) 0%,
			rgba(255, 255, 255, 0.5) 40%,
			rgba(255, 255, 255, 0.35) 80%
		);
		background-size: 200% 100%;
		background-clip: text;
		-webkit-background-clip: text;
	}

	.preview-stagger {
		animation: previewIn 0.4s ease-out both;
	}

	@keyframes previewIn {
		from {
			opacity: 0;
			transform: translateY(4px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.stage-pulse {
		animation: stagePulse 1.5s ease-in-out infinite;
	}

	@keyframes stagePulse {
		0%,
		100% {
			opacity: 0.4;
		}
		50% {
			opacity: 1;
		}
	}

	@keyframes shimmer {
		0% {
			background-position: 200% 0;
		}
		50% {
			background-position: -200% 0;
		}
		100% {
			background-position: -200% 0;
		}
	}
</style>
