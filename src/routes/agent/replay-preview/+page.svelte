<script lang="ts">
	import { onDestroy, onMount, tick as svelteTick } from 'svelte';
	import { page } from '$app/state';
	import { splitChartSegments } from '$lib/chart-blocks';
	import type { ChatSource, TimelineEvent, TurnSummary } from '$lib/chat-types';
	import LiveActivity from '$lib/components/agent/LiveActivity.svelte';
	import ChartBlock from '$lib/components/restaurants/ChartBlock.svelte';
	import { ensureAnonAuth, getFirebase } from '$lib/firebase';
	import { renderMarkdown } from '$lib/markdown';
	import { formatDuration } from '$lib/time';

	const DEFAULT_SID = 'd2028234-c706-4198-8728-7dae47e780d5';

	type ReplayStatus = 'idle' | 'loading' | 'ready' | 'playing' | 'done' | 'error';
	type ReplayTurn = {
		turnIndex: number;
		runId: string;
		userMessage: string;
		reply: string;
		sources: ChatSource[];
		turnSummary: TurnSummary | null;
		createdAtMs: number | null;
		completedAtMs: number | null;
	};
	type ReplayEvent = {
		key: string;
		offsetMs: number;
		event: TimelineEvent;
	};

	let sid = $state(DEFAULT_SID);
	let loadedSid = $state('');
	let status = $state<ReplayStatus>('idle');
	let error = $state('');
	let speed = $state(8);
	let turn = $state<ReplayTurn | null>(null);
	let replayEvents = $state<ReplayEvent[]>([]);
	let visibleEvents = $state<TimelineEvent[]>([]);
	let currentElapsedMs = $state(0);
	let bottomEl: HTMLDivElement | undefined = $state();

	let raf: number | null = null;
	let replayStartedAt = 0;
	let pausedElapsedMs = 0;

	function toMillis(value: unknown): number | null {
		if (typeof value === 'number' && Number.isFinite(value)) return value;
		if (
			typeof value === 'object' &&
			value !== null &&
			'toMillis' in value &&
			typeof (value as { toMillis?: unknown }).toMillis === 'function'
		) {
			try {
				return (value as { toMillis: () => number }).toMillis();
			} catch {
				return null;
			}
		}
		return null;
	}

	const allTimelineEvents = $derived(replayEvents.map((item) => item.event));
	const scrollKey = $derived(
		visibleEvents.map((event) => `${event.id}:${'text' in event ? event.text.length : ''}`).join('|')
	);
	const totalMs = $derived.by(() => {
		if (turn?.turnSummary?.elapsedMs) return turn.turnSummary.elapsedMs;
		if (turn?.completedAtMs && turn.createdAtMs) return Math.max(0, turn.completedAtMs - turn.createdAtMs);
		return Math.max(0, ...replayEvents.map((item) => item.offsetMs)) + 2000;
	});
	const progress = $derived(totalMs > 0 ? Math.min(100, (currentElapsedMs / totalMs) * 100) : 0);

	function stopReplay() {
		if (raf !== null) cancelAnimationFrame(raf);
		raf = null;
	}

	function setElapsed(elapsedMs: number) {
		const elapsed = Math.max(0, Math.min(totalMs, elapsedMs));
		currentElapsedMs = elapsed;
		visibleEvents =
			elapsed >= totalMs
				? allTimelineEvents
				: replayEvents.filter((item) => item.offsetMs <= elapsed).map((item) => item.event);
		if (elapsed >= totalMs && totalMs > 0) {
			stopReplay();
			pausedElapsedMs = totalMs;
			status = 'done';
		} else if (status === 'done') {
			status = 'ready';
		}
	}

	function resetReplay() {
		stopReplay();
		currentElapsedMs = 0;
		pausedElapsedMs = 0;
		visibleEvents = [];
		status = turn ? 'ready' : 'idle';
	}

	function tick(now = performance.now()) {
		const elapsed = Math.min(totalMs, pausedElapsedMs + (now - replayStartedAt) * speed);
		setElapsed(elapsed);
		if (currentElapsedMs >= totalMs) {
			return;
		}
		raf = requestAnimationFrame(tick);
	}

	function startReplay() {
		if (!turn) return;
		stopReplay();
		status = 'playing';
		currentElapsedMs = 0;
		pausedElapsedMs = 0;
		visibleEvents = [];
		replayStartedAt = performance.now();
		raf = requestAnimationFrame(tick);
	}

	function seekReplay(elapsedMs: number) {
		if (!turn || status === 'loading') return;
		const wasPlaying = status === 'playing';
		stopReplay();
		setElapsed(elapsedMs);
		pausedElapsedMs = currentElapsedMs;
		if (currentElapsedMs >= totalMs) return;
		if (wasPlaying) {
			status = 'playing';
			replayStartedAt = performance.now();
			raf = requestAnimationFrame(tick);
		} else if (status !== 'error') {
			status = 'ready';
		}
	}

	function pauseReplay() {
		if (status !== 'playing') return;
		stopReplay();
		pausedElapsedMs = currentElapsedMs;
		status = 'ready';
	}

	function resumeReplay() {
		if (!turn || currentElapsedMs >= totalMs) return;
		stopReplay();
		pausedElapsedMs = currentElapsedMs;
		status = 'playing';
		replayStartedAt = performance.now();
		raf = requestAnimationFrame(tick);
	}

	$effect(() => {
		if (status !== 'playing' && status !== 'done') return;
		scrollKey;
		svelteTick().then(() => {
			requestAnimationFrame(() => {
				bottomEl?.scrollIntoView({ block: 'end', behavior: 'smooth' });
			});
		});
	});

	async function loadReplay({ autoplay = false } = {}) {
		const requestedSid = sid.trim();
		if (!requestedSid) return;
		stopReplay();
		status = 'loading';
		error = '';
		turn = null;
		replayEvents = [];
		visibleEvents = [];
		currentElapsedMs = 0;
		pausedElapsedMs = 0;

		try {
			await ensureAnonAuth();
			const { db } = await getFirebase();
			const firestore = await import('firebase/firestore');
			const turnsSnap = await firestore.getDocs(
				firestore.query(
					firestore.collection(db, 'sessions', requestedSid, 'turns'),
					firestore.orderBy('turnIndex')
				)
			);
			const turns: ReplayTurn[] = [];
			turnsSnap.forEach((docSnap) => {
				const data = docSnap.data() as Record<string, unknown>;
				const sources = data.sources;
				turns.push({
					turnIndex: (data.turnIndex as number | undefined) ?? Number(docSnap.id),
					runId: (data.runId as string | undefined) ?? '',
					userMessage: (data.userMessage as string | undefined) ?? '',
					reply: (data.reply as string | undefined) ?? '',
					sources: Array.isArray(sources) ? (sources as ChatSource[]) : [],
					turnSummary: (data.turnSummary as TurnSummary | null | undefined) ?? null,
					createdAtMs: toMillis(data.createdAt),
					completedAtMs: toMillis(data.completedAt)
				});
			});

			const selectedTurn = [...turns].reverse().find((item) => item.reply) ?? turns.at(-1);
			if (!selectedTurn) throw new Error('No turn documents found for this session.');
			if (!selectedTurn.runId) throw new Error('The selected turn has no runId.');

			const eventsSnap = await firestore.getDocs(
				firestore.query(
					firestore.collection(db, 'sessions', requestedSid, 'events'),
					firestore.where('runId', '==', selectedTurn.runId),
					firestore.orderBy('attempt'),
					firestore.orderBy('seqInAttempt')
				)
			);

			const rawEvents: Array<{
				key: string;
				attempt: number;
				seq: number;
				tsMs: number | null;
				event: TimelineEvent;
			}> = [];
			eventsSnap.forEach((docSnap) => {
				const data = docSnap.data() as Record<string, unknown>;
				if (data.type !== 'timeline') return;
				rawEvents.push({
					key: docSnap.id,
					attempt: (data.attempt as number | undefined) ?? 0,
					seq: (data.seqInAttempt as number | undefined) ?? 0,
					tsMs: toMillis(data.ts),
					event: (data.data ?? {}) as TimelineEvent
				});
			});

			const firstEventAt = rawEvents.find((item) => item.tsMs !== null)?.tsMs ?? null;
			const baseMs = selectedTurn.createdAtMs ?? firstEventAt;
			const mapped = rawEvents
				.map((item, index) => ({
					key: item.key,
					offsetMs: baseMs !== null && item.tsMs !== null ? Math.max(0, item.tsMs - baseMs) : index * 700,
					event: item.event
				}))
				.sort((a, b) => a.offsetMs - b.offsetMs);

			turn = selectedTurn;
			replayEvents = mapped;
			loadedSid = requestedSid;
			status = 'ready';
			if (autoplay) startReplay();
		} catch (err) {
			status = 'error';
			error = err instanceof Error ? err.message : String(err);
		}
	}

	onMount(() => {
		sid = page.url.searchParams.get('sid') ?? DEFAULT_SID;
		void loadReplay({ autoplay: true });
	});

	onDestroy(stopReplay);
</script>

<svelte:head>
	<title>Session Replay Preview | Superextra</title>
</svelte:head>

<main class="min-h-screen bg-cream px-5 py-6 text-black dark:bg-black dark:text-white md:px-6">
	<div class="mx-auto flex max-w-[900px] flex-col gap-5">
		<section
			class="sticky top-3 z-30 rounded-2xl border border-black/8 bg-white/85 p-4 shadow-sm backdrop-blur-md dark:border-white/10 dark:bg-black/80"
		>
			<div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
				<div class="flex min-w-0 flex-1 items-center gap-2">
					<input
						bind:value={sid}
						aria-label="Session ID"
						class="min-w-0 flex-1 rounded-xl border border-black/8 bg-white px-3 py-2 text-[13px] text-black outline-none focus:border-black/25 dark:border-white/10 dark:bg-white/[0.04] dark:text-white dark:focus:border-white/25"
					/>
					<button
						type="button"
						onclick={() => loadReplay()}
						disabled={status === 'loading'}
						class="rounded-xl border border-black/10 px-3 py-2 text-[13px] text-black/65 transition-colors hover:bg-black/[0.04] disabled:opacity-40 dark:border-white/10 dark:text-white/65 dark:hover:bg-white/[0.06]"
					>
						Load
					</button>
				</div>
				<div class="flex items-center gap-2">
					<select
						bind:value={speed}
						aria-label="Replay speed"
						class="rounded-xl border border-black/8 bg-white px-2 py-2 text-[13px] text-black outline-none dark:border-white/10 dark:bg-white/[0.04] dark:text-white"
					>
						<option value={1}>1x</option>
						<option value={4}>4x</option>
						<option value={8}>8x</option>
						<option value={16}>16x</option>
					</select>
					<button
						type="button"
						onclick={() => {
							if (status === 'playing') {
								pauseReplay();
							} else if (currentElapsedMs > 0 && currentElapsedMs < totalMs) {
								resumeReplay();
							} else {
								startReplay();
							}
						}}
						disabled={!turn || status === 'loading'}
						class="rounded-xl bg-black px-3 py-2 text-[13px] text-white transition-colors hover:bg-black/80 disabled:opacity-30 dark:bg-white dark:text-black dark:hover:bg-white/80"
					>
						{status === 'playing'
							? 'Pause'
							: currentElapsedMs > 0 && currentElapsedMs < totalMs
								? 'Resume'
								: 'Replay'}
					</button>
					<button
						type="button"
						onclick={resetReplay}
						disabled={!turn || status === 'loading'}
						class="rounded-xl border border-black/10 px-3 py-2 text-[13px] text-black/65 transition-colors hover:bg-black/[0.04] disabled:opacity-40 dark:border-white/10 dark:text-white/65 dark:hover:bg-white/[0.06]"
					>
						Reset
					</button>
				</div>
			</div>
			<input
				type="range"
				min="0"
				max={Math.max(1, totalMs)}
				step="100"
				value={currentElapsedMs}
				disabled={!turn || status === 'loading'}
				aria-label="Replay timeline"
				oninput={(event) => seekReplay(event.currentTarget.valueAsNumber)}
				class="timeline-range mt-3 block w-full"
				style="--progress: {progress}%"
			/>
			<div class="mt-2 flex items-center justify-between text-[12px] text-black/40 dark:text-white/40">
				<span>{status}{loadedSid ? ` · ${loadedSid}` : ''}</span>
				<span>{formatDuration(currentElapsedMs)} / {formatDuration(totalMs)}</span>
			</div>
			{#if error}
				<p class="mt-3 text-[13px] text-red-600 dark:text-red-400">{error}</p>
			{/if}
		</section>

		<section class="mx-auto flex w-full max-w-[700px] flex-col gap-5">
			{#if turn}
				<div class="flex justify-end">
					<div
						class="max-w-[85%] rounded-2xl rounded-br-md bg-cream-100 px-4 py-3 text-[15px] leading-relaxed text-black dark:text-white"
					>
						{turn.userMessage}
					</div>
				</div>

				{#if status === 'done'}
					<div class="flex justify-start">
						<div class="max-w-[95%] px-1 py-1">
							<div
								class="prose max-w-none text-[15px] leading-relaxed text-black/80 dark:text-white/80 prose-headings:text-black dark:prose-headings:text-white prose-a:text-black prose-a:underline dark:prose-a:text-white prose-strong:text-black dark:prose-strong:text-white"
							>
								{#each splitChartSegments(turn.reply) as seg, segIdx (segIdx)}
									{#if seg.kind === 'chart'}
										<ChartBlock spec={seg.spec} />
									{:else}
										<!-- eslint-disable-next-line svelte/no-at-html-tags -->
										{@html renderMarkdown(seg.text)}
									{/if}
								{/each}
							</div>
							<div class="mt-4">
								<LiveActivity events={allTimelineEvents} elapsedMs={totalMs} completed />
							</div>
							{#if turn.sources.length}
								<div class="mt-5 text-[12px] text-black/40 dark:text-white/40">
									Sources ({turn.sources.length})
								</div>
							{/if}
						</div>
					</div>
				{:else}
					<div class="flex justify-start">
						<div class="max-w-[95%] px-1 py-1">
							<LiveActivity events={visibleEvents} elapsedMs={currentElapsedMs} />
						</div>
					</div>
				{/if}
			{:else if status === 'loading'}
				<div class="text-[13px] text-black/45 dark:text-white/45">Loading session…</div>
			{/if}
			<div bind:this={bottomEl} aria-hidden="true"></div>
		</section>
	</div>
</main>

<style>
	.timeline-range {
		height: 1.25rem;
		cursor: pointer;
		appearance: none;
		background: transparent;
	}
	.timeline-range:disabled {
		cursor: not-allowed;
		opacity: 0.45;
	}
	.timeline-range::-webkit-slider-runnable-track {
		height: 0.25rem;
		border-radius: 999px;
		background: linear-gradient(
			to right,
			rgba(0, 0, 0, 0.36) 0,
			rgba(0, 0, 0, 0.36) var(--progress),
			rgba(0, 0, 0, 0.06) var(--progress),
			rgba(0, 0, 0, 0.06) 100%
		);
	}
	.timeline-range::-webkit-slider-thumb {
		width: 0.85rem;
		height: 0.85rem;
		margin-top: -0.3rem;
		appearance: none;
		border-radius: 999px;
		background: currentColor;
		box-shadow: 0 0 0 4px rgba(0, 0, 0, 0.08);
	}
	.timeline-range::-moz-range-track {
		height: 0.25rem;
		border-radius: 999px;
		background: rgba(0, 0, 0, 0.06);
	}
	.timeline-range::-moz-range-progress {
		height: 0.25rem;
		border-radius: 999px;
		background: rgba(0, 0, 0, 0.36);
	}
	.timeline-range::-moz-range-thumb {
		width: 0.85rem;
		height: 0.85rem;
		border: 0;
		border-radius: 999px;
		background: currentColor;
		box-shadow: 0 0 0 4px rgba(0, 0, 0, 0.08);
	}
	:global(.dark) .timeline-range::-webkit-slider-runnable-track {
		background: linear-gradient(
			to right,
			rgba(255, 255, 255, 0.42) 0,
			rgba(255, 255, 255, 0.42) var(--progress),
			rgba(255, 255, 255, 0.1) var(--progress),
			rgba(255, 255, 255, 0.1) 100%
		);
	}
	:global(.dark) .timeline-range::-webkit-slider-thumb {
		box-shadow: 0 0 0 4px rgba(255, 255, 255, 0.12);
	}
	:global(.dark) .timeline-range::-moz-range-track {
		background: rgba(255, 255, 255, 0.1);
	}
	:global(.dark) .timeline-range::-moz-range-progress {
		background: rgba(255, 255, 255, 0.42);
	}
	:global(.dark) .timeline-range::-moz-range-thumb {
		box-shadow: 0 0 0 4px rgba(255, 255, 255, 0.12);
	}
</style>
