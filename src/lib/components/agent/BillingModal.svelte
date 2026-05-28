<script lang="ts">
	import { billing } from '$lib/billing-state.svelte';
	import { lockPageScroll } from '$lib/scroll-lock';

	$effect(() => {
		if (!billing.modalVisible) return;
		return lockPageScroll();
	});
</script>

{#if billing.modalVisible}
	<div
		class="fixed inset-0 z-[80] flex items-center justify-center bg-black/25 px-4 py-8 backdrop-blur-sm dark:bg-black/45"
		role="presentation"
		onclick={(e) => {
			if (e.target === e.currentTarget) billing.closeUpgrade();
		}}
	>
		<div
			class="w-full max-w-md rounded-lg border border-black/[0.08] bg-white shadow-2xl dark:border-white/[0.1] dark:bg-cream-50"
			role="dialog"
			aria-modal="true"
			aria-labelledby="billing-title"
		>
			<div class="border-b border-black/[0.06] px-5 py-4 dark:border-white/[0.08]">
				<div class="flex items-start justify-between gap-4">
					<div>
						<h2 id="billing-title" class="text-[16px] font-medium text-black dark:text-white">
							Superextra Unlimited
						</h2>
						<p class="mt-1 text-[13px] leading-snug text-black/50 dark:text-white/50">
							{billing.mode === 'test'
								? 'Stripe test mode. No real payment is collected.'
								: 'Billing country sets currency. Tax is included where applicable.'}
						</p>
					</div>
					<button
						type="button"
						aria-label="Close"
						onclick={() => billing.closeUpgrade()}
						class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-black/40 transition-colors hover:bg-black/[0.05] hover:text-black/70 dark:text-white/40 dark:hover:bg-white/[0.06] dark:hover:text-white/70"
					>
						<svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor">
							<path stroke-linecap="round" stroke-width="1.8" d="M6 6l12 12M18 6L6 18" />
						</svg>
					</button>
				</div>
			</div>

			<div class="px-5 py-4">
				<label for="billing-market" class="block text-[13px] text-black/55 dark:text-white/55">
					Billing country
				</label>
				<div class="relative mt-2">
					<select
						id="billing-market"
						bind:value={billing.selectedMarket}
						class="w-full appearance-none rounded-lg border border-black/[0.1] bg-white px-3 py-3 pr-10 text-[14px] text-black outline-none transition-colors focus:border-black/40 dark:border-white/[0.12] dark:bg-cream-100 dark:text-white dark:focus:border-white/40"
					>
						{#each billing.marketOptions as market (market.id)}
							<option value={market.id}>{market.label}</option>
						{/each}
					</select>
					<svg
						class="pointer-events-none absolute top-1/2 right-3 h-4 w-4 -translate-y-1/2 text-black/45 dark:text-white/45"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						aria-hidden="true"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							stroke-width="1.8"
							d="m6 9 6 6 6-6"
						/>
					</svg>
				</div>
				<p class="mt-2 text-[12px] leading-snug text-black/45 dark:text-white/45">
					Used for currency and tax handling in Stripe Checkout.
				</p>

				{#if billing.error}
					<p class="mt-3 text-[13px] text-red-600 dark:text-red-400" role="alert">
						{billing.error}
					</p>
				{/if}
				{#if billing.mode === 'test'}
					<p class="mt-3 text-[12px] text-black/45 dark:text-white/45">
						Test card: 4242 4242 4242 4242
					</p>
				{/if}
			</div>

			<div
				class="flex items-center justify-end gap-2 border-t border-black/[0.06] px-5 py-4 dark:border-white/[0.08]"
			>
				<button
					type="button"
					onclick={() => billing.closeUpgrade()}
					disabled={billing.posting}
					class="rounded-full px-4 py-2 text-[13px] text-black/55 transition-colors hover:bg-cream-100 hover:text-black disabled:opacity-50 dark:text-white/55 dark:hover:bg-cream-100 dark:hover:text-white"
				>
					Cancel
				</button>
				<button
					type="button"
					onclick={() => billing.startCheckout(billing.selectedMarket)}
					disabled={billing.posting}
					class="rounded-full bg-black px-4 py-2 text-[13px] font-medium text-white transition-colors hover:bg-black/80 disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-white/80"
				>
					{billing.posting ? 'Opening…' : 'Continue'}
				</button>
			</div>
		</div>
	</div>
{/if}
