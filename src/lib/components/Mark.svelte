<script lang="ts">
	// The Superextra eight-point asterisk mark. Geometry comes from the shared
	// brand-geometry module so every surface draws the same mark — pass sizing/colour
	// via `class` (stroke is currentColor; size with h-/w- utilities on the caller).
	import { MARK_LINES, MARK_VB, MARK_STROKE } from '$lib/brand/brand-geometry';

	let { class: className = '' }: { class?: string } = $props();
</script>

<svg class={className} viewBox="0 0 {MARK_VB} {MARK_VB}" fill="none" aria-hidden="true">
	{#each MARK_LINES as [x1, y1, x2, y2] (`${x1},${y1},${x2},${y2}`)}
		<line {x1} {y1} {x2} {y2} stroke="currentColor" stroke-width={MARK_STROKE} />
	{/each}
</svg>
