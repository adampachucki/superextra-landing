<script lang="ts">
	import { feedback } from '$lib/feedback.svelte';
	import ReasonPicker from './ReasonPicker.svelte';

	let { sid, turnIndex }: { sid: string | null; turnIndex: number } = $props();

	let stage = $state<'ask' | 'reasons' | 'done'>('ask');
	let reasons = $state<string[]>([]);
	let note = $state('');

	function finish() {
		stage = 'done';
		setTimeout(() => feedback.closeSurvey(sid, turnIndex), 2200);
	}

	function yes() {
		feedback.recordSurvey(sid, turnIndex, 'yes');
		finish();
	}

	function no() {
		stage = 'reasons';
	}

	function send() {
		feedback.recordSurvey(sid, turnIndex, 'no', reasons, note.trim() || undefined);
		finish();
	}

	function skip() {
		feedback.recordSurvey(sid, turnIndex, 'no');
		finish();
	}

	const pill =
		'rounded-full border border-black/10 px-4 py-1.5 text-[13px] text-black/70 transition-colors hover:border-black/20 hover:bg-black/[0.03] dark:border-white/10 dark:text-white/70 dark:hover:border-white/20 dark:hover:bg-white/[0.04]';
</script>

<div class="mt-8 max-w-[700px]">
	<div
		class="rounded-2xl border border-black/[0.08] bg-black/[0.02] px-4 py-3 dark:border-white/[0.1] dark:bg-white/[0.03]"
	>
		{#if stage === 'done'}
			<p class="text-[13px] text-black/55 dark:text-white/55">Thanks — noted.</p>
		{:else}
			<div class="flex items-center justify-between gap-3">
				<p class="text-[14px] text-black/70 dark:text-white/70">Do you find this report useful?</p>
				<button
					type="button"
					onclick={() => feedback.closeSurvey(sid, turnIndex)}
					aria-label="Dismiss"
					class="-mr-1 btn-icon h-6 w-6 text-[16px] leading-none"
				>
					×
				</button>
			</div>
			{#if stage === 'ask'}
				<div class="mt-3 flex gap-2">
					<button type="button" onclick={yes} class={pill}>Yes</button>
					<button type="button" onclick={no} class={pill}>No</button>
				</div>
			{:else}
				<div class="mt-3">
					<ReasonPicker
						prompt="What was missing?"
						bind:reasons
						bind:note
						onSend={send}
						onSkip={skip}
					/>
				</div>
			{/if}
		{/if}
	</div>
</div>
