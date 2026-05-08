<script lang="ts">
	import type { PlaceSearch, PlaceSuggestion } from '$lib/place-search.svelte';

	let {
		place,
		inputEl = $bindable(),
		placeholder = 'Venue name...',
		direction = 'down',
		onSelect
	}: {
		place: PlaceSearch;
		inputEl?: HTMLInputElement;
		placeholder?: string;
		direction?: 'down' | 'up';
		onSelect?: () => void;
	} = $props();

	let highlight = $state(-1);

	function resetHighlight() {
		highlight = -1;
	}

	function handleSelect(s: PlaceSuggestion) {
		place.select(s);
		resetHighlight();
		inputEl?.blur();
		onSelect?.();
	}

	$effect(() => {
		place.suggestions;
		resetHighlight();
	});

	function onKeydown(e: KeyboardEvent) {
		const count = place.suggestions.length;
		if (e.key === 'Escape') {
			e.preventDefault();
			place.hideSuggestions();
			resetHighlight();
			return;
		}
		if (!place.showSuggestions || count === 0) return;
		if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
			e.preventDefault();
			const delta = e.key === 'ArrowDown' ? 1 : -1;
			highlight = highlight < 0 ? (delta > 0 ? 0 : count - 1) : (highlight + delta + count) % count;
			return;
		}
		if (e.key === 'Enter' && highlight >= 0) {
			e.preventDefault();
			handleSelect(place.suggestions[highlight]);
		}
	}
</script>

<div class="relative">
	<input
		bind:this={inputEl}
		type="text"
		value={place.query}
		oninput={(e) => place.setQuery((e.target as HTMLInputElement).value)}
		onfocus={() => {
			if (place.suggestions.length) place.setQuery(place.query);
		}}
		onblur={() => {
			setTimeout(() => place.hideSuggestions(), 150);
			resetHighlight();
		}}
		onkeydown={onKeydown}
		{placeholder}
		autocomplete="off"
		autocorrect="off"
		autocapitalize="off"
		spellcheck="false"
		class="w-full rounded-xl border border-black/[0.08] bg-cream-50/50 px-4 py-2.5 pr-9 text-[13px] text-black placeholder:text-black/30 focus:border-black/25 focus:outline-none dark:border-white/[0.08] dark:bg-white/[0.03] dark:text-white dark:placeholder:text-white/30 dark:focus:border-white/25"
	/>
	{#if place.loading}
		<svg
			class="absolute top-1/2 right-3 h-3.5 w-3.5 -translate-y-1/2 animate-spin text-black/25 dark:text-white/25"
			xmlns="http://www.w3.org/2000/svg"
			fill="none"
			viewBox="0 0 24 24"
		>
			<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3"
			></circle>
			<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
			></path>
		</svg>
	{/if}
	{#if place.showSuggestions && place.suggestions.length > 0}
		<ul
			class="absolute right-0 left-0 z-50 max-h-48 overflow-auto rounded-xl border border-black/[0.08] bg-white py-1 shadow-lg dark:border-white/[0.08] dark:bg-cream-50 {direction ===
			'up'
				? 'bottom-full mb-1'
				: 'top-full mt-1'}"
		>
			{#each place.suggestions as s, i (s.placeId)}
				<li>
					<button
						type="button"
						class="w-full px-4 py-2.5 text-left text-[13px] transition-colors hover:bg-cream-50 dark:hover:bg-white/[0.04] {i ===
						highlight
							? 'bg-cream-50 dark:bg-white/[0.04]'
							: ''}"
						onpointerdown={(e) => e.preventDefault()}
						onclick={() => handleSelect(s)}
					>
						<span class="text-black dark:text-white">{s.name}</span>
						{#if s.secondary}
							<span class="ml-1.5 text-black/45 dark:text-white/45">{s.secondary}</span>
						{/if}
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</div>
