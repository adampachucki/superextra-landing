<script lang="ts">
	import { auth } from '$lib/auth.svelte';

	interface Props {
		returnTo?: string | null;
		initialError?: string | null;
		title?: string;
		subtitle?: string;
	}

	let {
		returnTo = null,
		initialError = null,
		title = 'Sign in to continue',
		subtitle = 'Save your chats and pick up where you left off.'
	}: Props = $props();

	let email = $state('');
	let pending = $state<'google' | 'email' | null>(null);
	const busy = $derived(pending !== null);
	let mode = $state<'choose' | 'email-sent'>('choose');
	let localErrorCode = $state<string | null>(null);
	const errorCode = $derived(localErrorCode ?? initialError);

	function friendlyError(code: string): string {
		switch (code) {
			case 'auth/popup-blocked':
				return 'Browser blocked the sign-in popup. Try email instead.';
			case 'auth/popup-closed-by-user':
			case 'auth/cancelled-popup-request':
				return 'Sign-in window closed before finishing. Try again.';
			case 'auth/account-exists-with-different-credential':
				return 'This email is already linked to a different sign-in method. Use that method instead.';
			case 'auth/operation-not-allowed':
			case 'auth/operation-not-supported-in-this-environment':
				return 'Google sign-in is not available yet. Use email below for now.';
			case 'auth/configuration-not-found':
			case 'auth/unauthorized-domain':
				return 'Sign-in is misconfigured for this domain. Try email below or contact support.';
			case 'auth/invalid-action-code':
			case 'auth/expired-action-code':
				return 'This sign-in link expired. Enter your email below to get a new one.';
			case 'auth/invalid-email':
			case 'Valid email is required':
				return 'Enter a valid email address.';
			case 'http_429':
				return 'Too many sign-in attempts. Wait a few minutes and try again.';
			case 'Email send failed':
			case 'Email service unreachable':
			case 'Magic link generation failed':
				return 'We couldn’t send the sign-in email. Try again in a moment.';
			default:
				return 'Something went wrong. Try again.';
		}
	}

	async function handleGoogle() {
		if (busy) return;
		pending = 'google';
		localErrorCode = null;
		try {
			await auth.signInWithGoogle();
		} catch (err) {
			const code =
				(err as { code?: string } | null)?.code ??
				(err instanceof Error ? err.message : 'unknown');
			localErrorCode = code;
		} finally {
			pending = null;
		}
	}

	async function handleEmail(e: Event) {
		e.preventDefault();
		if (busy) return;
		const trimmed = email.trim();
		if (!trimmed || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
			localErrorCode = 'auth/invalid-email';
			return;
		}
		pending = 'email';
		localErrorCode = null;
		try {
			await auth.sendMagicLink(trimmed, returnTo);
			mode = 'email-sent';
		} catch (err) {
			localErrorCode = err instanceof Error ? err.message : 'unknown';
		} finally {
			pending = null;
		}
	}

	function reset() {
		mode = 'choose';
		localErrorCode = null;
	}
</script>

<div class="space-y-4">
	<div class="space-y-1">
		<h2 class="text-lg font-medium tracking-tight text-black dark:text-white">
			{mode === 'email-sent' ? 'Check your email' : title}
		</h2>
		{#if mode === 'email-sent'}
			<p class="text-[13px] leading-snug text-black/50 dark:text-white/50">
				We sent a sign-in link to <span class="text-black dark:text-white">{email}</span>. Open it on
				this device to come back signed in.
			</p>
		{:else if subtitle}
			<p class="text-[13px] leading-snug text-black/50 dark:text-white/50">{subtitle}</p>
		{/if}
	</div>
	{#if mode === 'choose'}
		<button
			type="button"
			onclick={handleGoogle}
			disabled={busy}
			class="btn-outline flex w-full items-center justify-center gap-3 px-4 py-3 text-[14px]"
		>
			<svg class="h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
				<path
					fill="#4285F4"
					d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
				/>
				<path
					fill="#34A853"
					d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
				/>
				<path
					fill="#FBBC05"
					d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
				/>
				<path
					fill="#EA4335"
					d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
				/>
			</svg>
			{pending === 'google' ? 'Signing in…' : 'Continue with Google'}
		</button>

		<div class="flex items-center gap-3">
			<div class="h-px flex-1 bg-black/[0.08] dark:bg-white/[0.08]"></div>
			<span class="text-[11px] tracking-wider text-black/40 uppercase dark:text-white/40">or</span>
			<div class="h-px flex-1 bg-black/[0.08] dark:bg-white/[0.08]"></div>
		</div>

		<form onsubmit={handleEmail} class="space-y-3">
			<input
				type="email"
				bind:value={email}
				placeholder="you@example.com"
				autocomplete="email"
				required
				class="w-full rounded-xl border border-black/[0.12] bg-white px-4 py-3 text-[14px] text-black placeholder:text-black/30 focus:border-black/[0.55] focus:ring-0 focus:outline-none disabled:opacity-50 dark:border-white/[0.12] dark:bg-cream-50 dark:text-white dark:placeholder:text-white/30 dark:focus:border-white/[0.55]"
				disabled={busy}
			/>
			<button
				type="submit"
				disabled={busy || !email.trim()}
				class="btn-primary w-full px-4 py-3 text-[14px]"
			>
				{pending === 'email' ? 'Sending…' : 'Email me a sign-in link'}
			</button>
		</form>

		{#if errorCode}
			<p class="text-[13px] text-red-600 dark:text-red-400" role="alert">
				{friendlyError(errorCode)}
			</p>
		{/if}

		<p class="pt-1 text-[12px] leading-snug text-black/45 dark:text-white/45">
			By continuing, you agree to the
			<a
				href="/terms"
				target="_blank"
				rel="noopener"
				class="italic transition-colors hover:text-black dark:hover:text-white"
				>Terms</a
			>
			and
			<a
				href="/privacy-policy"
				target="_blank"
				rel="noopener"
				class="italic transition-colors hover:text-black dark:hover:text-white"
				>Privacy Policy</a
			>. Free accounts get 1 research per day.
		</p>
	{:else}
		<button
			type="button"
			onclick={reset}
			class="text-[13px] text-black/55 underline-offset-2 transition-colors hover:text-black/80 hover:underline dark:text-white/55 dark:hover:text-white/80"
		>
			Use a different email
		</button>
	{/if}
</div>
