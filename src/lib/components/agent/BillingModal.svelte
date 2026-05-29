<script lang="ts">
	import { billing } from '$lib/billing-state.svelte';
	import Modal from '$lib/components/Modal.svelte';
</script>

<Modal
	open={billing.modalVisible}
	onclose={() => billing.closeUpgrade()}
	labelledby="billing-title"
	maxWidth="max-w-md"
	z="z-[80]"
>
	<div class="border-b border-black/[0.06] px-5 py-4 pr-12 dark:border-white/[0.08]">
		<h2 id="billing-title" class="text-[16px] font-medium text-black dark:text-white">
			Superextra Pro
		</h2>
		<p class="mt-1 text-[13px] leading-snug text-black/50 dark:text-white/50">
			{billing.mode === 'test'
				? 'Stripe test mode. No real payment is collected.'
				: 'Billing country sets currency. Tax is included where applicable.'}
		</p>
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
				<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="m6 9 6 6 6-6" />
			</svg>
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
			class="btn-secondary px-4 py-2 text-[13px]"
		>
			Cancel
		</button>
		<button
			type="button"
			onclick={() => billing.startCheckout(billing.selectedMarket)}
			disabled={billing.posting}
			class="btn-primary px-4 py-2 text-[13px]"
		>
			{billing.posting ? 'Opening…' : 'Continue'}
		</button>
	</div>
</Modal>
