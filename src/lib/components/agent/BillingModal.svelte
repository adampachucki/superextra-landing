<script lang="ts">
	import { billing } from '$lib/billing-state.svelte';
	import Modal from '$lib/components/Modal.svelte';
	import * as m from '$lib/paraglide/messages';
</script>

<Modal
	open={billing.modalVisible}
	onclose={() => billing.closeUpgrade()}
	labelledby="billing-title"
	maxWidth="max-w-md"
	z="z-[80]"
	dismissible={!billing.posting}
>
	<div class="p-6">
		<h2 id="billing-title" class="text-lg font-medium tracking-tight text-black dark:text-white">
			Superextra Pro
		</h2>
		<p class="mt-1 text-[13px] leading-snug text-black/50 dark:text-white/50">
			{billing.mode === 'test' ? m.bill_test_mode() : m.bill_country_note()}
		</p>

		<label
			for="billing-market"
			class="mt-6 mb-1.5 block text-xs font-medium text-black/60 dark:text-white/60"
		>
			{m.bill_country()}
		</label>
		<div class="relative">
			<select
				id="billing-market"
				bind:value={billing.selectedMarket}
				class="field appearance-none pr-10"
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
				{m.bill_test_card()}
			</p>
		{/if}

		<div class="mt-6 flex items-center justify-end gap-2">
			<button
				type="button"
				onclick={() => billing.closeUpgrade()}
				disabled={billing.posting}
				class="btn-secondary px-4 py-2 text-[13px]"
			>
				{m.bill_cancel()}
			</button>
			<button
				type="button"
				onclick={() => billing.startCheckout(billing.selectedMarket)}
				disabled={billing.posting}
				class="btn-primary px-4 py-2 text-[13px]"
			>
				{billing.posting ? m.bill_opening() : m.bill_continue()}
			</button>
		</div>
	</div>
</Modal>
