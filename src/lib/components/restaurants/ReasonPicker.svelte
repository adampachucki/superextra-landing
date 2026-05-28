<script lang="ts">
	import { DOWNVOTE_REASONS } from '$lib/feedback.svelte';

	let {
		prompt,
		reasons = $bindable([]),
		note = $bindable(''),
		onSend,
		onSkip
	}: {
		prompt: string;
		reasons?: string[];
		note?: string;
		onSend: () => void;
		onSkip: () => void;
	} = $props();

	function toggle(reason: string) {
		reasons = reasons.includes(reason) ? reasons.filter((r) => r !== reason) : [...reasons, reason];
	}
</script>

<p class="mb-2 text-[12px] font-medium text-black/55 dark:text-white/55">{prompt}</p>
<div class="flex flex-wrap gap-1.5">
	{#each DOWNVOTE_REASONS as reason (reason)}
		<button
			type="button"
			onclick={() => toggle(reason)}
			class="rounded-full border px-2.5 py-1 text-[12px] transition-colors {reasons.includes(reason)
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
		onclick={onSkip}
		class="rounded-full px-2.5 py-1 text-[12px] text-black/45 transition-colors hover:text-black/70 dark:text-white/45 dark:hover:text-white/70"
	>
		Skip
	</button>
	<button
		type="button"
		onclick={onSend}
		class="rounded-full border border-black/15 bg-black/[0.04] px-3 py-1 text-[12px] text-black/80 transition-colors hover:bg-black/[0.07] dark:border-white/15 dark:bg-white/[0.04] dark:text-white/80 dark:hover:bg-white/[0.07]"
	>
		Send
	</button>
</div>
