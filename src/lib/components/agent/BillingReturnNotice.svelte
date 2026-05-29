<script lang="ts">
	import { onMount } from 'svelte';
	import { billing } from '$lib/billing-state.svelte';

	type NoticeState = 'confirming' | 'active' | 'pending';

	let visible = $state(false);
	let noticeState = $state<NoticeState>('confirming');
	let hideTimer: ReturnType<typeof setTimeout> | null = null;

	function removeBillingParams(url: URL) {
		url.searchParams.delete('billing');
		url.searchParams.delete('session_id');
		history.replaceState(history.state, '', `${url.pathname}${url.search}${url.hash}`);
	}

	function scheduleHide(delay = 7000) {
		if (hideTimer) clearTimeout(hideTimer);
		hideTimer = setTimeout(() => {
			visible = false;
		}, delay);
	}

	onMount(() => {
		const url = new URL(window.location.href);
		const result = url.searchParams.get('billing');
		if (result === 'cancelled') {
			removeBillingParams(url);
			return;
		}
		if (result !== 'success') return;

		const sessionId = url.searchParams.get('session_id');
		removeBillingParams(url);
		visible = true;
		noticeState = sessionId ? 'confirming' : 'pending';
		if (!sessionId) {
			scheduleHide();
			return () => {
				if (hideTimer) clearTimeout(hideTimer);
			};
		}

		void billing
			.confirmCheckout(sessionId)
			.then(() => {
				noticeState = 'active';
				scheduleHide();
			})
			.catch((err) => {
				console.warn('[billing] checkout confirmation failed', err);
				noticeState = 'pending';
				scheduleHide(9000);
			});

		return () => {
			if (hideTimer) clearTimeout(hideTimer);
		};
	});
</script>

{#if visible}
	<div
		class="pointer-events-none fixed top-[max(1rem,env(safe-area-inset-top))] right-0 left-0 z-[90] flex justify-center px-4"
		aria-live="polite"
	>
		<div
			class="billing-notice pointer-events-auto w-full max-w-sm rounded-lg border border-black/[0.08] bg-white px-4 py-3 shadow-2xl dark:border-white/[0.1] dark:bg-cream-50"
		>
			<div class="flex items-start gap-3">
				<div
					class="relative mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-white"
				>
					<svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="2"
							d="m5 12 4 4L19 6"
						/>
					</svg>
					<span class="billing-pulse absolute inset-0 rounded-full border border-emerald-400"></span>
				</div>
				<div class="min-w-0 flex-1">
					<p class="text-[14px] font-medium text-black dark:text-white">
						{noticeState === 'active' ? 'Welcome to Superextra Pro' : 'Activating Pro'}
					</p>
					<p class="mt-0.5 text-[12px] leading-snug text-black/50 dark:text-white/50">
						{noticeState === 'active'
							? 'Superextra Pro is active on this account.'
							: noticeState === 'confirming'
								? 'Confirming the subscription with Stripe.'
								: 'Subscription state will update in a moment.'}
					</p>
				</div>
				<button
					type="button"
					aria-label="Dismiss"
					onclick={() => (visible = false)}
					class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-black/35 transition-colors hover:bg-black/[0.05] hover:text-black/65 dark:text-white/35 dark:hover:bg-white/[0.06] dark:hover:text-white/65"
				>
					<svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor">
						<path stroke-linecap="round" stroke-width="1.8" d="M6 6l12 12M18 6L6 18" />
					</svg>
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.billing-notice {
		animation: billingNoticeIn 0.38s cubic-bezier(0.16, 1, 0.3, 1);
	}

	.billing-pulse {
		animation: billingPulse 1.6s ease-out infinite;
	}

	@keyframes billingNoticeIn {
		from {
			opacity: 0;
			transform: translateY(-10px) scale(0.98);
		}
		to {
			opacity: 1;
			transform: translateY(0) scale(1);
		}
	}

	@keyframes billingPulse {
		from {
			opacity: 0.7;
			transform: scale(1);
		}
		to {
			opacity: 0;
			transform: scale(1.7);
		}
	}
</style>
