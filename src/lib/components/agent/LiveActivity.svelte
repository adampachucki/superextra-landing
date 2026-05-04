<script lang="ts">
	import { marked } from 'marked';
	import type { TimelineEvent } from '$lib/chat-types';
	import ProgressEventRow from './ProgressEventRow.svelte';
	import ProgressWrapper from './ProgressWrapper.svelte';
	import TypewriterText from './TypewriterText.svelte';

	marked.setOptions({ breaks: true, gfm: true });
	function renderMarkdown(md: string): string {
		return marked.parse(md) as string;
	}

	let {
		events,
		startedAtMs
	}: {
		events: TimelineEvent[];
		startedAtMs: number | null;
	} = $props();

	let now = $state(Date.now());

	$effect(() => {
		now = Date.now();
		const timer = setInterval(() => {
			now = Date.now();
		}, 1000);
		return () => clearInterval(timer);
	});

	function formatDuration(ms: number): string {
		const totalSeconds = Math.max(0, Math.floor(ms / 1000));
		const minutes = Math.floor(totalSeconds / 60);
		const seconds = totalSeconds % 60;
		if (minutes > 0) return `${minutes}m ${seconds}s`;
		return `${seconds}s`;
	}

	const LEAD_AUTHORS = new Set(['router', 'context_enricher', 'research_lead', 'follow_up']);
	const leadRe = /^\s*\*\*([^*]+)\*\*\s*([\s\S]*)$/;

	type DetailEvent = Extract<TimelineEvent, { kind: 'detail' }>;
	type StepThought = { id: string; text: string; markdown: boolean };
	type Step = { id: string; title: string; thoughts: StepThought[]; tools: DetailEvent[] };

	function hasRows(step: Step): boolean {
		return step.thoughts.length > 0 || step.tools.length > 0;
	}

	const steps = $derived.by<Step[]>(() => {
		const out: Step[] = [];
		let lastThoughtAuthor: string | null = null;

		const startStep = (id: string, title = '') => {
			const step: Step = { id, title, thoughts: [], tools: [] };
			out.push(step);
			return step;
		};
		const ensureStep = (id: string) => out[out.length - 1] ?? startStep(id);

		for (const ev of events) {
			if (ev.kind === 'thought') {
				const author = ev.author ?? '';
				const match = ev.text.match(leadRe);
				if (match) {
					const step = startStep(ev.id, match[1].trim());
					const body = match[2].trim();
					if (body) step.thoughts.push({ id: ev.id, text: body, markdown: true });
				} else {
					const current = out[out.length - 1];
					const shouldStartLeadStep =
						current &&
						hasRows(current) &&
						author !== lastThoughtAuthor &&
						LEAD_AUTHORS.has(author) &&
						!!lastThoughtAuthor &&
						LEAD_AUTHORS.has(lastThoughtAuthor);
					const step = shouldStartLeadStep ? startStep(ev.id) : ensureStep(ev.id);
					step.thoughts.push({ id: ev.id, text: ev.text, markdown: true });
				}
				if (author) lastThoughtAuthor = author;
			} else if (ev.kind === 'note') {
				ensureStep(ev.id).thoughts.push({ id: ev.id, text: ev.text, markdown: false });
			} else {
				ensureStep(ev.id).tools.push(ev);
			}
		}

		return out;
	});
</script>

<div class="flex flex-col gap-3">
	<div class="text-[13px] text-black/55 dark:text-white/55">
		Working for {formatDuration(startedAtMs ? now - startedAtMs : 0)}
	</div>

	<ProgressWrapper>
		{#each steps as step, i (step.id)}
			<div class="relative pl-9">
				<div
					class="absolute top-0 left-0 flex h-7 w-7 items-center justify-center rounded-full border border-black/15 bg-white text-[12px] font-medium text-black/65 dark:border-white/20 dark:bg-cream dark:text-white/70"
				>
					{i + 1}
				</div>
				{#if i < steps.length - 1}
					<div
						class="absolute top-7 left-[13.5px] h-[calc(100%+1.25rem)] w-px bg-black/10 dark:bg-white/12"
					></div>
				{/if}

				{#if step.title}
					<div class="text-[15px] font-medium text-black/90 dark:text-white/90">
						{step.title}
					</div>
				{/if}

				{#each step.thoughts as thought (thought.id)}
					<div
						class="prose-thought mt-1.5 text-[14px] leading-relaxed text-black/70 dark:text-white/70"
					>
						<TypewriterText text={thought.text} charsPerFrame={3}>
							{#snippet children(text)}
								{#if thought.markdown}
									{@html renderMarkdown(text)}
								{:else}
									{text}
								{/if}
							{/snippet}
						</TypewriterText>
					</div>
				{/each}

				{#if step.tools.length}
					<div class="mt-2.5 flex flex-col gap-1.5 border-l-2 border-emerald-500/35 pl-3 dark:border-emerald-400/30">
						{#each step.tools as tool (tool.id)}
							<ProgressEventRow label={tool.family} detail={tool.text} />
						{/each}
					</div>
				{/if}
			</div>
		{/each}
	</ProgressWrapper>
</div>

<style>
	.prose-thought :global(p) {
		margin: 0 0 0.4rem 0;
	}
	.prose-thought :global(p:last-child) {
		margin-bottom: 0;
	}
	.prose-thought :global(strong) {
		font-weight: 600;
	}
</style>
