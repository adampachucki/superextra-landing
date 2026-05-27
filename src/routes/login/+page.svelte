<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/auth.svelte';
	import LoginForm from '$lib/components/agent/LoginForm.svelte';
	import Seo from '$lib/components/Seo.svelte';

	let phase = $state<'unknown' | 'completing' | 'form'>('unknown');
	let errorCode = $state<string | null>(null);
	let returnTo = $state<string | null>(null);

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
		phase = 'completing';
		try {
			const result = await auth.completeMagicLinkSignIn(window.location.href);
			if (!result) {
				// Not a magic-link URL — show the login form so this page also acts
				// as a standalone login entry (e.g. shared chat URL redirect).
				phase = 'form';
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

	onMount(() => {
		const url = new URL(window.location.href);
		returnTo = url.searchParams.get('returnTo');
		void auth.init();
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
	title="Sign in to Superextra"
	description="Sign in to Superextra to continue your restaurant market research."
	canonicalPath="/login"
	robots="noindex, nofollow, noarchive, nosnippet"
/>

<main class="flex min-h-dvh items-center justify-center bg-[var(--color-cream)] px-4">
	<div class="w-full max-w-[400px]">
		{#if phase === 'completing'}
			<p class="text-center text-[14px] text-black/55 dark:text-white/55">Signing you in…</p>
		{:else if phase === 'form'}
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
						{returnTo ? 'Sign in to continue' : 'Sign in to Superextra'}
					</h1>
					{#if returnTo}
						<p class="text-[13px] text-black/55 dark:text-white/55">Sign in to open this chat.</p>
					{/if}
				</div>
				<LoginForm {returnTo} initialError={errorCode} />
			</div>
		{/if}
	</div>
</main>
