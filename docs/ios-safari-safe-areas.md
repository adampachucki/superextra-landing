# iOS Safari Translucent Safe Areas

How to achieve translucent (gradient/blur) safe areas on iOS Safari with SvelteKit, Tailwind CSS, and full-screen app-like layouts (chat UIs, dashboards, etc.).

## The problem

iOS Safari can render the safe area regions (notch/Dynamic Island at top, home indicator at bottom) with a translucent gradient that blends the page background into the system chrome. This is the default behavior on simple pages like marketing sites, but breaks the moment you build an app-like layout with fixed positioning, viewport-locked containers, or overflow containment.

Most chat UIs, dashboards, and SPAs lose this effect because their CSS patterns trigger Safari to fall back to a solid-color safe area.

## Prerequisites

In your `app.html` (or equivalent):

```html
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<meta name="color-scheme" content="light dark" />
```

- `viewport-fit=cover` extends the viewport to the physical screen edges (required)
- Do NOT set a `<meta name="theme-color">` tag — Safari auto-detects from the page background, and explicit values override the translucent effect
- Set your page background on `body` (it propagates to the CSS canvas, which is what Safari renders in safe areas)

```css
body {
	background-color: var(--your-bg-color);
}
```

## Rules (discovered through experimentation)

### 1. Use `min-h-dvh`, never `h-dvh` or `h-screen`

Safari checks whether the page can scroll. A viewport-locked container signals "app mode" and triggers solid safe areas.

```html
<!-- GOOD: page can theoretically scroll -->
<div class="min-h-dvh">...</div>

<!-- BAD: viewport-locked, triggers solid safe areas -->
<div class="h-dvh">...</div>
<div class="fixed inset-0">...</div>
```

This applies transitively: if a child has `max-h-dvh` or any constraint that locks the page to exactly viewport height, Safari detects it and switches to solid.

### 2. No `position: fixed; inset: 0` containers

The classic app-shell pattern (`fixed inset-0 flex`) covers the entire screen with an element, preventing the body canvas from showing through in safe areas.

```html
<!-- BAD -->
<div class="fixed inset-0 flex bg-cream">
	<aside>...</aside>
	<main>...</main>
</div>

<!-- GOOD -->
<div class="relative flex min-h-dvh">
	<aside>...</aside>
	<main>...</main>
</div>
```

### 3. No full-width backgrounds covering safe areas

Any element with `left-0 right-0` (or `inset-x-0`) AND a background color at the bottom of the screen will cause Safari to render the bottom safe area as solid.

```html
<!-- BAD: full-width bg-cream bar at bottom -->
<div class="fixed right-0 bottom-0 left-0 bg-cream">
	<div class="mx-auto max-w-3xl px-4">...</div>
</div>

<!-- GOOD: card with margins, no full-width background -->
<div
	class="fixed right-4 bottom-[max(0.75rem,env(safe-area-inset-bottom))] left-4 mx-auto max-w-3xl"
>
	<div class="rounded-2xl border bg-white ...">...</div>
</div>
```

### 4. No CSS `transform` on fixed elements near safe areas

CSS `transform` on a fixed element (even `translateY(0)`) interacts with Safari's safe area detection. Entrance animations that use `transform` will break translucency.

```css
/* BAD: this kills translucent safe areas on the fixed element */
.input-enter {
	transform: translateY(24px);
	transition: transform 0.8s;
}
.input-enter.is-mounted {
	transform: translateY(0); /* still a transform! */
}
```

Use `opacity`-only animations for fixed elements near safe areas, or skip the animation entirely.

### 5. Fixed elements must be outside `transform` containers

A parent with `transform` (even `transform: scale(1)`) creates a new containing block. Any `position: fixed` child inside it behaves as `position: absolute` — it won't be fixed to the viewport.

```html
<!-- The entrance animation sets transform on .chat-enter -->
<div class="chat-enter">
	<!-- has transform: scale(0.97) → scale(1) -->
	<!-- BAD: this button won't actually be fixed to the viewport -->
	<button class="fixed top-4 left-4">Toggle</button>
</div>

<!-- GOOD: move fixed elements outside the transform container -->
<button class="fixed top-4 left-4">Toggle</button>
<div class="chat-enter">...</div>
```

### 6. Small fixed elements are fine

Small fixed elements (buttons, FABs, floating cards) at any screen edge don't break translucent safe areas. Safari's heuristic triggers on full-width coverage, not on the presence of any fixed element.

```html
<!-- GOOD: small toggle button, doesn't affect safe areas -->
<button
	class="fixed top-[max(1rem,env(safe-area-inset-top))] left-4 z-30 h-9 w-9 rounded-full bg-black/80"
>
	...
</button>
```

## Putting it together: chat UI pattern

```html
<!-- Fixed toggle button (outside transform container) -->
<button class="fixed top-[max(1rem,env(safe-area-inset-top))] left-4 z-30 ...">...</button>

<!-- Fixed prompt card (outside transform container, no full-width bg) -->
<div
	class="fixed right-4 bottom-[max(0.75rem,env(safe-area-inset-bottom))] left-4 z-20 mx-auto max-w-3xl"
>
	<div class="rounded-2xl border bg-white ...">
		<textarea>...</textarea>
	</div>
</div>

<!-- Main layout (normal document flow) -->
<div class="app-enter relative flex min-h-dvh">
	<!-- Sidebar: absolute on mobile, relative on desktop -->
	<aside class="{isDesktop ? 'relative' : 'absolute z-50'} inset-y-0 left-0 ...">...</aside>

	<!-- Main content column -->
	<div class="relative flex min-w-0 flex-1 flex-col">
		<!-- Chat thread: min-h-0 allows shrinking, overflow-hidden clips -->
		<div class="flex min-h-0 flex-1 flex-col overflow-hidden">
			<ChatThread />
		</div>
	</div>
</div>
```

Key points:

- `min-h-dvh` on the outer container (not `h-dvh`)
- Fixed elements (toggle, prompt) are siblings of the layout, not children
- No full-width background on the fixed prompt — just a bordered card with margins
- No `transform`-based animations on fixed elements
- Sidebar uses `absolute` (not `fixed`) on mobile so it stays within the layout container
- Chat thread uses `min-h-0 flex-1 overflow-hidden` to scroll internally

## What we tested

| Pattern                                            | Top safe area | Bottom safe area |
| -------------------------------------------------- | ------------- | ---------------- |
| `fixed inset-0 bg-cream`                           | Solid         | Solid            |
| `fixed inset-0` (no bg)                            | Solid         | Solid            |
| `h-dvh flex`                                       | Solid         | Solid            |
| `min-h-dvh`                                        | Translucent   | Translucent      |
| `min-h-dvh flex`                                   | Translucent   | Translucent      |
| `min-h-dvh flex` + child `max-h-dvh`               | Solid         | Solid            |
| Small fixed button (top)                           | Translucent   | Translucent      |
| Small fixed button (bottom)                        | Translucent   | Translucent      |
| Wide fixed button (bottom, `left-4 right-4`)       | Translucent   | Translucent      |
| Fixed prompt with `transform` animation            | Translucent   | Solid            |
| Fixed full-width bar (`left-0 right-0 bg-cream`)   | Translucent   | Solid            |
| Fixed prompt card (no transform, no full-width bg) | Translucent   | Translucent      |

## Stack

Tested with: SvelteKit 2, Svelte 5, Tailwind CSS v4, iOS Safari 18+, iPhone with Dynamic Island.
