<script lang="ts">
	import { lockPageScroll } from '$lib/scroll-lock';
	import * as m from '$lib/paraglide/messages';
	import type { Snippet } from 'svelte';

	let {
		open,
		onclose,
		ariaLabel,
		labelledby,
		maxWidth = 'max-w-[400px]',
		z = 'z-[60]',
		dismissible = true,
		children
	}: {
		open: boolean;
		onclose: () => void;
		ariaLabel?: string;
		labelledby?: string;
		maxWidth?: string;
		z?: string;
		/** When false, the close button, backdrop click, and Escape are all inert. */
		dismissible?: boolean;
		children: Snippet;
	} = $props();

	// Single shared open/close motion: backdrop fades + blurs, panel slides + fades.
	// `mounted` keeps the node in the DOM through the exit animation; `visible`
	// toggles the animated classes one frame after mount. DURATION drives both the
	// JS unmount timer and the CSS transition (applied inline), so they stay in sync.
	const DURATION = 300;

	let mounted = $state(false);
	let visible = $state(false);
	let panelEl: HTMLDivElement | undefined = $state();
	let closeTimer: ReturnType<typeof setTimeout>;
	let enterFrame = 0;

	$effect(() => {
		if (open) {
			clearTimeout(closeTimer);
			mounted = true;
			enterFrame = requestAnimationFrame(() => {
				visible = true;
			});
		} else if (mounted) {
			cancelAnimationFrame(enterFrame);
			visible = false;
			closeTimer = setTimeout(() => {
				mounted = false;
			}, DURATION);
		}
	});

	$effect(() => {
		if (!mounted) return;
		return lockPageScroll();
	});

	$effect(() => {
		if (visible && panelEl) panelEl.focus();
	});

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			if (dismissible) onclose();
			return;
		}
		if (e.key !== 'Tab' || !panelEl) return;
		const focusable = panelEl.querySelectorAll<HTMLElement>(
			'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
		);
		if (focusable.length === 0) return;
		const first = focusable[0];
		const last = focusable[focusable.length - 1];
		const active = document.activeElement;
		// When the panel itself holds focus (initial state), or focus has somehow
		// landed outside the dialog, route Tab back to the appropriate edge.
		if (!(active instanceof HTMLElement) || !panelEl.contains(active) || active === panelEl) {
			e.preventDefault();
			(e.shiftKey ? last : first).focus();
		} else if (e.shiftKey && active === first) {
			e.preventDefault();
			last.focus();
		} else if (!e.shiftKey && active === last) {
			e.preventDefault();
			first.focus();
		}
	}
</script>

{#if mounted}
	<div
		role="presentation"
		style="transition-duration: {DURATION}ms"
		class="fixed inset-0 {z} flex items-center justify-center px-4 py-8 transition-all {visible
			? 'bg-black/40 backdrop-blur-sm'
			: 'backdrop-blur-0 bg-black/0'}"
		onmousedown={(e) => {
			if (dismissible && e.target === e.currentTarget) onclose();
		}}
	>
		<div
			bind:this={panelEl}
			role="dialog"
			aria-modal="true"
			aria-label={ariaLabel}
			aria-labelledby={labelledby}
			tabindex="-1"
			onkeydown={handleKeydown}
			style="transition-duration: {DURATION}ms"
			class="relative w-full {maxWidth} rounded-2xl bg-white shadow-2xl shadow-black/10 transition-all focus:outline-none dark:bg-cream-50 {visible
				? 'translate-y-0 opacity-100'
				: 'translate-y-4 opacity-0'}"
		>
			{#if dismissible}
				<button
					type="button"
					onclick={onclose}
					aria-label={m.modal_close()}
					class="absolute top-4 right-4 z-10 btn-icon h-8 w-8"
				>
					<svg
						class="h-4 w-4"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="2"
					>
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			{/if}

			{@render children()}
		</div>
	</div>
{/if}
