<script lang="ts">
	import { feedback } from '$lib/feedback.svelte';

	let { sid, turnIndex }: { sid: string | null; turnIndex: number } = $props();

	let done = $state(false);

	function answer(helped: 'yes' | 'not_yet') {
		feedback.recordSurvey(sid, turnIndex, helped);
		done = true;
		setTimeout(() => feedback.closeSurvey(sid, turnIndex), 2200);
	}

	const pill =
		'rounded-full border border-black/10 px-4 py-1.5 text-[13px] text-black/70 transition-colors hover:border-black/20 hover:bg-black/[0.03] dark:border-white/10 dark:text-white/70 dark:hover:border-white/20 dark:hover:bg-white/[0.04]';
</script>

<div class="mt-5 max-w-[700px]">
	<div
		class="rounded-2xl border border-black/[0.08] bg-black/[0.02] px-4 py-3 dark:border-white/[0.1] dark:bg-white/[0.03]"
	>
		{#if done}
			<p class="text-[13px] text-black/55 dark:text-white/55">Thanks — noted.</p>
		{:else}
			<div class="flex items-center justify-between gap-3">
				<p class="text-[14px] text-black/70 dark:text-white/70">Did this help you decide?</p>
				<button
					type="button"
					onclick={() => feedback.closeSurvey(sid, turnIndex)}
					aria-label="Dismiss"
					class="-mr-1 inline-flex h-6 w-6 items-center justify-center rounded-full text-[16px] leading-none text-black/35 transition-colors hover:bg-black/[0.04] hover:text-black/60 dark:text-white/35 dark:hover:bg-white/[0.05] dark:hover:text-white/60"
				>
					×
				</button>
			</div>
			<div class="mt-3 flex gap-2">
				<button type="button" onclick={() => answer('yes')} class={pill}>Yes</button>
				<button type="button" onclick={() => answer('not_yet')} class={pill}>Not yet</button>
			</div>
		{/if}
	</div>
</div>
