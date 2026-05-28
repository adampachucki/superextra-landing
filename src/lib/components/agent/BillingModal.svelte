<script lang="ts">
	import { billing, billingMarkets } from '$lib/billing-state.svelte';
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
				<div class="grid gap-2">
					{#each billingMarkets as market (market.id)}
						<label
							class="flex cursor-pointer items-center justify-between rounded-lg border px-3 py-3 transition-colors {billing.selectedMarket ===
							market.id
								? 'border-black/25 bg-black/[0.04] dark:border-white/25 dark:bg-white/[0.08]'
								: 'border-black/[0.08] hover:bg-cream-100/60 dark:border-white/[0.08] dark:hover:bg-white/[0.04]'}"
						>
							<span class="flex items-center gap-3">
								<input
									type="radio"
									name="billing-market"
									value={market.id}
									checked={billing.selectedMarket === market.id}
									onchange={() => (billing.selectedMarket = market.id)}
									class="h-4 w-4 accent-black dark:accent-white"
								/>
								<span>
									<span class="block text-[14px] text-black dark:text-white">{market.label}</span>
									<span class="block text-[12px] text-black/45 dark:text-white/45"
										>Monthly subscription</span
									>
								</span>
							</span>
							<span class="text-[14px] font-medium text-black dark:text-white">{market.price}</span>
						</label>
					{/each}
				</div>

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
