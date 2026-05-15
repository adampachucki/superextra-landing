<script lang="ts">
	import { tick } from 'svelte';
	import { chatState } from '$lib/chat-state.svelte';
	import { tts } from '$lib/tts.svelte';
	import { splitChartSegments } from '$lib/chart-blocks';
	import type { ChatSource, ChatSourceProvider, TimelineEvent } from '$lib/chat-types';
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
	const PROVIDER_LABELS: Partial<Record<ChatSourceProvider, string>> = {
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

	function sourceProviderLabel(provider: ChatSourceProvider | undefined): string | undefined {
		return provider ? PROVIDER_LABELS[provider] : undefined;
	}

	function sourceLabel(src: ChatSource, domain: string): string {
		return sourceProviderLabel(src.provider) ?? (domain || src.title);
	}

	function sourceGroupKey(src: ChatSource): string {
		const providerLabel = sourceProviderLabel(src.provider);
		if (providerLabel && src.provider) return `provider:${src.provider}`;
		const domain = sourceDomain(src.url, src.domain).toLowerCase();
		if (domain) return `domain:${domain}`;
		return `url:${src.url}`;
	}

	function sourceRank(src: ChatSource, seed: number): number {
		let hash = 2166136261;
		const value = `${seed}:${src.url}:${src.title}`;
		for (let i = 0; i < value.length; i += 1) {
			hash ^= value.charCodeAt(i);
			hash = Math.imul(hash, 16777619);
		}
		return hash >>> 0;
	}

	function varietyFirstSources(sources: ChatSource[], seed: number): ChatSource[] {
		const groups: { key: string; sources: ChatSource[] }[] = [];
		for (const source of sources) {
			const key = sourceGroupKey(source);
			const group = groups.find((entry) => entry.key === key);
			if (group) {
				group.sources.push(source);
			} else {
				groups.push({ key, sources: [source] });
			}
		}

		const first = groups.flatMap((group) => group.sources.slice(0, 1));
		const rest = groups.flatMap((group) => group.sources.slice(1));
		rest.sort((a, b) => sourceRank(a, seed) - sourceRank(b, seed));
		return [...first, ...rest];
	}

	function thoughtCount(events: TimelineEvent[] | undefined): number {
		return events?.filter((event) => event.kind === 'thought').length ?? 0;
	}

	let expandedSources: Record<number, boolean> = $state({});
</script>

<div bind:this={scrollEl} class="px-5 py-6 md:px-6">
	<div bind:this={contentEl} class="flex flex-col gap-5">
		{#each chatState.messages as msg, i (`${chatState.activeSid ?? 'local'}:${msg.turnIndex}:${msg.role}`)}
			{#if msg.role === 'user'}
				<div
					class="mx-auto flex w-full max-w-[700px] scroll-mt-6 justify-end"
					data-user-turn={msg.turnIndex}
				>
					<div
						class="max-w-[85%] rounded-2xl rounded-br-md bg-cream-100 px-4 py-3 text-[15px] leading-relaxed text-black dark:text-white"
					>
						{msg.text}
					</div>
				</div>
			{:else}
				<div class="assistant-row min-w-0 px-1 py-1">
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
					<div class="mt-2 flex max-w-[700px] justify-end">
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
						<div class="mt-4 max-w-[700px]">
							<LiveActivity
								events={msg.activityEvents ?? []}
								elapsedMs={msg.turnSummary.elapsedMs}
								completed
							/>
						</div>
					{/if}

					{#if msg.sources && msg.sources.length >= SOURCE_COUNT_MIN}
						{@const showAll = expandedSources[msg.turnIndex]}
						{@const displaySources = varietyFirstSources(msg.sources, msg.turnIndex)}
						{@const visible = showAll ? displaySources : displaySources.slice(0, SOURCES_LIMIT)}
						<div class="mt-5 max-w-[700px]">
							<span class="mb-2 block text-[12px] font-medium text-black/40 dark:text-white/40"
								>Sources ({msg.sources.length})</span
							>
							<div class="flex flex-wrap gap-1.5">
								{#each visible as src (`${src.url}:${src.title}`)}
									{@const domain = sourceDomain(src.url, src.domain)}
									{@const label = sourceLabel(src, domain)}
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
		{/each}

		{#if chatState.loading}
			<div class="assistant-row max-w-[700px] min-w-0 px-1 py-1">
				<LiveActivity
					events={chatState.liveTimeline}
					startedAtMs={chatState.currentTurnStartedAtMs}
					statusLabel={chatState.liveStatusLabel}
				/>
			</div>
		{/if}

		{#if chatState.error}
			{@const isTimeout = chatState.error === 'timeout'}
			{@const message = errorMessage(chatState.error)}
			<div class="assistant-row max-w-[700px]">
				<div
					class="inline-flex items-center gap-3 rounded-2xl border px-5 py-3 {isTimeout
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

	/* Each assistant message row's left edge sits where a centered
	 * 700px column would start in the available space, so text aligns
	 * with the user-message column. The row has no right max — its
	 * right edge follows the parent's right padding, giving tables
	 * room to extend rightward without negative margins. */
	.assistant-row {
		margin-left: max(0px, calc((100% - 700px) / 2));
		margin-right: 0;
	}

	/* Text-level prose children stay at reading width; tables (and any
	 * other intentionally-wide block) take the row's full width. */
	:global(.chat-markdown > p),
	:global(.chat-markdown > ul),
	:global(.chat-markdown > ol),
	:global(.chat-markdown > h1),
	:global(.chat-markdown > h2),
	:global(.chat-markdown > h3),
	:global(.chat-markdown > h4),
	:global(.chat-markdown > h5),
	:global(.chat-markdown > h6),
	:global(.chat-markdown > blockquote),
	:global(.chat-markdown > pre) {
		max-width: 700px;
	}

	:global(.chat-markdown .markdown-table-scroll) {
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

	/* `overflow-wrap: break-word` (not `anywhere`) preserves each
	 * column's natural minimum width (longest word). The `min-width`
	 * floor stops the auto-layout algorithm from squeezing short-label
	 * columns below a readable threshold when one cell carries paragraph
	 * content — without it, auto-layout hands almost the entire width
	 * to the wordy column. */
	:global(.chat-markdown .markdown-table-scroll th),
	:global(.chat-markdown .markdown-table-scroll td) {
		min-width: 7rem;
		white-space: normal;
		overflow-wrap: break-word;
		word-break: normal;
	}

	/* Mobile: let the table touch the right viewport edge (past the
	 * page's px-5 padding + the assistant-row's px-1), and force a
	 * minimum width so 4+ column tables aren't crammed into a narrow
	 * viewport. */
	@media (max-width: 640px) {
		:global(.chat-markdown .markdown-table-scroll) {
			margin-right: -1.5rem;
		}
		:global(.chat-markdown .markdown-table-scroll table) {
			min-width: max(100%, min(56rem, calc(var(--markdown-table-columns, 1) * 12rem)));
		}
	}
</style>
