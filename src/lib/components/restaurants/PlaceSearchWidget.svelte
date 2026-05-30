<script lang="ts">
	import { scale } from 'svelte/transition';
	import type { PlaceSearch, PlaceSuggestion } from '$lib/place-search.svelte';
	import Spinner from '$lib/components/Spinner.svelte';

	let {
		place,
		inputEl = $bindable(),
		placeholder = 'Restaurant, address, neighborhood, or city',
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
		class="field pr-9"
	/>
	{#if place.loading}
		<Spinner
			class="absolute top-1/2 right-3 h-3.5 w-3.5 -translate-y-1/2 text-black/25 dark:text-white/25"
		/>
	{/if}
	{#if place.showSuggestions && place.suggestions.length > 0}
		<ul
			class="absolute right-0 left-0 z-50 max-h-48 popover {direction === 'up'
				? 'bottom-full mb-1 origin-bottom'
				: 'top-full mt-1 origin-top'}"
			transition:scale={{ duration: 150, start: 0.97, opacity: 0 }}
		>
			{#each place.suggestions as s, i (s.placeId)}
				<li>
					<button
						type="button"
						class="popover-option text-[13px] {i === highlight ? 'bg-cream-100' : ''}"
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
