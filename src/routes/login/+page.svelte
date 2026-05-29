<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/auth.svelte';
	import LoginForm from '$lib/components/agent/LoginForm.svelte';
	import Seo from '$lib/components/Seo.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import * as m from '$lib/paraglide/messages';

	// Initial state is `completing` so the prerendered HTML ships with the
	// neutral "Signing you in…" placeholder. Magic-link arrivals stay on this
	// state until completion or the email-confirm form takes over; standalone
	// visits flip to `form` synchronously in onMount before any async work,
	// avoiding a flash from spinner to form.
	let phase = $state<'completing' | 'form' | 'confirm-email'>('completing');
	let errorCode = $state<string | null>(null);
	let returnTo = $state<string | null>(null);
	let confirmEmail = $state('');
	let confirming = $state(false);
	let confirmError = $state<string | null>(null);
	let magicUrl = '';

	function safeReturnTo(raw: string | null): string | null {
		if (!raw) return null;
		if (!raw.startsWith('/')) return null;
		// Reject protocol-relative redirects and paths with auth-bypass surface.
		if (raw.startsWith('//')) return null;
		return raw;
	}

	function buildChatUrlFromDraft() {
		const draft = auth.consumeDraft();
		if (!draft) return null;
		const params: string[] = [`q=${encodeURIComponent(draft.prompt)}`];
		if (draft.placeContext) {
			params.push(`placeId=${encodeURIComponent(draft.placeContext.placeId)}`);
			params.push(`placeName=${encodeURIComponent(draft.placeContext.name)}`);
			if (draft.placeContext.secondary) {
				params.push(`placeSecondary=${encodeURIComponent(draft.placeContext.secondary)}`);
			}
		}
		return `/chat?${params.join('&')}`;
	}

	async function postSignInDestination(): Promise<string> {
		// returnTo wins (the user was going somewhere specific). Draft is only
		// honoured when there's no explicit returnTo.
		const target = safeReturnTo(returnTo);
		if (target) return target;
		const draftUrl = buildChatUrlFromDraft();
		if (draftUrl) return draftUrl;
		return '/chat';
	}

	async function tryCompleteMagicLink() {
		magicUrl = window.location.href;
		try {
			const result = await auth.completeMagicLinkSignIn(magicUrl);
			if (result.kind === 'not-magic-link') {
				// Standalone login entry (e.g. arrived via shared-URL redirect).
				phase = 'form';
				return;
			}
			if (result.kind === 'needs-email') {
				// Clicked link in a browser without the stored email — ask for
				// confirmation inline instead of throwing a native window.prompt.
				phase = 'confirm-email';
				return;
			}
			const dest = await postSignInDestination();
			goto(dest, { replaceState: true });
		} catch (err) {
			const code =
				(err as { code?: string } | null)?.code ?? (err instanceof Error ? err.message : 'unknown');
			errorCode = code;
			phase = 'form';
		}
	}

	async function handleConfirmEmail(e: Event) {
		e.preventDefault();
		const trimmed = confirmEmail.trim();
		if (!trimmed || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
			confirmError = m.login_confirm_err_enter();
			return;
		}
		confirming = true;
		confirmError = null;
		try {
			await auth.finishMagicLinkSignIn(magicUrl, trimmed);
			const dest = await postSignInDestination();
			goto(dest, { replaceState: true });
		} catch (err) {
			const code =
				(err as { code?: string } | null)?.code ?? (err instanceof Error ? err.message : 'unknown');
			if (code === 'auth/invalid-action-code' || code === 'auth/expired-action-code') {
				errorCode = code;
				phase = 'form';
				return;
			}
			if (code === 'auth/invalid-email') {
				confirmError = m.login_confirm_err_mismatch();
			} else {
				confirmError = m.login_confirm_err_failed();
			}
		} finally {
			confirming = false;
		}
	}

	onMount(() => {
		const url = new URL(window.location.href);
		returnTo = url.searchParams.get('returnTo');
		void auth.init();
		// Quick sync URL probe — Firebase magic-link URLs carry `oobCode`. If
		// it's not present we know there's no link to complete and can show
		// the login form immediately, no spinner flash.
		if (!url.searchParams.has('oobCode')) {
			phase = 'form';
			return;
		}
		void tryCompleteMagicLink();
	});

	// If the user signs in via the embedded form (Google or magic-link from this
	// same tab), navigate to the post-sign-in destination.
	$effect(() => {
		if (auth.status !== 'signed-in') return;
		if (phase !== 'form') return;
		void (async () => {
			const dest = await postSignInDestination();
			goto(dest, { replaceState: true });
		})();
	});
</script>

<Seo
	title={m.login_seo_title()}
	description={m.login_seo_desc()}
	canonicalPath="/login"
	robots="noindex, nofollow, noarchive, nosnippet"
	localized={false}
/>

<main class="flex min-h-dvh items-center justify-center bg-[var(--color-cream)] px-4">
	<div class="w-full max-w-[400px]">
		{#if phase === 'completing'}
			<div class="flex flex-col items-center gap-3 text-center">
				<Spinner class="h-5 w-5 text-black/40 dark:text-white/40" />
				<p class="text-[14px] text-black/55 dark:text-white/55">{m.login_signing_you_in()}</p>
			</div>
		{:else if phase === 'confirm-email'}
			<div class="space-y-4">
				<div class="space-y-1 text-center">
					<a
						href="/"
						class="inline-flex items-center gap-0.5 text-black no-underline dark:text-white"
					>
						<svg class="-mt-1 h-[16px] w-[16px]" viewBox="0 0 12 12" fill="none">
							<line x1="6" y1="0.5" x2="6" y2="11.5" stroke="currentColor" stroke-width="1.5" />
							<line
								x1="1.24"
								y1="3.25"
								x2="10.76"
								y2="8.75"
								stroke="currentColor"
								stroke-width="1.5"
							/>
							<line
								x1="1.24"
								y1="8.75"
								x2="10.76"
								y2="3.25"
								stroke="currentColor"
								stroke-width="1.5"
							/>
						</svg>
						<span class="text-[20px] font-light tracking-tight">Superextra</span>
					</a>
					<h1 class="pt-4 text-[18px] font-light text-black dark:text-white">
						{m.login_confirm_title()}
					</h1>
					<p class="text-[13px] text-black/55 dark:text-white/55">
						{m.login_confirm_sub()}
					</p>
				</div>
				<form onsubmit={handleConfirmEmail} class="space-y-3">
					<input
						type="email"
						bind:value={confirmEmail}
						placeholder={m.login_email_ph()}
						autocomplete="email"
						required
						disabled={confirming}
						class="field disabled:opacity-50"
					/>
					<button
						type="submit"
						disabled={confirming || !confirmEmail.trim()}
						class="w-full rounded-xl bg-black px-4 py-3 text-[14px] font-medium text-white transition-colors hover:bg-black/85 disabled:opacity-30 dark:bg-white dark:text-black dark:hover:bg-white/85"
					>
						{confirming ? m.login_signing_in() : m.af_continue()}
					</button>
				</form>
				{#if confirmError}
					<p class="text-[13px] text-red-600 dark:text-red-400" role="alert">
						{confirmError}
					</p>
				{/if}
			</div>
		{:else if phase === 'form'}
			<div class="space-y-4">
				<a
					href="/"
					class="inline-flex items-center gap-0.5 text-black no-underline dark:text-white"
				>
					<svg class="-mt-1 h-[16px] w-[16px]" viewBox="0 0 12 12" fill="none">
						<line x1="6" y1="0.5" x2="6" y2="11.5" stroke="currentColor" stroke-width="1.5" />
						<line
							x1="1.24"
							y1="3.25"
							x2="10.76"
							y2="8.75"
							stroke="currentColor"
							stroke-width="1.5"
						/>
						<line
							x1="1.24"
							y1="8.75"
							x2="10.76"
							y2="3.25"
							stroke="currentColor"
							stroke-width="1.5"
						/>
					</svg>
					<span class="text-[20px] font-light tracking-tight">Superextra</span>
				</a>
				<LoginForm
					{returnTo}
					initialError={errorCode}
					title={returnTo ? m.login_open_chat_title() : m.login_seo_title()}
					subtitle={returnTo ? m.login_open_chat_sub() : ''}
				/>
			</div>
		{/if}
	</div>
</main>
