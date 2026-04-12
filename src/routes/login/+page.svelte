<script lang="ts">
	import { theme } from '$lib/theme.svelte';
	import { onMount } from 'svelte';

	let step: 'email' | 'code' = $state('email');
	let email = $state('');
	let code = $state(['', '', '', '', '', '']);
	let sending = $state(false);
	let shake = $state(false);
	let codeInputs: HTMLInputElement[] = $state([]);
	let emailInput: HTMLInputElement | undefined = $state();

	function handleEmailSubmit(e: SubmitEvent) {
		e.preventDefault();
		if (!email.trim()) return;
		sending = true;
		setTimeout(() => {
			sending = false;
			history.pushState({ step: 'code' }, '');
			step = 'code';
			setTimeout(() => codeInputs[0]?.focus(), 50);
		}, 800);
	}

	function handleCodeInput(index: number, e: Event) {
		const input = e.target as HTMLInputElement;
		const value = input.value;

		if (!/^\d*$/.test(value)) {
			input.value = code[index];
			return;
		}

		if (value.length > 1) {
			const digits = value.split('').filter((c) => /\d/.test(c));
			digits.forEach((digit, i) => {
				if (index + i < 6) code[index + i] = digit;
			});
			const next = Math.min(index + digits.length, 5);
			codeInputs[next]?.focus();
			return;
		}

		code[index] = value;
		if (value && index < 5) {
			codeInputs[index + 1]?.focus();
		}
	}

	function handleCodeKeydown(index: number, e: KeyboardEvent) {
		if (e.key === 'Backspace' && !code[index] && index > 0) {
			codeInputs[index - 1]?.focus();
		}
	}

	function handlePaste(e: ClipboardEvent) {
		const paste = e.clipboardData?.getData('text') ?? '';
		const digits = paste.replace(/\D/g, '').slice(0, 6).split('');
		if (digits.length === 0) return;
		e.preventDefault();
		digits.forEach((d, i) => (code[i] = d));
		codeInputs[Math.min(digits.length, 5)]?.focus();
	}

	function verifyCode() {
		// TODO: validate code against backend
		shake = true;
		setTimeout(() => {
			shake = false;
			code = ['', '', '', '', '', ''];
			codeInputs[0]?.focus();
		}, 500);
	}

	let codeComplete = $derived(code.every((d) => d !== ''));

	$effect(() => {
		if (codeComplete) verifyCode();
	});

	onMount(() => {
		if (window.matchMedia('(min-width: 768px)').matches) {
			setTimeout(() => emailInput?.focus(), 300);
		}

		const onPopState = () => {
			if (step === 'code') {
				step = 'email';
				code = ['', '', '', '', '', ''];
			}
		};
		addEventListener('popstate', onPopState);
		return () => removeEventListener('popstate', onPopState);
	});
</script>

<svelte:head>
	<title>Log in - Superextra</title>
</svelte:head>

<div class="flex min-h-svh flex-col bg-cream">
	<!-- Content -->
	<div class="flex flex-1 items-center justify-center px-6">
		<div class="w-full max-w-xs">
			{#if step === 'email'}
				<h1
					class="stagger-1 mb-6 text-center text-2xl font-semibold tracking-tight text-black dark:text-white"
				>
					Log in
				</h1>
				<form onsubmit={handleEmailSubmit} class="stagger-2">
					<div class="relative">
						<input
							bind:this={emailInput}
							id="email"
							type="email"
							required
							bind:value={email}
							name="email"
							placeholder="Email address"
							autocomplete="email"
							class="w-full rounded-full border border-black/[0.12] bg-white py-3 pr-12 pl-4 text-[15px] text-black placeholder:text-black/25 focus:border-black/[0.55] focus:outline-none dark:border-white/[0.12] dark:bg-cream-50 dark:text-white dark:placeholder:text-white/25 dark:focus:border-white/[0.55]"
						/>
						<button
							type="submit"
							disabled={sending || !email.trim()}
							class="absolute top-1/2 right-1.5 -translate-y-1/2 cursor-pointer rounded-full bg-black p-2 transition-colors hover:bg-black/80 disabled:cursor-default disabled:opacity-20 dark:bg-white dark:hover:bg-white/80"
						>
							{#if sending}
								<svg
									class="h-4 w-4 animate-spin text-white dark:text-black"
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									><circle
										class="opacity-25"
										cx="12"
										cy="12"
										r="10"
										stroke="currentColor"
										stroke-width="4"
									></circle><path
										class="opacity-75"
										fill="currentColor"
										d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
									></path></svg
								>
							{:else}
								<svg
									class="h-4 w-4 text-white dark:text-black"
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									stroke="currentColor"
									stroke-width="2.5"
									><path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3"
									/></svg
								>
							{/if}
						</button>
					</div>
				</form>
			{:else}
				<h1
					class="mb-6 text-center text-2xl font-semibold tracking-tight text-black dark:text-white"
				>
					Log in
				</h1>
				<div class="flex gap-2 {shake ? 'shake' : ''}" onpaste={handlePaste}>
					{#each code as digit, i}
						<input
							bind:this={codeInputs[i]}
							type="text"
							inputmode="numeric"
							maxlength="1"
							value={digit}
							oninput={(e) => handleCodeInput(i, e)}
							onkeydown={(e) => handleCodeKeydown(i, e)}
							class="code-digit h-14 w-full rounded-xl border border-black/[0.12] bg-white text-center text-[22px] font-medium text-black focus:border-black/[0.55] focus:outline-none dark:border-white/[0.12] dark:bg-cream-50 dark:text-white dark:focus:border-white/[0.55]"
							style="animation-delay: {i * 40}ms"
						/>
					{/each}
				</div>

				<p class="code-hint mt-6 text-center text-[13px] text-black/25 dark:text-white/25">
					Code sent to <span class="text-black/50 dark:text-white/50">{email}</span>
				</p>
			{/if}
		</div>
	</div>

	<footer class="px-6 py-5">
		<div class="mx-auto flex max-w-[1200px] items-center justify-center gap-5">
			<p class="text-xs text-black/40 dark:text-white/40">
				&copy; {new Date().getFullYear()} Superextra
			</p>
			<a
				href="/privacy-policy"
				class="text-xs text-black/40 transition-colors hover:text-black/60 dark:text-white/40 dark:hover:text-white/60"
				>Privacy</a
			>
			<a
				href="/terms"
				class="text-xs text-black/40 transition-colors hover:text-black/60 dark:text-white/40 dark:hover:text-white/60"
				>Terms</a
			>
			<button
				onclick={() => theme.cycle()}
				class="cursor-pointer text-black/40 transition-colors hover:text-black/60 dark:text-white/40 dark:hover:text-white/60"
				aria-label="Toggle theme"
			>
				{#if theme.mode === 'dark'}
					<svg
						class="h-3.5 w-3.5"
						fill="none"
						viewBox="0 0 24 24"
						stroke="currentColor"
						stroke-width="1.5"
						><path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"
						/></svg
					>
				{:else if theme.mode === 'light'}
					<svg
						class="h-3.5 w-3.5"
						fill="none"
						viewBox="0 0 24 24"
						stroke="currentColor"
						stroke-width="1.5"
						><circle cx="12" cy="12" r="4" /><path
							stroke-linecap="round"
							d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32l1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41m11.32-11.32l1.41-1.41"
						/></svg
					>
				{:else}
					<svg
						class="h-3.5 w-3.5"
						fill="none"
						viewBox="0 0 24 24"
						stroke="currentColor"
						stroke-width="1.5"
						><path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25A2.25 2.25 0 015.25 3h13.5A2.25 2.25 0 0121 5.25z"
						/></svg
					>
				{/if}
			</button>
		</div>
	</footer>
</div>

<style>
	/* Email step entrance */
	.stagger-1 {
		animation: headingIn 0.8s cubic-bezier(0.16, 1, 0.3, 1) 0.05s both;
	}
	.stagger-2 {
		animation: scaleIn 0.9s cubic-bezier(0.16, 1, 0.3, 1) 0.2s both;
	}

	/* Code step entrance */
	.code-digit {
		animation: scaleIn 0.5s cubic-bezier(0.16, 1, 0.3, 1) both;
	}
	.code-hint {
		animation: fadeIn 0.6s ease 0.3s both;
	}

	.shake {
		animation: shake 0.4s ease-in-out;
	}

	@keyframes headingIn {
		from {
			opacity: 0;
			transform: translateY(8px) scale(0.97);
		}
		to {
			opacity: 1;
			transform: translateY(0) scale(1);
		}
	}

	@keyframes scaleIn {
		from {
			opacity: 0;
			transform: scale(0.95);
		}
		to {
			opacity: 1;
			transform: scale(1);
		}
	}

	@keyframes fadeIn {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}

	@keyframes shake {
		0%,
		100% {
			transform: translateX(0);
		}
		20% {
			transform: translateX(-8px);
		}
		40% {
			transform: translateX(8px);
		}
		60% {
			transform: translateX(-4px);
		}
		80% {
			transform: translateX(4px);
		}
	}
</style>
