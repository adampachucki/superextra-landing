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
// The lockup mark is raised so its centre sits this fraction of the wordmark ABOVE the
// wordmark's vertical centre — landing it near the cap height. This is a true full raise
// (applied via explicit coordinates / position, never a centred-flex margin, which would
// only move it half as far).
export const LOCKUP_RAISE_K = 0.18; // lockup mark raise ÷ wordmark
export const WORD_K = 5.85; // gallery-tile wordmark size in cqw, at k = 1
export const TAG_K = 0.33; // tagline size ÷ wordmark (sized so it overruns the wordmark ~8%)

// The mark+S monogram reuses the same mark width, gap, and raise as the primary lockup,
// measured against the S size. Only the whole-group drop is monogram-specific, so the same
// mark→letter relationship sits optically centred inside square/circle icon crops.
export const MONO_CAP_K = 0.7; // S cap height ÷ S (system-font approximation)
export const MONOGRAM_DROP_K = (LOCKUP_RAISE_K + MARK_K / 2 - MONO_CAP_K / 2) / 2; // ≈ 0.1025

// Tagline vertical rhythm (lockup layout): baseline sits TAG_BOTTOM_K·tagsz above the
// bottom inset, and TAG_GAP_K·tagsz + 0.5·word below the wordmark's vertical centre.
export const TAG_BOTTOM_K = 0.58;
export const TAG_GAP_K = 1.6;

/**
 * Lockup element positions for a w×h tile, in the tile's own px coordinate space — the single
 * source both the on-page preview and the SVG/PNG exports render from (as outlined SVG paths),
 * so the mark, wordmark and tagline land on identical coordinates everywhere.
 * @param {number} w @param {number} h @param {number} [k] @param {number} [m]
 * @param {'lockup'|'split'|'splitbr'} [layout]
 */
export function lockupGeom(w, h, k = 1, m = 0.12, layout = 'lockup') {
	const word = (WORD_K * k * w) / 100;
	const markw = word * MARK_K;
	const gap = word * GAP_K;
	const raise = word * LOCKUP_RAISE_K;
	const tagsz = word * TAG_K;
	const M = m * Math.min(w, h);
	const wordX = M + markw + gap;
	const tagBaseline = h - M - TAG_BOTTOM_K * tagsz;
	if (layout === 'lockup') {
		const wordCY = tagBaseline - TAG_GAP_K * tagsz - 0.5 * word;
		return {
			word,
			markw,
			gap,
			tagsz,
			markX: M,
			markY: wordCY - raise - markw / 2,
			wordX,
			wordCY,
			tagX: wordX,
			tagBaseline,
			tagAnchor: 'start'
		};
	}
	return {
		word,
		markw,
		gap,
		tagsz,
		markX: M,
		markY: M,
		wordX,
		wordCY: M + markw / 2 + raise,
		tagX: layout === 'splitbr' ? w - M : M,
		tagBaseline,
		tagAnchor: layout === 'splitbr' ? 'end' : 'start'
	};
}
