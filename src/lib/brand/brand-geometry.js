// Single source of truth for the Superextra mark + lockup proportions.
// Imported by BOTH the build-time generator (scripts/build-brand-content.mjs, plain
// node ESM) and the browser download engine (src/routes/brand/+page.svelte), so the
// on-page CSS render and the SVG/PNG exports can never drift. Plain .js with JSDoc
// types because the node generator can't import .ts directly.

// Eight-point asterisk: four lines crossing at 45° in a 0–12 viewBox, stroke 1.3.
/** @type {[number, number, number, number][]} */
export const MARK_LINES = [
	[6, 0.5, 6, 11.5],
	[0.5, 6, 11.5, 6],
	[2.11, 2.11, 9.89, 9.89],
	[2.11, 9.89, 9.89, 2.11]
];
export const MARK_VB = 12; // mark viewBox extent
export const MARK_STROKE = 1.3; // mark stroke-width, in viewBox units

// Lockup proportions, all relative to the wordmark size. The eight-point mark runs a
// touch smaller than the old 18/22 so its denser center doesn't read heavy.
export const MARK_K = 0.75; // lockup mark width ÷ wordmark
export const GAP_K = 2 / 22; // mark→word gap ÷ wordmark
export const RAISE_K = 0.36; // mark raise ÷ wordmark (also the monogram raise)
export const WORD_K = 5.85; // gallery-tile wordmark size in cqw, at k = 1
export const TAG_K = 0.31; // tagline size ÷ wordmark

// ✲S monogram, relative to the "S" size.
export const MONO_MARK_K = 0.55; // monogram mark width ÷ S
export const MONO_GAP_K = 0.04; // monogram mark→S gap ÷ S
export const MONO_CAP_K = 0.7; // S cap height ÷ S (system-font approximation)
// The "S" is centred and the mark raised, which leaves the ✲S group top-heavy; drop the
// whole group by this fraction of S so its bounding box sits centred in a square icon.
export const MONO_DROP_K = (RAISE_K + MONO_MARK_K / 2 - MONO_CAP_K / 2) / 2; // ≈ 0.1425
