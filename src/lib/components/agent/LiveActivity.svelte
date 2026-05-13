<script lang="ts">
	import { fade, fly, slide } from 'svelte/transition';
	import { formatDuration } from '$lib/time';
	import type { TimelineEvent } from '$lib/chat-types';

	let {
		events,
		startedAtMs = null,
		elapsedMs = null,
		completed = false
	}: {
		events: TimelineEvent[];
		startedAtMs?: number | null;
		elapsedMs?: number | null;
		completed?: boolean;
	} = $props();

	let now = $state(Date.now());
	let expanded = $state(false);
	let expandedTools: Record<string, boolean> = $state({});

	const IDLE_LABELS = ['Thinking', 'Working', 'Analyzing'] as const;
	type IdleLabel = (typeof IDLE_LABELS)[number];

	let idleLabel = $state<IdleLabel>(IDLE_LABELS[0]);

	function idleLabelDelay() {
		return 5000 + Math.random() * 5000;
	}

	function nextIdleLabel(label: IdleLabel): IdleLabel {
		const index = IDLE_LABELS.indexOf(label);
		return IDLE_LABELS[(index + 1) % IDLE_LABELS.length];
	}

	$effect(() => {
		if (completed) return;
		now = Date.now();
		const timer = setInterval(() => {
			now = Date.now();
		}, 1000);
		return () => clearInterval(timer);
	});

	$effect(() => {
		if (completed || events.length) return;
		idleLabel = IDLE_LABELS[0];
		let timer: ReturnType<typeof setTimeout>;
		const schedule = () => {
			timer = setTimeout(() => {
				idleLabel = nextIdleLabel(idleLabel);
				schedule();
			}, idleLabelDelay());
		};
		schedule();
		return () => clearTimeout(timer);
	});

	type DetailEvent = Extract<TimelineEvent, { kind: 'detail' }>;

	const FAMILY_LABEL: Record<DetailEvent['family'], string> = {
		'Google Maps': 'Looking up venue data',
		'Google reviews': 'Reading reviews',
		TripAdvisor: 'Cross-referencing TripAdvisor',
		'Searching the web': 'Searching the web',
		Analysis: 'Continuing research',
		'Public sources': 'Reading sources',
		Warnings: 'Checking sources'
	};
	const AUTHOR_LABEL: Record<string, string> = {
		router: 'Choosing next steps',
		context_enricher: 'Looking up the venue',
		research_lead: 'Reasoning',
		report_writer: 'Drafting final report',
		continue_research: 'Continuing research',
		follow_up: 'Following up'
	};
	function authorLabel(author: string | null | undefined): string {
		if (!author) return 'Reasoning';
		if (AUTHOR_LABEL[author]) return AUTHOR_LABEL[author];
		return author.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
	}

	const label = $derived.by<string>(() => {
		const latest = events[events.length - 1];
		if (!latest) return idleLabel;
		if (latest.kind === 'detail') {
			return latest.family === 'Analysis' ? latest.text : FAMILY_LABEL[latest.family];
		}
		return authorLabel(latest.author);
	});

	const LEAD_AUTHORS = new Set([
		'router',
		'context_enricher',
		'research_lead',
		'report_writer',
		'continue_research',
		'follow_up'
	]);
	const TOOL_PREVIEW_LIMIT = 5;
	const leadRe = /^\s*\*\*([^*]+)\*\*\s*([\s\S]*)$/;

	type StepThought = { id: string; text: string; open: boolean };
	type ThoughtSegment = { key: string; text: string; pending: boolean };
	type InlineSegment = { key: string; text: string; strong: boolean };
	type Step = { id: string; title: string; thoughts: StepThought[]; tools: DetailEvent[] };

	function hasRows(step: Step): boolean {
		return step.thoughts.length > 0 || step.tools.length > 0;
	}

	function visibleTools(step: Step): DetailEvent[] {
		return expandedTools[step.id] ? step.tools : step.tools.slice(0, TOOL_PREVIEW_LIMIT);
	}

	function hiddenToolCount(step: Step): number {
		return Math.max(0, step.tools.length - TOOL_PREVIEW_LIMIT);
	}

	function toggleTools(stepId: string) {
		expandedTools = { ...expandedTools, [stepId]: !expandedTools[stepId] };
	}

	function normalizeNewlines(text: string): string {
		return text
			.replace(/\\r\\n/g, '\n')
			.replace(/\\n/g, '\n')
			.replace(/\\r/g, '\n')
			.replace(/\n{3,}/g, '\n\n');
	}

	const steps = $derived.by<Step[]>(() => {
		const out: Step[] = [];
		let lastThoughtAuthor: string | null = null;
		let thoughtBuffer = '';
		let thoughtId = '';
		let thoughtAuthor: string | null = null;

		const startStep = (id: string, title = '') => {
			const step: Step = { id, title, thoughts: [], tools: [] };
			out.push(step);
			return step;
		};
		const ensureStep = (id: string) => out[out.length - 1] ?? startStep(id);

		const pushThought = (id: string, author: string | null, text: string, open: boolean) => {
			const authorKey = author ?? '';
			const normalized = normalizeNewlines(text);
			const match = normalized.match(leadRe);
			if (match) {
				const step = startStep(id, match[1].trim());
				const body = match[2].trim();
				if (body) step.thoughts.push({ id, text: body, open });
			} else {
				const current = out[out.length - 1];
				const shouldStartLeadStep =
					current &&
					hasRows(current) &&
					authorKey !== lastThoughtAuthor &&
					LEAD_AUTHORS.has(authorKey) &&
					!!lastThoughtAuthor &&
					LEAD_AUTHORS.has(lastThoughtAuthor);
				const step = shouldStartLeadStep ? startStep(id) : ensureStep(id);
				step.thoughts.push({ id, text: normalized, open });
			}
			if (authorKey) lastThoughtAuthor = authorKey;
		};

		const flushThought = (open = false) => {
			if (thoughtBuffer.trim()) pushThought(thoughtId, thoughtAuthor, thoughtBuffer, open);
			thoughtBuffer = '';
			thoughtId = '';
			thoughtAuthor = null;
		};

		for (const ev of events) {
			if (ev.kind === 'thought') {
				const text = normalizeNewlines(ev.text);
				const author = ev.author ?? null;
				if (thoughtBuffer.trim() && (author !== thoughtAuthor || leadRe.test(text))) flushThought();
				if (!thoughtId) {
					thoughtId = ev.id;
					thoughtAuthor = author;
				}
				thoughtBuffer += text;
			} else {
				flushThought();
				ensureStep(ev.id).tools.push(ev);
			}
		}
		flushThought(true);
		return out;
	});
	const showSteps = $derived(!completed || expanded);
	const durationLabel = $derived(
		formatDuration(
			completed ? (elapsedMs ?? 0) : (elapsedMs ?? (startedAtMs ? now - startedAtMs : 0))
		)
	);

	function thoughtSegments(thought: StepThought): ThoughtSegment[] {
		const parts = thought.text
			.split(/\n{2,}/)
			.map((part) => part.trim())
			.filter(Boolean);
		const trailingBoundary = /\n{2,}\s*$/.test(thought.text);
		return parts.map((part, index) => ({
			key: `${thought.id}:${index}`,
			text: part,
			pending: !completed && thought.open && index === parts.length - 1 && !trailingBoundary
		}));
	}

	function inlineSegments(text: string): InlineSegment[] {
		const out: InlineSegment[] = [];
		const re = /\*\*([^*]+)\*\*/g;
		let last = 0;
		let match: RegExpExecArray | null;

		const push = (value: string, strong: boolean) => {
			if (value) out.push({ key: `${out.length}`, text: value, strong });
		};

		while ((match = re.exec(text))) {
			if (match.index > last) push(text.slice(last, match.index), false);
			push(match[1], true);
			last = match.index + match[0].length;
		}
		if (last < text.length) push(text.slice(last), false);
		return out;
	}
</script>

{#snippet activityToggle(extraClass: string)}
	<button
		type="button"
		onclick={() => {
			expanded = !expanded;
		}}
		aria-expanded={expanded}
		class="flex w-full items-center justify-between gap-3 text-left text-[13px] text-black/55 transition-colors hover:text-black/70 dark:text-white/55 dark:hover:text-white/70 {extraClass}"
	>
		<span class="flex min-w-0 items-center gap-1.5">
			<svg
				class="h-3.5 w-3.5 shrink-0 transition-transform {expanded ? '-rotate-90' : ''}"
				viewBox="0 0 16 16"
				fill="none"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				aria-hidden="true"
			>
				<path d="M6 4l4 4-4 4" />
			</svg>
			<span>Analysis activity</span>
		</span>
		<span class="shrink-0 text-[12px] text-black/45 dark:text-white/45">{durationLabel} total</span>
	</button>
{/snippet}

{#if completed && !expanded}
	{@render activityToggle(
		'rounded-xl border border-black/8 px-3 py-2 hover:border-black/12 hover:bg-black/[0.02] dark:border-white/10 dark:hover:border-white/15 dark:hover:bg-white/[0.03]'
	)}
{:else}
	<div
		class="rounded-xl border border-black/8 bg-white/30 p-4 dark:border-white/10 dark:bg-white/[0.02] {!completed &&
		!steps.length
			? 'w-56'
			: ''}"
	>
		{#if showSteps && steps.length}
			<div transition:slide={{ duration: 180 }} class="flex flex-col gap-6">
				{#each steps as step, i (step.id)}
					<div class="relative pl-9">
						<div
							class="absolute top-0 left-0 flex h-7 w-7 items-center justify-center rounded-full border border-black/15 bg-white text-[12px] font-medium text-black/65 dark:border-white/20 dark:bg-cream dark:text-white/70"
						>
							{i + 1}
						</div>
						{#if i < steps.length - 1}
							<div
								class="absolute top-7 left-[13.5px] h-[calc(100%+1.5rem)] w-px bg-black/10 dark:bg-white/12"
							></div>
						{/if}

						{#if step.title}
							<div class="text-[15px] font-medium text-black/90 dark:text-white/90">
								{step.title}
							</div>
						{/if}

						{#each step.thoughts as thought (thought.id)}
							<div
								in:fade={{ duration: 220 }}
								class="prose-thought mt-1.5 text-[14px] leading-relaxed text-black/80 dark:text-white/80"
							>
								{#each thoughtSegments(thought) as segment (segment.key)}
									<div in:fade={{ duration: 180 }} class="thought-segment" class:pending={segment.pending}>
										{#each inlineSegments(segment.text) as inline (inline.key)}
											<span class="thought-inline" class:strong={inline.strong}>{inline.text}</span>
										{/each}
									</div>
								{/each}
							</div>
						{/each}

						{#if step.tools.length}
							<div
								class="mt-2.5 flex flex-col gap-1.5 border-l-2 border-emerald-500/35 pl-3 dark:border-emerald-400/30"
							>
								{#each visibleTools(step) as tool (tool.id)}
									<div
										in:fly={{ y: 4, duration: 200 }}
										class="flex items-start text-[13px] leading-snug text-black/60 dark:text-white/60"
									>
										<span class="break-words">{tool.text}</span>
									</div>
								{/each}
								{#if hiddenToolCount(step)}
									<button
										type="button"
										onclick={() => toggleTools(step.id)}
										class="mt-0.5 w-fit text-left text-[13px] leading-snug text-black/42 transition-colors hover:text-black/65 dark:text-white/42 dark:hover:text-white/65"
									>
										{expandedTools[step.id] ? 'Show fewer' : `Show ${hiddenToolCount(step)} more`}
									</button>
								{/if}
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}

		{#if completed}
			{@render activityToggle(
				showSteps && steps.length ? 'mt-4 border-t border-black/8 pt-3 dark:border-white/10' : ''
			)}
		{:else}
			<div
				class="{steps.length
					? 'mt-4 border-t border-black/8 pt-3 dark:border-white/10'
					: ''} flex items-baseline justify-between gap-2"
			>
				<div class="flex min-w-0 flex-1 items-baseline gap-2 text-[13px] text-black/55 dark:text-white/55">
					<span class="work-dot" aria-hidden="true"></span>
					<span class="status-shimmer truncate">{label}<span aria-hidden="true">...</span></span>
				</div>
				<span class="min-w-[4ch] shrink-0 text-right text-[12px] tabular-nums text-black/45 dark:text-white/45">
					{durationLabel}
				</span>
			</div>
		{/if}
	</div>
{/if}

<style>
	.work-dot {
		position: relative;
		top: calc(-0.05em - 1px);
		display: inline-block;
		width: 0.4rem;
		height: 0.4rem;
		flex-shrink: 0;
		border-radius: 999px;
		background-color: rgb(16 185 129 / 0.55);
		animation: work-dot-pulse 1.8s ease-in-out infinite;
	}
	@keyframes work-dot-pulse {
		0%,
		100% {
			background-color: rgb(16 185 129 / 0.45);
		}
		50% {
			background-color: rgb(16 185 129 / 0.95);
		}
	}
	.status-shimmer {
		--status-base: rgb(0 0 0 / 0.55);
		--status-highlight: rgb(0 0 0 / 0.78);

		color: transparent;
		background-image: linear-gradient(
			90deg,
			var(--status-base) 0%,
			var(--status-base) 38%,
			var(--status-highlight) 50%,
			var(--status-base) 62%,
			var(--status-base) 100%
		);
		background-size: 260% 100%;
		background-repeat: no-repeat;
		background-clip: text;
		-webkit-background-clip: text;
		animation: status-shimmer 6s cubic-bezier(0.4, 0, 0.2, 1) infinite;
	}
	:global(.dark) .status-shimmer {
		--status-base: rgb(255 255 255 / 0.55);
		--status-highlight: rgb(255 255 255 / 0.82);
	}
	@keyframes status-shimmer {
		0% {
			background-position: 100% 0;
		}
		42%,
		100% {
			background-position: 0% 0;
		}
	}
	.thought-segment {
		opacity: 1;
		transition: opacity 420ms ease;
		white-space: pre-line;
	}
	.thought-inline.strong {
		font-weight: 600;
	}
	.thought-segment.pending {
		opacity: 0.78;
	}
	.thought-segment + .thought-segment {
		margin-top: 0.4rem;
	}
	@media (prefers-reduced-motion: reduce) {
		.status-shimmer {
			color: var(--status-base);
			background: none;
			animation: none;
		}
	}
</style>
