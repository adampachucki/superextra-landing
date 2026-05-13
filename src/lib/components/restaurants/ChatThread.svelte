<script lang="ts">
	import { tick } from 'svelte';
	import { chatState } from '$lib/chat-state.svelte';
	import { tts } from '$lib/tts.svelte';
	import { splitChartSegments } from '$lib/chart-blocks';
	import type { ChatSourceProvider, TimelineEvent } from '$lib/chat-types';
	import { finalAnswerReveal } from '$lib/final-answer-reveal';
	import LiveActivity from '$lib/components/agent/LiveActivity.svelte';
	import { renderMarkdown } from '$lib/markdown';
	import ChartBlock from './ChartBlock.svelte';
	import SourceFavicon from './SourceFavicon.svelte';

	let scrollEl: HTMLDivElement | undefined = $state();
	let contentEl: HTMLDivElement | undefined = $state();
	let bottomEl: HTMLDivElement | undefined = $state();
	let scrollRun = 0;
	let scrollFrame: number | null = null;
	let scrolledSid: string | null = null;

	function isInView(node: HTMLElement) {
		const rect = node.getBoundingClientRect();
		return rect.top >= 0 && rect.bottom <= window.innerHeight - 160;
	}

	const revealTurnIndex = $derived.by(() => {
		const latest = chatState.messages[chatState.messages.length - 1];
		return latest?.role === 'agent' && latest.animateReveal ? latest.turnIndex : null;
	});
	const scrollKey = $derived(
		[
			chatState.messages.length,
			chatState.loading,
			chatState.error ?? '',
			chatState.liveTimeline
				.map((event) => `${event.id}:${'text' in event ? event.text.length : ''}`)
				.join('|')
		].join(':')
	);

	function promptBottomOffset() {
		const raw = getComputedStyle(document.documentElement).getPropertyValue('--chat-prompt-height');
		const promptHeight = Number.parseFloat(raw);
		return (Number.isFinite(promptHeight) ? promptHeight : 128) + 16;
	}

	function bottomScrollTop() {
		if (!bottomEl) return null;
		const scroller = document.scrollingElement ?? document.documentElement;
		const target =
			scroller.scrollTop +
			bottomEl.getBoundingClientRect().top -
			window.innerHeight +
			promptBottomOffset();
		return Math.max(0, Math.min(target, scroller.scrollHeight - window.innerHeight));
	}

	function scrollToBottom(behavior: ScrollBehavior) {
		const top = bottomScrollTop();
		if (top === null) return;
		if (behavior === 'auto') {
			const scroller = document.scrollingElement ?? document.documentElement;
			scroller.scrollTop = top;
			return;
		}
		window.scrollTo({ top, behavior });
	}

	function scheduleBottomScroll(behavior: ScrollBehavior) {
		if (scrollFrame !== null) cancelAnimationFrame(scrollFrame);
		scrollFrame = requestAnimationFrame(() => {
			scrollFrame = null;
			scrollToBottom(behavior);
		});
	}

	function isNearBottom() {
		const scroller = document.scrollingElement ?? document.documentElement;
		return scroller.scrollHeight - (window.scrollY + window.innerHeight) < 320;
	}

	$effect(() => {
		scrollKey;
		const sid = chatState.activeSid;
		if (!sid) {
			scrolledSid = null;
			return;
		}
		if (!scrollEl || chatState.messages.length === 0) return;
		const behavior: ScrollBehavior = scrolledSid === sid ? 'smooth' : 'auto';
		const turnToReveal = behavior === 'smooth' ? revealTurnIndex : null;
		const run = ++scrollRun;
		tick().then(() => {
			requestAnimationFrame(() => {
				if (run !== scrollRun) return;
				if (turnToReveal !== null) {
					const userMessage = scrollEl?.querySelector<HTMLElement>(
						`[data-user-turn="${turnToReveal}"]`
					);
					if (userMessage && !isInView(userMessage)) {
						userMessage.scrollIntoView({ block: 'start', behavior: 'smooth' });
					}
					return;
				}
				scrollToBottom(behavior);
				scrolledSid = sid;
			});
		});
	});

	$effect(() => {
		if (!contentEl || typeof ResizeObserver === 'undefined') return;
		const observer = new ResizeObserver(() => {
			if (!chatState.loading || !isNearBottom()) return;
			scheduleBottomScroll('smooth');
		});
		observer.observe(contentEl);
		return () => {
			observer.disconnect();
			if (scrollFrame !== null) cancelAnimationFrame(scrollFrame);
		};
	});

	const SOURCES_LIMIT = 19;
	const SOURCE_COUNT_MIN = 5;
	const ACTIVITY_THOUGHT_MIN = 2;
	const PROVIDER_LABELS: Record<ChatSourceProvider, string> = {
		google_maps: 'Google Maps',
		google_reviews: 'Google Reviews',
		tripadvisor: 'TripAdvisor'
	};
	const ERROR_COPY: Record<string, string> = {
		timeout: 'The analysis took longer than expected and was cut short.',
		progress_stalled: 'The analysis stalled before a final answer was delivered. Please try again.',
		heartbeat_lost:
			'The analysis stopped because the research worker lost connection. Please try again.',
		handoff_start_timeout: 'The analysis could not start. Please try again.',
		handoff_failed: 'The analysis could not start. Please try again.',
		empty_or_malformed_reply: 'The analysis finished without a usable answer. Please try again.',
		finalize_failed: 'The analysis finished, but the answer could not be saved. Please try again.',
		pipeline_error: 'The analysis could not be completed. Please try again.'
	};

	function errorMessage(code: string) {
		return ERROR_COPY[code] ?? ERROR_COPY.pipeline_error;
	}

	function sourceDomain(url: string, domain?: string): string {
		const candidate = domain?.trim();
		if (candidate) return cleanSourceHost(candidate);
		try {
			return cleanSourceHost(new URL(url).hostname);
		} catch {
			return '';
		}
	}

	function cleanSourceHost(value: string): string {
		try {
			const host = value.includes('://') ? new URL(value).hostname : value.split('/')[0];
			if (host.includes('vertexaisearch')) return '';
			return host.replace(/^www\./, '');
		} catch {
			return '';
		}
	}

	function thoughtCount(events: TimelineEvent[] | undefined): number {
		return events?.filter((event) => event.kind === 'thought').length ?? 0;
	}

	let expandedSources: Record<number, boolean> = $state({});
</script>

<div bind:this={scrollEl} class="px-5 py-6 md:px-6">
	<div bind:this={contentEl} class="mx-auto flex max-w-[700px] flex-col gap-5">
		{#each chatState.messages as msg, i (`${chatState.activeSid ?? 'local'}:${msg.turnIndex}:${msg.role}`)}
			<div
				class="flex {msg.role === 'user' ? 'scroll-mt-6 justify-end' : 'justify-start'}"
				data-user-turn={msg.role === 'user' ? msg.turnIndex : undefined}
			>
				{#if msg.role === 'user'}
					<div
						class="max-w-[85%] rounded-2xl rounded-br-md bg-cream-100 px-4 py-3 text-[15px] leading-relaxed text-black dark:text-white"
					>
						{msg.text}
					</div>
				{:else}
					<div class="max-w-[95%] min-w-0 px-1 py-1">
						<div
							class="chat-markdown prose max-w-none min-w-0 text-[15px] leading-relaxed text-black/80 dark:text-white/80 prose-headings:text-black dark:prose-headings:text-white prose-a:text-black prose-a:underline dark:prose-a:text-white prose-strong:text-black dark:prose-strong:text-white"
							use:finalAnswerReveal={msg.animateReveal
								? () => chatState.markReplyRevealed(msg.turnIndex)
								: undefined}
						>
							{#each splitChartSegments(msg.text) as seg, segIdx (segIdx)}
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
								class="group inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] transition-colors {tts.loading ===
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

						{#if msg.turnSummary && thoughtCount(msg.activityEvents) >= ACTIVITY_THOUGHT_MIN}
							<div class="mt-4">
								<LiveActivity
									events={msg.activityEvents ?? []}
									elapsedMs={msg.turnSummary.elapsedMs}
									completed
								/>
							</div>
						{/if}

						{#if msg.sources && msg.sources.length >= SOURCE_COUNT_MIN}
							{@const showAll = expandedSources[msg.turnIndex]}
							{@const visible = showAll ? msg.sources : msg.sources.slice(0, SOURCES_LIMIT)}
							<div class="mt-5">
								<span class="mb-2 block text-[12px] font-medium text-black/40 dark:text-white/40"
									>Sources ({msg.sources.length})</span
								>
								<div class="flex flex-wrap gap-1.5">
									{#each visible as src (`${src.url}:${src.title}`)}
										{@const domain = sourceDomain(src.url, src.domain)}
										{@const label = src.provider
											? PROVIDER_LABELS[src.provider]
											: domain || src.title}
										<a
											href={src.url}
											target="_blank"
											rel="noopener noreferrer"
											class="group inline-flex items-center gap-1.5 rounded-full border border-black/5 px-2.5 py-1 no-underline transition-colors hover:border-black/10 hover:bg-black/[0.02] dark:border-white/5 dark:hover:border-white/10 dark:hover:bg-white/[0.02]"
										>
											<SourceFavicon {domain} {label} />
											<span
												class="text-[12px] leading-snug text-black/50 transition-colors group-hover:text-black/70 dark:text-white/50 dark:group-hover:text-white/70"
											>
												{label}
											</span>
										</a>
									{/each}
									{#if msg.sources.length > SOURCES_LIMIT && !showAll}
										<button
											onclick={() => {
												expandedSources[msg.turnIndex] = true;
											}}
											class="inline-flex items-center rounded-full border border-black/5 px-2.5 py-1 text-[12px] leading-snug text-black/40 transition-colors hover:border-black/10 hover:bg-black/[0.02] hover:text-black/60 dark:border-white/5 dark:text-white/40 dark:hover:border-white/10 dark:hover:bg-white/[0.02] dark:hover:text-white/60"
										>
											+{msg.sources.length - SOURCES_LIMIT} more
										</button>
									{/if}
								</div>
							</div>
						{/if}
					</div>
				{/if}
			</div>
		{/each}

		{#if chatState.loading}
			<div class="flex justify-start">
				<div class="max-w-[95%] px-1 py-1">
					<LiveActivity
						events={chatState.liveTimeline}
						startedAtMs={chatState.currentTurnStartedAtMs}
					/>
				</div>
			</div>
		{/if}

		{#if chatState.error}
			{@const isTimeout = chatState.error === 'timeout'}
			{@const message = errorMessage(chatState.error)}
			<div class="flex justify-start">
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
						{message}
					</span>
				</div>
			</div>
		{/if}
		<div bind:this={bottomEl} class="chat-bottom-anchor" aria-hidden="true"></div>
	</div>
</div>

<style>
	.chat-bottom-anchor {
		scroll-margin-bottom: calc(var(--chat-prompt-height, 8rem) + 1rem);
	}

	:global(.chat-markdown .markdown-table-scroll) {
		width: 100%;
		max-width: 100%;
		margin: 2em 0;
		overflow-x: auto;
		-webkit-overflow-scrolling: touch;
	}

	:global(.chat-markdown .markdown-table-scroll table) {
		width: 100%;
		min-width: 100%;
		margin: 0;
		table-layout: auto;
	}

	:global(.chat-markdown .markdown-table-scroll th),
	:global(.chat-markdown .markdown-table-scroll td) {
		white-space: normal;
		overflow-wrap: anywhere;
		word-break: normal;
	}

	@media (max-width: 640px) {
		:global(.chat-markdown .markdown-table-scroll table) {
			min-width: max(100%, min(56rem, calc(var(--markdown-table-columns, 1) * 12rem)));
		}
	}
</style>
