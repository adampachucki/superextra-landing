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

This is permanent, not just during animation. A CSS transition that ends at `transform: scale(1)` still maintains a containing block after the animation finishes. This affects **all** fixed children: sidebars, overlays, floating buttons, prompt bars — they all need to be siblings of the transform container, not children.

```html
<!-- The entrance animation sets transform on .chat-enter -->
<div class="chat-enter">
	<!-- has transform: scale(0.97) → scale(1) — permanent containing block! -->
	<!-- BAD: none of these will be fixed to the viewport -->
	<button class="fixed top-4 left-4">Toggle</button>
	<aside class="fixed top-0 left-0 h-dvh w-64">Sidebar</aside>
	<div class="fixed right-0 bottom-0 left-0">Prompt bar</div>
</div>

<!-- GOOD: move ALL fixed elements outside the transform container -->
<button class="fixed top-4 left-4">Toggle</button>
<aside class="fixed top-0 left-0 h-dvh w-64">Sidebar</aside>
<div class="chat-enter">...</div>
<div class="fixed right-0 bottom-0 left-0">Prompt bar</div>
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

### 7. `fixed inset-0` elements must be conditionally rendered

Even invisible `fixed inset-0` elements (e.g. `opacity-0`, `pointer-events-none`) trigger solid safe areas. Safari's heuristic checks CSS properties, not visual appearance. If you have a modal overlay, sidebar backdrop, or any full-screen fixed element, conditionally render it with `{#if}` rather than toggling opacity.

```html
<!-- BAD: always in DOM, kills translucent even when invisible -->
<div
	class="{open ? 'opacity-100' : 'opacity-0 pointer-events-none'} fixed inset-0 bg-black/20"
></div>

<!-- GOOD: removed from DOM when not needed -->
{#if open}
<div class="fixed inset-0 bg-black/20"></div>
{/if}
```

### 8. Page-level scroll vs inner overflow scroll

Safari grants translucent safe areas to the **page-level scroll**, not to inner `overflow-y: auto` containers. If your content scrolls inside a bounded `div` (e.g. a flex child with `overflow-y-auto`), the page itself doesn't scroll, and Safari treats it as an app-like layout.

To get translucent safe areas on a chat UI, let the content flow in normal document flow and scroll with the page:

```html
<!-- BAD: inner scroll container, page doesn't scroll → solid safe areas -->
<div class="flex h-dvh">
	<div class="flex-1 overflow-y-auto">
		<ChatThread />
	</div>
</div>

<!-- GOOD: page-level scroll → translucent safe areas -->
<div class="min-h-dvh">
	<ChatThread />
	<!-- content flows naturally, page scrolls -->
</div>
```

This means the scrollbar appears at the page edge (not within a content column), but it's the only way to get translucent safe areas on a scroll-heavy layout.

## Putting it together: chat UI pattern

```html
<!-- Fixed toggle button (outside transform container) -->
<button class="fixed top-[max(1rem,env(safe-area-inset-top))] left-4 z-30 ...">...</button>

<!-- Main layout (normal document flow, page-level scroll) -->
<div class="app-enter relative min-h-dvh">
	<!-- Sidebar: fixed, slides in/out. Overlay conditionally rendered. -->
	{#if !isDesktop && sidebarOpen}
	<div class="fixed inset-0 z-40 bg-black/20" onclick="{closeSidebar}"></div>
	{/if}
	<aside class="{sidebarOpen ? '' : '-translate-x-full'} fixed top-0 left-0 z-50 h-dvh w-64">
		...
	</aside>

	<!-- Main content (flows in document, page scrolls) -->
	<div class="{isDesktop && sidebarOpen ? 'pl-64' : ''} min-h-dvh pb-40">
		<ChatThread />
	</div>
</div>

<!-- Fixed prompt bar (outside transform container, full-width bg = solid bottom safe area) -->
<div
	class="{isDesktop && sidebarOpen ? 'left-64' : ''} fixed right-0 bottom-0 left-0 z-20 bg-cream"
>
	<div class="mx-auto max-w-3xl px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
		<div class="rounded-2xl border bg-white ...">
			<textarea>...</textarea>
		</div>
	</div>
</div>
```

Key points:

- `min-h-dvh` on the outer container (not `h-dvh`)
- Content flows in normal document flow — page-level scroll gives translucent top safe area
- Fixed elements (toggle, prompt) are siblings of the layout, not children of transform containers
- Sidebar overlay conditionally rendered (`{#if}`) — `fixed inset-0` in DOM kills translucent even when invisible
- Sidebar is `fixed` with `h-dvh` (narrow element, doesn't trigger solid)
- Full-width prompt bar with `bg-cream` at bottom = solid bottom safe area (acceptable trade-off)
- No `transform`-based animations on fixed elements near safe areas
- `pb-40` on content area clears the fixed prompt bar

## What we tested

| Pattern                                            | Top safe area | Bottom safe area |
| -------------------------------------------------- | ------------- | ---------------- |
| `fixed inset-0 bg-cream`                           | Solid         | Solid            |
| `fixed inset-0` (no bg)                            | Solid         | Solid            |
| `fixed inset-0 opacity-0` (invisible but in DOM)   | Solid         | Solid            |
| `h-dvh flex`                                       | Solid         | Solid            |
| `min-h-dvh`                                        | Translucent   | Translucent      |
| `min-h-dvh flex`                                   | Translucent   | Translucent      |
| `min-h-dvh flex` + child `max-h-dvh`               | Solid         | Solid            |
| Inner `overflow-y-auto` (page doesn't scroll)      | Solid         | Solid            |
| Page-level scroll (`min-h-dvh`, no overflow)       | Translucent   | Translucent      |
| Small fixed button (top)                           | Translucent   | Translucent      |
| Small fixed button (bottom)                        | Translucent   | Translucent      |
| Wide fixed button (bottom, `left-4 right-4`)       | Translucent   | Translucent      |
| Fixed prompt with `transform` animation            | Translucent   | Solid            |
| Fixed full-width bar (`left-0 right-0 bg-cream`)   | Translucent   | Solid            |
| Fixed prompt card (no transform, no full-width bg) | Translucent   | Translucent      |

## Stack

Tested with: SvelteKit 2, Svelte 5, Tailwind CSS v4, iOS Safari 18+, iPhone with Dynamic Island.
