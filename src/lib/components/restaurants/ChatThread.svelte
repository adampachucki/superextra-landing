<script lang="ts">
	import { marked } from 'marked';
	import { chatState } from '$lib/chat-state.svelte';
	import { tts } from '$lib/tts.svelte';
	import { splitChartSegments } from '$lib/chart-blocks';
	import { createTypewriter } from '$lib/typewriter';
	import type { TurnCounts } from '$lib/firestore-stream';
	import ChartBlock from './ChartBlock.svelte';
	import StreamingProgress from './StreamingProgress.svelte';

	marked.setOptions({ breaks: true, gfm: true });

	let scrollEl: HTMLDivElement | undefined = $state();
	let typedReply = $state('');
	let activeTypedTimestamp: number | null = null;
	let now = $state(Date.now());

	const replyTyper = createTypewriter({
		onUpdate: (value) => {
			typedReply = value;
		},
		onDone: () => {
			if (chatState.typingMessageTimestamp === activeTypedTimestamp) {
				chatState.typingMessageTimestamp = null;
			}
		},
		charsPerFrame: 4
	});

	$effect(() => {
		chatState.messages.length;
		chatState.loading;
		chatState.liveTimeline.length;
		if (scrollEl) {
			requestAnimationFrame(() => {
				window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' });
			});
		}
	});

	$effect(() => {
		now = Date.now();
		const timer = setInterval(() => {
			now = Date.now();
		}, 1000);
		return () => clearInterval(timer);
	});

	$effect(() => {
		const ts = chatState.typingMessageTimestamp;
		if (!ts) {
			activeTypedTimestamp = null;
			typedReply = '';
			replyTyper.stop();
			return;
		}
		if (activeTypedTimestamp === ts) return;
		const message = [...chatState.messages].reverse().find((msg) => msg.timestamp === ts);
		if (!message) return;
		activeTypedTimestamp = ts;
		typedReply = '';
		replyTyper.reset();
		replyTyper.setTarget(message.text);
		return () => {
			replyTyper.stop();
		};
	});

	function renderMarkdown(text: string): string {
		return marked.parse(text) as string;
	}

	function displayText(text: string, timestamp: number): string {
		if (chatState.typingMessageTimestamp === timestamp && activeTypedTimestamp === timestamp) {
			return typedReply;
		}
		return text;
	}

	function formatDuration(ms: number): string {
		const totalSeconds = Math.max(0, Math.floor(ms / 1000));
		const minutes = Math.floor(totalSeconds / 60);
		const seconds = totalSeconds % 60;
		if (minutes > 0) return `${minutes}m ${seconds}s`;
		return `${seconds}s`;
	}

	function formatCounts(counts: TurnCounts): string {
		const parts: string[] = [];
		if (counts.webQueries > 0)
			parts.push(`Searched ${counts.webQueries} quer${counts.webQueries === 1 ? 'y' : 'ies'}`);
		if (counts.sources > 0)
			parts.push(`Opened ${counts.sources} source${counts.sources === 1 ? '' : 's'}`);
		if (counts.venues > 0)
			parts.push(`Checked ${counts.venues} venue${counts.venues === 1 ? '' : 's'}`);
		if (counts.platforms > 0)
			parts.push(`Reviewed ${counts.platforms} platform${counts.platforms === 1 ? '' : 's'}`);
		return parts.join(', ') || 'Worked';
	}

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
							{#each splitChartSegments(displayText(msg.text, msg.timestamp)) as seg, segIdx (segIdx)}
								{#if seg.kind === 'chart'}
									<ChartBlock spec={seg.spec} />
								{:else}
									{@html renderMarkdown(seg.text)}
								{/if}
							{/each}
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

						{#if msg.turnSummary}
							{@const summary = msg.turnSummary}
							<details
								class="mt-4 rounded-2xl border border-black/6 px-4 py-3 dark:border-white/10"
							>
								<summary class="cursor-pointer text-[13px] text-black/55 dark:text-white/55">
									Worked for {formatDuration(summary.elapsedMs)}
								</summary>
								<div class="mt-4 flex flex-col gap-4">
									{#each summary.notes as note, noteIdx (noteIdx)}
										<div class="flex flex-col gap-1">
											<div class="text-[14px] leading-relaxed text-black/82 dark:text-white/82">
												{note.text}
											</div>
											<div class="text-[12px] text-black/38 dark:text-white/38">
												{formatCounts(note.counts)}
											</div>
										</div>
									{/each}
								</div>
							</details>
						{/if}

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

		{#if chatState.loading && chatState.liveTimeline.length > 0}
			<div class="msg-appear flex justify-start">
				<div class="max-w-[95%] px-1 py-1">
					<StreamingProgress
						events={chatState.liveTimeline}
						startedAtMs={chatState.currentTurnStartedAtMs}
					/>
				</div>
			</div>
		{:else if chatState.loading && !chatState.recovering}
			<div class="msg-appear flex justify-start">
				<div class="max-w-[95%] px-1 py-1">
					<div class="flex flex-col gap-2">
						<div class="text-[14px] text-black/55 dark:text-white/55">
							Working for {formatDuration(now - (chatState.currentTurnStartedAtMs ?? now))}
						</div>
						<div class="text-[15px] leading-relaxed text-black/82 dark:text-white/82">
							Starting research…
						</div>
					</div>
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
						>Reconnecting to the session...</span
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
		60%,
		100% {
			opacity: 0.35;
			transform: translateY(0);
		}
		30% {
			opacity: 1;
			transform: translateY(-2px);
		}
	}
</style>
