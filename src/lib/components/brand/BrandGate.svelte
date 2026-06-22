<script lang="ts">
	// PIN gate for internal /brand/* tools. Renders its children only once unlocked.
	// Reuses the same PIN + sessionStorage key as /brand, so unlocking either unlocks both.
	import { onMount } from 'svelte';
	import { unlock } from '$lib/brand/gate';

	let { children }: { children: import('svelte').Snippet } = $props();

	const PIN_LENGTH = 4;
	let unlocked = $state(false);
	let digits = $state<string[]>(Array(PIN_LENGTH).fill(''));
	let shake = $state(false);
	let busy = $state(false);
	let inputs: HTMLInputElement[] = [];

	onMount(() => {
		if (sessionStorage.getItem('brand_html') !== null) {
			unlocked = true;
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
			const html = await unlock(digits.join(''));
			busy = false;
			if (html !== null) {
				sessionStorage.setItem('brand_html', html);
				unlocked = true;
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

{#if unlocked}
	{@render children()}
{:else}
	<div class="gate">
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
