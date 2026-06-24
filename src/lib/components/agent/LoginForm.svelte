<script lang="ts">
	import { auth } from '$lib/auth.svelte';
	import { localizeHref } from '$lib/paraglide/runtime';
	import * as analytics from '$lib/analytics';
	import * as m from '$lib/paraglide/messages';

	interface Props {
		returnTo?: string | null;
		initialError?: string | null;
		title?: string;
		subtitle?: string;
	}

	let {
		returnTo = null,
		initialError = null,
		title = m.login_title(),
		subtitle = m.login_subtitle()
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
				return m.login_err_popup_blocked();
			case 'auth/popup-closed-by-user':
			case 'auth/cancelled-popup-request':
				return m.login_err_popup_closed();
			case 'auth/account-exists-with-different-credential':
				return m.login_err_account_exists();
			case 'auth/operation-not-allowed':
			case 'auth/operation-not-supported-in-this-environment':
				return m.login_err_not_allowed();
			case 'auth/configuration-not-found':
			case 'auth/unauthorized-domain':
				return m.login_err_misconfigured();
			case 'auth/invalid-action-code':
			case 'auth/expired-action-code':
				return m.login_err_link_expired();
			case 'auth/invalid-email':
			case 'Valid email is required':
				return m.login_err_invalid_email();
			case 'http_429':
				return m.login_err_too_many();
			case 'Email send failed':
			case 'Email service unreachable':
			case 'Magic link generation failed':
				return m.login_err_email_failed();
			default:
				return m.login_err_generic();
		}
	}

	async function handleGoogle() {
		if (busy) return;
		analytics.capture('login_method_selected', { method: 'google' });
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
		analytics.capture('login_method_selected', { method: 'magic_link' });
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
			{mode === 'email-sent' ? m.login_check_email() : title}
		</h2>
		{#if mode === 'email-sent'}
			<p class="text-[13px] leading-snug text-black/50 dark:text-white/50">
				{m.login_sent_1()} <span class="text-black dark:text-white">{email}</span>{m.login_sent_2()}
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
			{pending === 'google' ? m.login_signing_in() : m.login_google()}
		</button>

		<div class="flex items-center gap-3">
			<div class="h-px flex-1 bg-black/[0.08] dark:bg-white/[0.08]"></div>
			<span class="text-[11px] tracking-wider text-black/40 uppercase dark:text-white/40">{m.login_or()}</span>
			<div class="h-px flex-1 bg-black/[0.08] dark:bg-white/[0.08]"></div>
		</div>

		<form onsubmit={handleEmail} class="space-y-3">
			<input
				type="email"
				bind:value={email}
				placeholder={m.login_email_ph()}
				autocomplete="email"
				required
				class="field disabled:opacity-50"
				disabled={busy}
			/>
			<button
				type="submit"
				disabled={busy || !email.trim()}
				class="btn-primary w-full px-4 py-3 text-[14px]"
			>
				{pending === 'email' ? m.login_sending() : m.login_email_link()}
			</button>
		</form>

		{#if errorCode}
			<p class="text-[13px] text-red-600 dark:text-red-400" role="alert">
				{friendlyError(errorCode)}
			</p>
		{/if}

		<p class="pt-1 text-[12px] leading-snug text-black/45 dark:text-white/45">
			{m.login_terms_pre()}
			<a
				href={localizeHref('/terms')}
				target="_blank"
				rel="noopener"
				class="italic transition-colors hover:text-black dark:hover:text-white"
				>{m.login_terms()}</a
			>
			{m.login_and()}
			<a
				href={localizeHref('/privacy-policy')}
				target="_blank"
				rel="noopener"
				class="italic transition-colors hover:text-black dark:hover:text-white"
				>{m.login_privacy()}</a
			>{m.login_free_suffix()}
		</p>
	{:else}
		<button
			type="button"
			onclick={reset}
			class="text-[13px] text-black/55 underline-offset-2 transition-colors hover:text-black/80 hover:underline dark:text-white/55 dark:hover:text-white/80"
		>
			{m.login_use_different()}
		</button>
	{/if}
</div>
