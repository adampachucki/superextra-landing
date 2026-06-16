<script lang="ts">
	import { onMount } from 'svelte';

	const PIN_LENGTH = 4;

	let html = $state<string | null>(null);
	let phase = $state<'locked' | 'revealing' | 'unlocked'>('locked');
	let digits = $state<string[]>(Array(PIN_LENGTH).fill(''));
	let shake = $state(false);
	let busy = $state(false);
	let inputs: HTMLInputElement[] = [];

	function b64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
		return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)) as Uint8Array<ArrayBuffer>;
	}

	async function tryDecrypt(pin: string): Promise<string | null> {
		try {
			// Loaded only when a PIN is actually checked — a cached reload reads
			// plaintext from sessionStorage and never fetches the 80 KB bundle.
			const { BRAND_SALT, BRAND_IV, BRAND_CIPHERTEXT, BRAND_ITERATIONS } =
				await import('$lib/brand/brand-encrypted');
			const keyMaterial = await crypto.subtle.importKey(
				'raw',
				new TextEncoder().encode(pin),
				'PBKDF2',
				false,
				['deriveKey']
			);
			const key = await crypto.subtle.deriveKey(
				{
					name: 'PBKDF2',
					salt: b64ToBytes(BRAND_SALT),
					iterations: BRAND_ITERATIONS,
					hash: 'SHA-256'
				},
				keyMaterial,
				{ name: 'AES-GCM', length: 256 },
				false,
				['decrypt']
			);
			const decrypted = await crypto.subtle.decrypt(
				{ name: 'AES-GCM', iv: b64ToBytes(BRAND_IV) },
				key,
				b64ToBytes(BRAND_CIPHERTEXT)
			);
			return new TextDecoder().decode(decrypted);
		} catch {
			return null;
		}
	}

	onMount(() => {
		const cached = sessionStorage.getItem('brand_html');
		if (cached !== null) {
			html = cached;
			phase = 'unlocked';
			return;
		}
		if (window.matchMedia('(pointer: fine)').matches) inputs[0]?.focus();
	});

	async function onDigit(index: number, value: string) {
		if (busy) return;
		if (value && !/^\d$/.test(value)) {
			digits[index] = '';
			return;
		}
		digits[index] = value;
		if (value && index < PIN_LENGTH - 1) inputs[index + 1]?.focus();

		if (digits.every((d) => d !== '')) {
			busy = true;
			const result = await tryDecrypt(digits.join(''));
			busy = false;
			if (result) {
				sessionStorage.setItem('brand_html', result);
				html = result;
				phase = 'revealing';
				setTimeout(() => (phase = 'unlocked'), 400);
			} else {
				shake = true;
				setTimeout(() => {
					shake = false;
					digits = Array(PIN_LENGTH).fill('');
					inputs[0]?.focus();
				}, 500);
			}
		}
	}

	function onKeydown(index: number, e: KeyboardEvent) {
		if (e.key === 'Backspace' && !digits[index] && index > 0) inputs[index - 1]?.focus();
	}
</script>

<svelte:head>
	<title>Superextra — Brand</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

{#if phase === 'unlocked'}
	<!-- Trusted source: our own HTML, AES-GCM-decrypted from the bundled ciphertext (never user input).
	     DOMPurify isn't used because the content ships its own <style> block, which sanitizers strip. -->
	<!-- eslint-disable-next-line svelte/no-at-html-tags -->
	<div class="reveal">{@html html}</div>
{:else}
	<div class="gate" class:fade-out={phase === 'revealing'}>
		<svg class="gmark" viewBox="0 0 12 12" fill="none">
			<line x1="6" y1="0.5" x2="6" y2="11.5" stroke="currentColor" stroke-width="1.3" />
			<line x1="0.5" y1="6" x2="11.5" y2="6" stroke="currentColor" stroke-width="1.3" />
			<line x1="2.11" y1="2.11" x2="9.89" y2="9.89" stroke="currentColor" stroke-width="1.3" />
			<line x1="2.11" y1="9.89" x2="9.89" y2="2.11" stroke="currentColor" stroke-width="1.3" />
		</svg>
		<div class="pins" class:shake>
			{#each digits as d, i (i)}
				<input
					bind:this={inputs[i]}
					type="text"
					inputmode="numeric"
					maxlength="1"
					value={d}
					disabled={busy}
					oninput={(e) => onDigit(i, e.currentTarget.value)}
					onkeydown={(e) => onKeydown(i, e)}
				/>
			{/each}
		</div>
	</div>
{/if}

<style>
	.gate {
		position: fixed;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 22px;
		background: #1a1714;
		color: #ede9e3;
		animation: fade-in 0.4s ease;
	}
	.gate.fade-out {
		animation: fade-out 0.4s ease forwards;
	}
	.gmark {
		width: 26px;
		height: 26px;
		opacity: 0.55;
	}
	.pins {
		display: flex;
		gap: 12px;
	}
	/* Cached reload: pre-paint guard in app.html hides the prompt so the
	   gate reads as a loading splash until the content hydrates in. */
	:global(html[data-brand-unlocked]) .pins {
		display: none;
	}
	.pins input {
		height: 52px;
		width: 42px;
		border-radius: 9px;
		border: 1px solid rgba(237, 233, 227, 0.16);
		background: transparent;
		text-align: center;
		font-size: 20px;
		color: #ede9e3;
		outline: none;
		transition: border-color 0.2s ease;
		font-family: 'Inter', system-ui, sans-serif;
	}
	.pins input:focus {
		border-color: rgba(237, 233, 227, 0.5);
	}
	.pins input:disabled {
		opacity: 0.3;
	}
	.pins.shake {
		animation: shake 0.45s ease;
	}
	.reveal {
		animation: fade-in 0.5s ease;
	}
	@keyframes fade-in {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}
	@keyframes fade-out {
		from {
			opacity: 1;
		}
		to {
			opacity: 0;
		}
	}
	@keyframes shake {
		0%,
		100% {
			transform: translateX(0);
		}
		20%,
		60% {
			transform: translateX(-7px);
		}
		40%,
		80% {
			transform: translateX(7px);
		}
	}
</style>
