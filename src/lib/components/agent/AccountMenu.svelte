<script lang="ts">
	import { goto } from '$app/navigation';
	import { auth } from '$lib/auth.svelte';
	import { billing } from '$lib/billing-state.svelte';

	interface Props {
		// `inline` (sidebar) renders the avatar + name+email row with a popover
		// dropdown above. `compact` (navbar) renders just the avatar circle with
		// the dropdown anchored below-right.
		variant?: 'inline' | 'compact';
	}

	let { variant = 'compact' }: Props = $props();

	let open = $state(false);
	let signingOut = $state(false);
	let billingAction = $derived(billing.paid || billing.canManage ? 'Manage billing' : 'Upgrade');

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
		if (billing.paid || billing.canManage) {
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
		<div class="border-b border-black/[0.06] px-3 py-2 dark:border-white/[0.06]">
			<p class="truncate text-[12px] text-black dark:text-white">
				{user.displayName ?? user.email ?? 'Signed in'}
			</p>
			{#if user.displayName && user.email}
				<p class="truncate text-[11px] text-black/40 dark:text-white/40">{user.email}</p>
			{/if}
			{#if billing.paid}
				<p class="mt-1 text-[11px] text-black/40 dark:text-white/40">
					{billing.snapshot.cancelAtPeriodEnd ? 'Unlimited ends soon' : 'Unlimited'}
				</p>
			{/if}
		</div>
		<button
			type="button"
			onclick={handleBilling}
			disabled={billing.posting}
			class="block w-full px-3 py-2 text-left text-[13px] text-black/70 transition-colors hover:bg-cream-100 hover:text-black disabled:opacity-50 dark:text-white/70 dark:hover:bg-cream-100 dark:hover:text-white"
			role="menuitem"
		>
			{billing.posting ? 'Opening…' : billingAction}
		</button>
		<button
			type="button"
			onclick={handleSignOut}
			disabled={signingOut}
			class="block w-full px-3 py-2 text-left text-[13px] text-black/70 transition-colors hover:bg-cream-100 hover:text-black disabled:opacity-50 dark:text-white/70 dark:hover:bg-cream-100 dark:hover:text-white"
			role="menuitem"
		>
			{signingOut ? 'Signing out…' : 'Sign out'}
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
						{user.displayName ?? user.email ?? 'Signed in'}
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
					class="absolute right-3 bottom-full left-3 mb-2 rounded-lg border border-black/[0.08] bg-white py-1 shadow-lg dark:border-white/[0.08] dark:bg-cream-50"
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
				aria-label="Account"
				class="flex h-8 w-8 items-center justify-center overflow-hidden rounded-full bg-black text-[11px] font-medium text-white transition-opacity hover:opacity-80 dark:bg-white dark:text-black"
			>
				{@render avatar()}
			</button>
			{#if open}
				<div
					class="absolute top-full right-0 mt-2 w-56 rounded-lg border border-black/[0.08] bg-white py-1 shadow-lg dark:border-white/[0.08] dark:bg-cream-50"
					role="menu"
				>
					{@render menuItems()}
				</div>
			{/if}
		</div>
	{/if}
{/if}
