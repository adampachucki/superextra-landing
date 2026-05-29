<script lang="ts">
	import { goto } from '$app/navigation';
	import { auth } from '$lib/auth.svelte';
	import { billing } from '$lib/billing-state.svelte';
	import * as m from '$lib/paraglide/messages';

	interface Props {
		// `inline` (sidebar) renders the avatar + name+email row with a popover
		// dropdown above. `compact` (navbar) renders just the avatar circle with
		// the dropdown anchored below-right.
		variant?: 'inline' | 'compact';
	}

	let { variant = 'compact' }: Props = $props();

	let open = $state(false);
	let signingOut = $state(false);
	let billingAction = $derived(
		billing.mode === 'test'
			? billing.canManage
				? m.am_manage_test()
				: m.am_test_pro()
			: billing.canManage
				? m.am_manage()
				: m.am_upgrade()
	);

	function handleWindowClick(e: MouseEvent) {
		const target = e.target as HTMLElement;
		if (open && !target.closest('.account-menu')) open = false;
	}

	function avatarInitials(): string {
		const name = auth.user?.displayName ?? auth.user?.email ?? '';
		const parts = name.trim().split(/\s+/).filter(Boolean);
		if (!parts.length) return '?';
		if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase();
		return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
	}

	async function handleSignOut() {
		if (signingOut) return;
		signingOut = true;
		try {
			await auth.signOut();
			open = false;
			goto('/', { replaceState: true });
		} catch (err) {
			console.warn('sign out failed:', err);
		} finally {
			signingOut = false;
		}
	}

	async function handleBilling() {
		open = false;
		if (billing.canManage) {
			await billing.openPortal();
		} else {
			billing.openUpgrade();
		}
	}
</script>

<svelte:window onclick={handleWindowClick} />

{#if auth.user}
	{@const user = auth.user}
	{#snippet avatar()}
		{#if user.photoURL}
			<img
				src={user.photoURL}
				alt=""
				referrerpolicy="no-referrer"
				class="h-full w-full object-cover"
			/>
		{:else}
			{avatarInitials()}
		{/if}
	{/snippet}

	{#snippet menuItems()}
		<div class="border-b border-black/[0.06] px-4 py-2 dark:border-white/[0.06]">
			<p class="truncate text-[12px] text-black dark:text-white">
				{user.displayName ?? user.email ?? m.am_signed_in()}
			</p>
			{#if user.displayName && user.email}
				<p class="truncate text-[11px] text-black/40 dark:text-white/40">{user.email}</p>
			{/if}
			{#if billing.paid}
				<p class="mt-1 text-[11px] text-black/40 dark:text-white/40">
					{billing.mode === 'test'
						? billing.snapshot.cancelAtPeriodEnd
							? m.am_test_pro_ends()
							: m.am_test_pro()
						: billing.snapshot.cancelAtPeriodEnd
							? m.am_pro_ends()
							: m.am_pro()}
				</p>
			{:else if billing.mode === 'test'}
				<p class="mt-1 text-[11px] text-black/40 dark:text-white/40">{m.am_test_billing()}</p>
			{/if}
		</div>
		<button
			type="button"
			onclick={handleBilling}
			disabled={billing.posting}
			class="popover-option text-[13px] text-black/70 hover:text-black disabled:opacity-50 dark:text-white/70 dark:hover:text-white"
			role="menuitem"
		>
			{billing.posting ? m.bill_opening() : billingAction}
		</button>
		<button
			type="button"
			onclick={handleSignOut}
			disabled={signingOut}
			class="popover-option text-[13px] text-black/70 hover:text-black disabled:opacity-50 dark:text-white/70 dark:hover:text-white"
			role="menuitem"
		>
			{signingOut ? m.am_signing_out() : m.am_sign_out()}
		</button>
	{/snippet}

	{#if variant === 'inline'}
		<div class="account-menu relative">
			<button
				type="button"
				onclick={() => (open = !open)}
				class="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-cream-100/60 dark:hover:bg-cream-100/40"
			>
				<span
					class="flex h-7 w-7 items-center justify-center overflow-hidden rounded-full bg-black text-[11px] font-medium text-white dark:bg-white dark:text-black"
				>
					{@render avatar()}
				</span>
				<div class="min-w-0 flex-1">
					<p class="truncate text-[12px] text-black dark:text-white">
						{user.displayName ?? user.email ?? m.am_signed_in()}
					</p>
					{#if user.displayName && user.email}
						<p class="truncate text-[11px] text-black/40 dark:text-white/40">
							{user.email}
						</p>
					{/if}
				</div>
			</button>
			{#if open}
				<div
					class="popover absolute right-3 bottom-full left-3 mb-2"
					role="menu"
				>
					{@render menuItems()}
				</div>
			{/if}
		</div>
	{:else}
		<div class="account-menu relative">
			<button
				type="button"
				onclick={() => (open = !open)}
				aria-label={m.am_account()}
				class="flex h-8 w-8 items-center justify-center overflow-hidden rounded-full bg-black text-[11px] font-medium text-white transition-opacity hover:opacity-80 dark:bg-white dark:text-black"
			>
				{@render avatar()}
			</button>
			{#if open}
				<div
					class="popover absolute top-full right-0 mt-2 w-56"
					role="menu"
				>
					{@render menuItems()}
				</div>
			{/if}
		</div>
	{/if}
{/if}
