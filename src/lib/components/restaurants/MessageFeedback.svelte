<script lang="ts">
	import { feedback, DOWNVOTE_REASONS } from '$lib/feedback.svelte';
	import type { TurnFeedback } from '$lib/chat-types';

	let { sid, turnIndex, entry }: { sid: string | null; turnIndex: number; entry?: TurnFeedback } =
		$props();

	const selected = $derived(feedback.ratingFor(sid, turnIndex, entry?.rating));
	const reasonsOpen = $derived(feedback.isReasonsOpen(sid, turnIndex));

	let reasons = $state<string[]>([]);
	let note = $state('');

	function thumbUp() {
		feedback.closeReasons();
		feedback.rate(sid, turnIndex, 'up');
	}

	function thumbDown() {
		if (selected === 'down') {
			feedback.toggleReasons(sid, turnIndex);
			return;
		}
		feedback.rate(sid, turnIndex, 'down');
		feedback.openReasons(sid, turnIndex);
	}

	function toggleReason(reason: string) {
		reasons = reasons.includes(reason) ? reasons.filter((r) => r !== reason) : [...reasons, reason];
	}

	function send() {
		feedback.rate(sid, turnIndex, 'down', reasons, note.trim() || undefined);
		feedback.closeReasons();
	}

	const thumbBase =
		'inline-flex items-center justify-center rounded-full border p-1.5 transition-colors';
	const thumbIdle =
		'border-black/5 text-black/40 hover:border-black/10 hover:bg-black/[0.02] hover:text-black/60 dark:border-white/5 dark:text-white/40 dark:hover:border-white/10 dark:hover:bg-white/[0.02] dark:hover:text-white/60';
	const thumbActive =
		'border-black/15 bg-black/[0.04] text-black/80 dark:border-white/15 dark:bg-white/[0.04] dark:text-white/80';
</script>

<div class="relative inline-flex items-center gap-1">
	<button
		type="button"
		onclick={thumbUp}
		aria-label="Helpful"
		aria-pressed={selected === 'up'}
		class="{thumbBase} {selected === 'up' ? thumbActive : thumbIdle}"
	>
		<svg
			class="h-3.5 w-3.5"
			viewBox="0 0 24 24"
			fill={selected === 'up' ? 'currentColor' : 'none'}
			stroke="currentColor"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round"
		>
			<path d="M7 10v12" />
			<path
				d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"
			/>
		</svg>
	</button>

	<button
		type="button"
		onclick={thumbDown}
		aria-label="Not helpful"
		aria-pressed={selected === 'down'}
		class="{thumbBase} {selected === 'down' ? thumbActive : thumbIdle}"
	>
		<svg
			class="h-3.5 w-3.5"
			viewBox="0 0 24 24"
			fill={selected === 'down' ? 'currentColor' : 'none'}
			stroke="currentColor"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round"
		>
			<path d="M17 14V2" />
			<path
				d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z"
			/>
		</svg>
	</button>

	{#if reasonsOpen}
		<div
			class="absolute top-full right-0 z-10 mt-2 w-72 rounded-xl border border-cream-200 bg-cream-50 p-3 shadow-lg"
		>
			<p class="mb-2 text-[12px] font-medium text-black/55 dark:text-white/55">What was off?</p>
			<div class="flex flex-wrap gap-1.5">
				{#each DOWNVOTE_REASONS as reason (reason)}
					<button
						type="button"
						onclick={() => toggleReason(reason)}
						class="rounded-full border px-2.5 py-1 text-[12px] transition-colors {reasons.includes(
							reason
						)
							? 'border-black/20 bg-black/[0.05] text-black/80 dark:border-white/20 dark:bg-white/[0.06] dark:text-white/80'
							: 'border-black/5 text-black/50 hover:border-black/10 hover:bg-black/[0.02] dark:border-white/5 dark:text-white/50 dark:hover:border-white/10 dark:hover:bg-white/[0.02]'}"
					>
						{reason}
					</button>
				{/each}
			</div>
			<textarea
				bind:value={note}
				rows="2"
				placeholder="Tell us more (optional)"
				class="mt-2 w-full resize-none rounded-lg border border-black/10 bg-transparent px-2.5 py-1.5 text-[13px] text-black/80 placeholder:text-black/35 focus:border-black/25 focus:outline-none dark:border-white/10 dark:text-white/80 dark:placeholder:text-white/35 dark:focus:border-white/25"
			></textarea>
			<div class="mt-2 flex justify-end gap-2">
				<button
					type="button"
					onclick={() => feedback.closeReasons()}
					class="rounded-full px-2.5 py-1 text-[12px] text-black/45 transition-colors hover:text-black/70 dark:text-white/45 dark:hover:text-white/70"
				>
					Skip
				</button>
				<button
					type="button"
					onclick={send}
					class="rounded-full border border-black/15 bg-black/[0.04] px-3 py-1 text-[12px] text-black/80 transition-colors hover:bg-black/[0.07] dark:border-white/15 dark:bg-white/[0.04] dark:text-white/80 dark:hover:bg-white/[0.07]"
				>
					Send
				</button>
			</div>
		</div>
	{/if}
</div>
