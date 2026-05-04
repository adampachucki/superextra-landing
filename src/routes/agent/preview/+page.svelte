<script lang="ts">
	import { marked } from 'marked';
	import { fade, fly } from 'svelte/transition';
	import { onDestroy, onMount } from 'svelte';
	import { page } from '$app/state';
	import { ensureAnonAuth, getFirebase } from '$lib/firebase';
	import TypewriterText from '$lib/components/agent/TypewriterText.svelte';

	marked.setOptions({ breaks: true, gfm: true });

	type Family =
		| 'Google Maps'
		| 'TripAdvisor'
		| 'Google reviews'
		| 'Searching the web'
		| 'Public sources';

	// `author` mirrors ADK's `event.author`. `string` (not a union) because
	// live data from Firestore can carry any specialist or sub-agent name.
	type Author = string;

	type Frame =
		| { kind: 'thought'; author: Author; text: string }
		| { kind: 'note'; author: Author; text: string }
		| { kind: 'tool'; author: Author; family: Family; text: string };

	// One shared simulated run — used by all three designs. Same data the real
	// stream would deliver: model thought-summary deltas (best-effort, gaps OK)
	// interleaved with tool activity rows. Each entry has an `at` ms offset and
	// the agent that produced it.
	const script: { at: number; frame: Frame }[] = [
		{
			at: 0,
			frame: {
				kind: 'thought',
				author: 'context_enricher',
				text: '**Looking up Pizzeria Stamatello**\n\n'
			}
		},
		{
			at: 800,
			frame: {
				kind: 'thought',
				author: 'context_enricher',
				text: 'I want a baseline on the venue itself — its rating, review volume, and the closest neapolitan-leaning competitors within walking distance — before I read anything anyone has written about it.\n\n'
			}
		},
		{
			at: 2400,
			frame: {
				kind: 'tool',
				author: 'context_enricher',
				family: 'Google Maps',
				text: 'Checking Google Maps for Pizzeria Stamatello and 6 nearby competitors'
			}
		},
		// Demonstrates the best-effort case: this thought block has no bold lead.
		// Steps view falls back to "untitled step", Stream and Rail render normally.
		{
			at: 3800,
			frame: {
				kind: 'thought',
				author: 'research_lead',
				text: 'Now I want to see how Stamatello stacks up on each platform that travelers and locals actually use, and whether the rating spread tells a different story than the volume.\n\n'
			}
		},
		{
			at: 5800,
			frame: {
				kind: 'tool',
				author: 'research_lead',
				family: 'Google reviews',
				text: 'Reading 128 Google reviews for Pizzeria Stamatello'
			}
		},
		{
			at: 6800,
			frame: {
				kind: 'tool',
				author: 'research_lead',
				family: 'TripAdvisor',
				text: 'Cross-referencing TripAdvisor for Pizzeria Stamatello (54 reviews)'
			}
		},
		{
			at: 8200,
			frame: {
				kind: 'thought',
				author: 'research_lead',
				text: '**Looking for market context**\n\n'
			}
		},
		{
			at: 9000,
			frame: {
				kind: 'thought',
				author: 'research_lead',
				text: 'The Mokotów dining scene shifted noticeably last year, so I need press and aggregator coverage to set this venue against the trend rather than against itself.\n\n'
			}
		},
		{
			at: 10000,
			frame: {
				kind: 'tool',
				author: 'research_lead',
				family: 'Searching the web',
				text: 'Searching for "warsaw neapolitan pizza market 2026"'
			}
		},
		{
			at: 10800,
			frame: {
				kind: 'tool',
				author: 'research_lead',
				family: 'Searching the web',
				text: 'Searching for "mokotów dining trends"'
			}
		},
		{
			at: 12200,
			frame: {
				kind: 'tool',
				author: 'research_lead',
				family: 'Public sources',
				text: 'Reading warsawinsider.pl/pizzeria-stamatello-review'
			}
		},
		{
			at: 12900,
			frame: {
				kind: 'tool',
				author: 'research_lead',
				family: 'Public sources',
				text: 'Reading gazetawyborcza.pl/dining-trends-2026'
			}
		},
		{
			at: 14000,
			frame: {
				kind: 'thought',
				author: 'research_lead',
				text: '**Pulling it together**\n\n'
			}
		},
		{
			at: 14800,
			frame: {
				kind: 'thought',
				author: 'research_lead',
				text: 'These three angles — venue, platform spread, market context — give me enough to answer the market-fit question with more than just headline ratings.'
			}
		}
	];

	const totalDuration = script[script.length - 1].at + 1500;

	// ---- Honest label derivation ----
	// No cycling array, no setInterval. The label comes from real signals:
	//   1. If a tool was the most recent thing → friendly verb for that family
	//   2. Else → friendly name for the current `author` (ADK event.author)
	//   3. Idle gap → freeze on the last derived label, no rotation
	const FAMILY_LABEL: Record<Family, string> = {
		'Google Maps': 'Looking up venue data',
		'Google reviews': 'Reading reviews',
		TripAdvisor: 'Cross-referencing TripAdvisor',
		'Searching the web': 'Searching the web',
		'Public sources': 'Reading sources'
	};
	const AUTHOR_LABEL: Record<string, string> = {
		router: 'Routing your question',
		context_enricher: 'Looking up the venue',
		research_lead: 'Reasoning',
		follow_up: 'Following up'
	};
	function authorLabel(author: string | null | undefined): string {
		if (!author) return 'Working';
		if (AUTHOR_LABEL[author]) return AUTHOR_LABEL[author];
		// Specialist authors arrive verbatim ("review_analyst", "guest_intelligence").
		// Convert "snake_case" → "Snake case" as a fallback.
		return author.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
	}

	// Active design + replay state.
	type Design = 'stream' | 'rail' | 'steps';
	let design = $state<Design>('stream');
	let frames = $state<Frame[]>([]);
	let running = $state(false);
	let elapsed = $state(0);
	let timers: ReturnType<typeof setTimeout>[] = [];
	let elapsedTimer: ReturnType<typeof setInterval> | null = null;

	function clearAll() {
		for (const t of timers) clearTimeout(t);
		timers = [];
		if (elapsedTimer) clearInterval(elapsedTimer);
		elapsedTimer = null;
	}

	function play() {
		clearAll();
		frames = [];
		running = true;
		elapsed = 0;
		const start = Date.now();
		elapsedTimer = setInterval(() => {
			elapsed = Date.now() - start;
		}, 200);
		for (const { at, frame } of script) {
			timers.push(
				setTimeout(() => {
					frames = [...frames, frame];
				}, at)
			);
		}
		timers.push(
			setTimeout(() => {
				running = false;
				if (elapsedTimer) clearInterval(elapsedTimer);
				elapsedTimer = null;
			}, totalDuration)
		);
	}

	onDestroy(() => clearAll());

	// Derived label — picks the latest frame's signal.
	const label = $derived.by<string>(() => {
		if (frames.length === 0) return 'Working';
		const latest = frames[frames.length - 1];
		if (latest.kind === 'tool') return FAMILY_LABEL[latest.family];
		return authorLabel(latest.author);
	});

	// Walk frames in arrival order → render-blocks. Thoughts buffer until a
	// non-thought frame arrives, then flush as one markdown block.
	type Block =
		| { kind: 'thought'; markdown: string }
		| { kind: 'note'; text: string }
		| { kind: 'tool'; family: Family; text: string };
	const blocks = $derived.by<Block[]>(() => {
		const out: Block[] = [];
		let buffer = '';
		const flush = () => {
			if (buffer.trim()) out.push({ kind: 'thought', markdown: buffer });
			buffer = '';
		};
		for (const f of frames) {
			if (f.kind === 'thought') {
				buffer += f.text;
			} else if (f.kind === 'note') {
				flush();
				out.push({ kind: 'note', text: f.text });
			} else {
				flush();
				out.push({ kind: 'tool', family: f.family, text: f.text });
			}
		}
		flush();
		return out;
	});

	const tools = $derived(
		frames.filter((f): f is Extract<Frame, { kind: 'tool' }> => f.kind === 'tool')
	);

	// For "steps": group blocks into steps. A bold-led thought opens a new step.
	// If a thought block has no bold lead (best-effort gap), it attaches to the
	// previous step or starts an untitled one.
	type Step = { title: string; thoughts: string[]; tools: { family: Family; text: string }[] };
	const steps = $derived.by<Step[]>(() => {
		const out: Step[] = [];
		const headerRe = /^\s*\*\*([^*]+)\*\*\s*([\s\S]*)$/;
		for (const b of blocks) {
			if (b.kind === 'thought') {
				const m = b.markdown.match(headerRe);
				if (m) {
					out.push({ title: m[1].trim(), thoughts: m[2].trim() ? [m[2].trim()] : [], tools: [] });
				} else {
					if (out.length === 0) out.push({ title: '', thoughts: [], tools: [] });
					out[out.length - 1].thoughts.push(b.markdown);
				}
			} else if (b.kind === 'note') {
				if (out.length === 0) out.push({ title: '', thoughts: [], tools: [] });
				out[out.length - 1].thoughts.push(b.text);
			} else {
				if (out.length === 0) out.push({ title: '', thoughts: [], tools: [] });
				out[out.length - 1].tools.push({ family: b.family, text: b.text });
			}
		}
		return out;
	});

	// ---- Live Firestore mode ----
	// When the URL has `?sid=<sessionId>`, subscribe to that session's events
	// and stream them into `frames` as they arrive. Disables the simulated
	// replay button — the data is the run.
	let liveSid = $state('');
	let liveStatus = $state<'idle' | 'subscribing' | 'live' | 'error'>('idle');
	let liveError = $state<string | null>(null);
	let liveUnsubscribe: (() => void) | null = null;
	// Replay speed for finished runs: 1 = real-time, 4 = 4× faster, etc.
	// `Infinity` would mean "instant", but that defeats the purpose of seeing
	// cadence — we never go faster than 8×.
	let replaySpeed = $state(2);
	const SPEED_OPTIONS = [1, 2, 4, 8] as const;
	// First-event ts in the snapshot, used to schedule subsequent events at
	// (event.ts − first.ts) / replaySpeed wall-clock ms.
	let liveFirstEventTs: number | null = null;
	let liveFirstWallTime: number | null = null;
	let liveLastScheduledDelay = 0;
	let liveFrameTimers: ReturnType<typeof setTimeout>[] = [];
	// Minimum wall-clock spacing between consecutive scheduled events. Many
	// docs share the same ts (parallel AgentTool children write within ms of
	// each other) — without a min gap they'd all render together. 180ms is
	// fast enough to keep up with bursts but slow enough to be visually
	// distinct.
	const MIN_GAP_MS = 180;

	function disconnectLive() {
		if (liveUnsubscribe) {
			liveUnsubscribe();
			liveUnsubscribe = null;
		}
		for (const t of liveFrameTimers) clearTimeout(t);
		liveFrameTimers = [];
		liveFirstEventTs = null;
		liveFirstWallTime = null;
		liveLastScheduledDelay = 0;
	}

	async function subscribeLive(sid: string) {
		disconnectLive();
		clearAll();
		frames = [];
		elapsed = 0;
		liveSid = sid;
		liveStatus = 'subscribing';
		liveError = null;

		try {
			await ensureAnonAuth();
			const { db } = await getFirebase();
			const fs = await import('firebase/firestore');
			// Find the run we should attach to: prefer `currentRunId` from the
			// session doc; if it isn't set, fall back to the most recent doc in
			// the events subcollection.
			const sessSnap = await fs.getDoc(fs.doc(db, 'sessions', sid));
			const runId = (sessSnap.data() as { currentRunId?: string } | undefined)?.currentRunId;
			if (!runId) {
				liveError = `session ${sid} has no currentRunId`;
				liveStatus = 'error';
				return;
			}
			const start = Date.now();
			elapsedTimer = setInterval(() => {
				elapsed = Date.now() - start;
			}, 200);

			const q = fs.query(
				fs.collection(db, 'sessions', sid, 'events'),
				fs.where('runId', '==', runId),
				fs.orderBy('attempt'),
				fs.orderBy('seqInAttempt')
			);
			liveStatus = 'live';
			liveUnsubscribe = fs.onSnapshot(
				q,
				(snap) => {
					// Each `added` doc is scheduled for append at
					// (doc.ts − firstEventTs)/replaySpeed wall-clock ms after the
					// first event we saw. For a run still in progress, doc.ts is
					// roughly current time so the delay is ~0; for a finished run
					// we see all docs at once and replay at requested speed.
					for (const change of snap.docChanges()) {
						if (change.type !== 'added') continue;
						const docData = change.doc.data() as {
							type?: string;
							data?: Record<string, unknown>;
							ts?: { toMillis?: () => number; seconds?: number };
						};
						if (docData.type !== 'timeline') continue;
						const data = docData.data ?? {};
						const kind = data.kind as string | undefined;
						const tsMs =
							docData.ts && typeof docData.ts.toMillis === 'function'
								? docData.ts.toMillis()
								: docData.ts && typeof docData.ts.seconds === 'number'
									? docData.ts.seconds * 1000
									: Date.now();
						if (liveFirstEventTs === null) {
							liveFirstEventTs = tsMs;
							liveFirstWallTime = Date.now();
						}
						const targetDelay =
							((tsMs - liveFirstEventTs) / replaySpeed) -
							(Date.now() - (liveFirstWallTime ?? Date.now()));
						// Floor at 0, then enforce a minimum gap from the previous
						// scheduled event so events that share a ts (parallel
						// specialist runs) don't all flush at the same wall-clock
						// instant.
						let delay = Math.max(0, targetDelay);
						delay = Math.max(delay, liveLastScheduledDelay + MIN_GAP_MS);
						liveLastScheduledDelay = delay;
						let frame: Frame | null = null;
						if (kind === 'thought') {
							frame = {
								kind: 'thought',
								author: (data.author as string) ?? '',
								text: String(data.text ?? '')
							};
						} else if (kind === 'note') {
							frame = { kind: 'note', author: '', text: String(data.text ?? '') };
						} else if (kind === 'detail') {
							frame = {
								kind: 'tool',
								author: '',
								family: data.family as Family,
								text: String(data.text ?? '')
							};
						}
						if (frame) {
							const f = frame;
							liveFrameTimers.push(
								setTimeout(() => {
									frames = [...frames, f];
								}, delay)
							);
						}
					}
				},
				(err) => {
					liveError = err.message;
					liveStatus = 'error';
				}
			);
		} catch (err) {
			liveError = err instanceof Error ? err.message : String(err);
			liveStatus = 'error';
		}
	}

	let liveSidInput = $state('');

	onMount(() => {
		const sid = page.url.searchParams.get('sid');
		if (sid) {
			liveSidInput = sid;
			void subscribeLive(sid);
		}
	});

	onDestroy(() => disconnectLive());

	function fmtSeconds(ms: number): string {
		const total = Math.max(0, Math.floor(ms / 1000));
		const minutes = Math.floor(total / 60);
		const seconds = total % 60;
		if (minutes > 0) return `${minutes}m ${seconds}s`;
		return `${seconds}s`;
	}

	function render(md: string): string {
		return marked.parse(md) as string;
	}
</script>

<svelte:head>
	<title>Live Activity — UX Preview</title>
</svelte:head>

<div class="min-h-screen bg-cream px-6 py-10 text-black dark:bg-cream dark:text-white">
	<div class="mx-auto flex max-w-[820px] flex-col gap-8">
		<header class="flex flex-col gap-3">
			<h1 class="text-[clamp(1.5rem,2.6vw,2rem)] font-medium">Live activity — three approaches</h1>
			<p class="text-[14px] text-black/60 dark:text-white/60">
				Each approach treats the model's own thought summaries (Gemini
				<code>thinkingConfig.includeThoughts</code>) as the main channel and surfaces tool
				activity as inline rows. The header label is derived from real ADK signals
				(<code>event.author</code> or the most recent tool family) — no cycling word, no
				hardcoded vocabulary on the model side.
			</p>

			<div class="mt-2 flex flex-wrap items-center gap-2">
				<div class="flex rounded-full border border-black/10 p-0.5 dark:border-white/15">
					{#each [{ id: 'stream', label: 'Thought stream' }, { id: 'rail', label: 'Stream + activity rail' }, { id: 'steps', label: 'Step blocks' }] as opt (opt.id)}
						<button
							type="button"
							class="rounded-full px-3 py-1 text-[12.5px] transition-colors {design === opt.id
								? 'bg-black text-white dark:bg-white dark:text-black'
								: 'text-black/65 hover:text-black dark:text-white/65 dark:hover:text-white'}"
							onclick={() => (design = opt.id as Design)}
						>
							{opt.label}
						</button>
					{/each}
				</div>

				{#if liveStatus !== 'live'}
					<button
						type="button"
						onclick={play}
						class="rounded-full border border-black px-3.5 py-1 text-[12.5px] font-medium text-black hover:bg-black hover:text-white dark:border-white dark:text-white dark:hover:bg-white dark:hover:text-black"
					>
						{running ? 'Restart' : frames.length ? 'Replay' : 'Play simulated run'}
					</button>
				{/if}

				{#if (running || frames.length) && liveStatus !== 'live'}
					<span class="text-[12px] text-black/45 dark:text-white/45">{fmtSeconds(elapsed)}</span>
				{/if}
			</div>

			<div class="mt-1 flex flex-wrap items-center gap-2 text-[12.5px]">
				<span class="text-black/55 dark:text-white/55">Or attach to a live session:</span>
				<input
					type="text"
					placeholder="sid e.g. probe-thought-20260504-093657"
					bind:value={liveSidInput}
					class="w-[320px] rounded-md border border-black/15 bg-white/60 px-2.5 py-1 text-[12.5px] text-black placeholder:text-black/30 dark:border-white/20 dark:bg-black/20 dark:text-white dark:placeholder:text-white/30"
				/>
				<button
					type="button"
					onclick={() => subscribeLive(liveSidInput.trim())}
					disabled={!liveSidInput.trim()}
					class="rounded-full border border-black/40 px-3 py-1 text-[12.5px] text-black hover:bg-black hover:text-white disabled:cursor-not-allowed disabled:opacity-40 dark:border-white/40 dark:text-white dark:hover:bg-white dark:hover:text-black"
				>
					Subscribe
				</button>
				<span class="ml-2 text-black/55 dark:text-white/55">replay:</span>
				<div class="flex rounded-full border border-black/10 p-0.5 dark:border-white/15">
					{#each SPEED_OPTIONS as speed (speed)}
						<button
							type="button"
							onclick={() => (replaySpeed = speed)}
							class="rounded-full px-2 py-0.5 text-[11.5px] {replaySpeed === speed
								? 'bg-black text-white dark:bg-white dark:text-black'
								: 'text-black/55 hover:text-black dark:text-white/55 dark:hover:text-white'}"
						>
							{speed}×
						</button>
					{/each}
				</div>
				{#if liveStatus === 'live'}
					<span class="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] text-emerald-700 dark:text-emerald-400">
						● live · {liveSid} · {fmtSeconds(elapsed)}
					</span>
					<button
						type="button"
						onclick={() => {
							disconnectLive();
							liveStatus = 'idle';
							if (elapsedTimer) clearInterval(elapsedTimer);
							elapsedTimer = null;
						}}
						class="text-[12px] text-black/55 underline hover:text-black dark:text-white/55 dark:hover:text-white"
					>
						stop
					</button>
				{:else if liveStatus === 'subscribing'}
					<span class="text-[11px] text-black/45 dark:text-white/45">subscribing…</span>
				{:else if liveStatus === 'error'}
					<span class="text-[11px] text-red-600 dark:text-red-400">{liveError}</span>
				{/if}
			</div>
		</header>

		<!-- Active design -->
		<div class="rounded-2xl border border-black/8 bg-white/40 p-5 dark:border-white/10 dark:bg-white/[0.02]">
			{#if frames.length === 0}
				<p class="text-[14px] text-black/45 italic dark:text-white/45">
					Press “Play simulated run” to see the {design === 'stream'
						? 'thought stream'
						: design === 'rail'
							? 'stream + activity rail'
							: 'step blocks'} fill in over ~15 seconds.
				</p>
			{:else if design === 'stream'}
				<!-- Approach 1: continuous prose; tool actions as muted footnote-style asides. -->
				<div class="flex items-baseline justify-between gap-2">
					<div class="flex items-baseline gap-1.5 text-[13px] text-black/55 dark:text-white/55">
						<span>{label}</span>
						{#if running || liveStatus === 'live'}
							<span class="label-typing-dots" aria-hidden="true"></span>
						{/if}
					</div>
					{#if running || frames.length}
						<span class="text-[12px] text-black/45 dark:text-white/45">{fmtSeconds(elapsed)}</span>
					{/if}
				</div>

				<div class="prose-stream mt-3 flex flex-col gap-3 text-[14.5px] leading-relaxed text-black/75 dark:text-white/75">
					{#each blocks as b, i (i)}
						{#if b.kind === 'thought'}
							<div in:fade={{ duration: 220 }} class="thought-block">
								<TypewriterText text={b.markdown} charsPerFrame={3}>
									{#snippet children(revealed)}
										{@html render(revealed)}
									{/snippet}
								</TypewriterText>
							</div>
						{:else if b.kind === 'note'}
							<div
								in:fly={{ y: 4, duration: 220 }}
								class="text-[14px] text-black/82 dark:text-white/82"
							>
								{b.text}
							</div>
						{:else}
							<div
								in:fly={{ y: 4, duration: 200 }}
								class="text-[13px] text-black/45 italic dark:text-white/45"
							>
								→ {b.text}
							</div>
						{/if}
					{/each}
				</div>
			{:else if design === 'rail'}
				<!-- Approach 2: thought stream on the left, compact activity rail on the right -->
				<div class="flex items-baseline justify-between gap-2">
					<div class="flex items-baseline gap-1.5 text-[13px] text-black/55 dark:text-white/55">
						<span>{label}</span>
						{#if running || liveStatus === 'live'}
							<span class="label-typing-dots" aria-hidden="true"></span>
						{/if}
					</div>
					{#if running || frames.length}
						<span class="text-[12px] text-black/45 dark:text-white/45">{fmtSeconds(elapsed)}</span>
					{/if}
				</div>

				<div class="mt-3 grid gap-5 md:grid-cols-[1fr_220px]">
					<div class="flex flex-col gap-3">
						{#each blocks as b, i (i)}
							{#if b.kind === 'thought'}
								<div class="prose-thought text-[14.5px] leading-relaxed text-black/75 dark:text-white/75">
									{@html render(b.markdown)}
								</div>
							{/if}
						{/each}
					</div>

					<div class="flex flex-col gap-2 border-l border-black/8 pl-4 dark:border-white/10">
						<div class="text-[11px] font-medium tracking-wide text-black/45 uppercase dark:text-white/45">Activity</div>
						{#each tools as t, i (i)}
							<div class="flex items-start text-[13px] leading-snug">
								<span class="relative mt-[7px] flex h-[6px] w-[6px] shrink-0 items-center justify-center">
									<span class="h-[6px] w-[6px] rounded-full bg-emerald-500 dark:bg-emerald-400"></span>
								</span>
								<span class="ml-2 min-w-0 flex-1 break-words text-black/60 dark:text-white/60">{t.text}</span>
							</div>
						{/each}
					</div>
				</div>
			{:else}
				<!-- Approach 3: step blocks — bold thought lead becomes the step header, tools nest under -->
				<div class="flex items-baseline justify-between gap-2">
					<div class="flex items-baseline gap-1.5 text-[13px] text-black/55 dark:text-white/55">
						<span>{label}</span>
						{#if running || liveStatus === 'live'}
							<span class="label-typing-dots" aria-hidden="true"></span>
						{/if}
					</div>
					{#if running || frames.length}
						<span class="text-[12px] text-black/45 dark:text-white/45">{fmtSeconds(elapsed)}</span>
					{/if}
				</div>

				<div class="mt-4 flex flex-col gap-6">
					{#each steps as step, i (i)}
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
							{:else}
								<div class="text-[12px] text-black/40 italic dark:text-white/40">
									(model emitted thoughts without a bold lead — best-effort case)
								</div>
							{/if}
							{#each step.thoughts as t, j (j)}
								<div
									in:fade={{ duration: 220 }}
									class="thought-block prose-thought mt-1.5 text-[14px] leading-relaxed text-black/70 dark:text-white/70"
								>
									<TypewriterText text={t} charsPerFrame={3}>
										{#snippet children(revealed)}
											{@html render(revealed)}
										{/snippet}
									</TypewriterText>
								</div>
							{/each}
							{#if step.tools.length}
								<div class="mt-2.5 flex flex-col gap-1.5 border-l-2 border-emerald-500/35 pl-3 dark:border-emerald-400/30">
									{#each step.tools as t, j (j)}
										<div
											in:fly={{ y: 4, duration: 200 }}
											class="flex items-start text-[13px] leading-snug text-black/60 dark:text-white/60"
										>
											<span class="ml-0 break-words">{t.text}</span>
										</div>
									{/each}
								</div>
							{/if}
						</div>
					{/each}
				</div>
			{/if}
		</div>

		<footer class="flex flex-col gap-3 text-[12.5px] text-black/50 dark:text-white/50">
			<p>
				<strong>Stream content.</strong> Set
				<code>ThinkingConfig(include_thoughts=True)</code> on research-path
				<code>LlmAgent</code>s; in <code>FirestoreProgressPlugin.on_event_callback</code>,
				parts where <code>part.thought is True</code> are mapped to
				<code>kind: 'thought'</code> timeline rows. Best-effort — some turns produce no
				thought parts; the layout degrades gracefully (steps with empty bodies).
			</p>
			<p>
				<strong>Header label.</strong> Derived from real ADK signals: latest tool's family if a
				tool just fired, otherwise <code>event.author</code> mapped to a friendly name. No
				cycling word, no hardcoded vocabulary on the model side, no prompt parsing.
			</p>
			<p>
				<strong>Specialist thoughts surface fine.</strong> Specialists are dispatched via
				<code>AgentTool</code> with <code>include_plugins=True</code> (<code>agent.py:154</code>),
				which makes the parent's <code>FirestoreProgressPlugin</code> run inside child runners.
				The 2026-05-04 probe confirmed thoughts arrive on the parent stream from
				<code>review_analyst</code>, <code>guest_intelligence</code>, and
				<code>market_landscape</code> alongside <code>context_enricher</code> and
				<code>research_lead</code>. No <code>sub_agents</code>/<code>transfer_to_agent</code>
				migration needed.
			</p>
			<p>
				<strong>Preview vs v1 production.</strong> This page renders an exploratory header
				(<em>Looking up venue data…</em> with typing dots, elapsed timer in the right corner).
				<strong>Production v1</strong> (per
				<code>docs/agent-thought-stream-production-plan-2026-05-04.md</code>) ships the
				existing <code>LiveActivity.svelte</code> header — <em>“Working for Xs”</em> plus
				<code>ProgressWrapper</code>'s bouncing dots — and the Step-blocks rendering only.
				The richer header is a §5 OPEN item; layer it in only if it tests better.
			</p>
		</footer>
	</div>
</div>

<style>
	/* Header typing-dots: cycles content '.', '..', '...', '..', '.', ''
	   so the dots type forward and back. Width is fixed at 1.2ch so the
	   surrounding text doesn't shift when the count changes. */
	.label-typing-dots::after {
		content: '';
		display: inline-block;
		width: 1.2ch;
		text-align: left;
		animation: label-dots-cycle 1.6s steps(1, end) infinite;
	}
	@keyframes label-dots-cycle {
		0%,
		100% {
			content: '';
		}
		16% {
			content: '.';
		}
		32% {
			content: '..';
		}
		48% {
			content: '...';
		}
		64% {
			content: '..';
		}
		80% {
			content: '.';
		}
	}

	.prose-thought :global(p) {
		margin: 0 0 0.4rem 0;
	}
	.prose-thought :global(p:last-child) {
		margin-bottom: 0;
	}
	.prose-thought :global(strong) {
		font-weight: 600;
	}
	.thought-block :global(p) {
		margin: 0 0 0.5rem 0;
	}
	.thought-block :global(p:last-child) {
		margin-bottom: 0;
	}
	.thought-block :global(strong) {
		font-weight: 600;
		color: rgb(0 0 0 / 0.85);
	}
	:global(.dark) .thought-block :global(strong) {
		color: rgb(255 255 255 / 0.85);
	}
</style>
