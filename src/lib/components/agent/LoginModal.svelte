<script lang="ts">
	import { onMount } from 'svelte';
	import { auth } from '$lib/auth.svelte';
	import LoginForm from './LoginForm.svelte';

	let mounted = $state(false);

	onMount(() => {
		// Kick auth init so onAuthStateChanged is wired before the user clicks.
		void auth.init();
		mounted = true;
	});

	// When auth resolves to signed-in while the modal is open, fire the queued
	// callback (if any) and close.
	$effect(() => {
		if (!auth.modalVisible) return;
		if (auth.status !== 'signed-in') return;
		const cb = auth.consumeAfterSignIn();
		auth.closeModal();
		if (cb) cb();
	});

	function handleBackdrop() {
		auth.closeModal();
	}

	function handleEscape(e: KeyboardEvent) {
		if (e.key !== 'Escape') return;
		if (!auth.modalVisible) return;
		auth.closeModal();
	}
</script>

<svelte:window onkeydown={handleEscape} />

{#if auth.modalVisible && mounted}
	<div
		class="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 px-4 backdrop-blur-sm"
		role="presentation"
		onclick={handleBackdrop}
	>
		<div
			class="relative w-full max-w-[400px] rounded-2xl bg-[var(--color-cream)] p-6 shadow-2xl dark:bg-cream-50"
			role="dialog"
			tabindex="-1"
			aria-modal="true"
			aria-label="Sign in to Superextra"
			onclick={(e) => e.stopPropagation()}
			onkeydown={(e) => e.stopPropagation()}
		>
			<button
				type="button"
				onclick={() => auth.closeModal()}
				aria-label="Close"
				class="absolute top-3 right-3 flex h-8 w-8 items-center justify-center rounded-full text-black/40 transition-colors hover:bg-black/[0.06] hover:text-black/70 dark:text-white/40 dark:hover:bg-white/[0.06] dark:hover:text-white/70"
			>
				<svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
				</svg>
			</button>

			<div class="mb-5 space-y-1">
				<h2 class="text-[18px] font-light text-black dark:text-white">Sign in to continue</h2>
				<p class="text-[13px] text-black/55 dark:text-white/55">
					Save your chats and pick up where you left off.
				</p>
			</div>

			<LoginForm returnTo={auth.modalReturnTo} />
		</div>
	</div>
{/if}
