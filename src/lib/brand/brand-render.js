// Shared SVG rendering of the Superextra lockup — mark + outlined wordmark/tagline.
// Imported by BOTH the build-time generator (scripts/build-brand-content.mjs, which draws the
// on-page preview tiles) and the browser export engine (src/routes/brand/+page.svelte), so the
// preview and the downloaded SVG/PNG are byte-identical: same geometry, same SF Pro Light
// outlines, no live-font optical-sizing drift between screen and file.
import { MARK_LINES, MARK_VB, MARK_STROKE, lockupGeom } from './brand-geometry.js';
import { UPM, SUPEREXTRA, TAGLINE } from './brand-glyphs.js';

// A glyph string's alphabetic baseline sits BASELINE_K·size below its em-centre — where the
// mark and wordmark are vertically anchored — matching SF Pro's metrics.
export const BASELINE_K = 0.394;

/**
 * Rendered advance width of an outlined string at a given size (px).
 * @param {{ adv: number }} g @param {number} size
 */
export const glyphWidth = (g, size) => (g.adv * size) / UPM;

/**
 * The four asterisk strokes, as <line>s, for a mark of `box` px at (ox, oy).
 * @param {number} ox @param {number} oy @param {number} box @param {string} color
 */
export function markLinesSVG(ox, oy, box, color) {
	const sw = ((box * MARK_STROKE) / MARK_VB).toFixed(2);
	return MARK_LINES.map(
		([x1, y1, x2, y2]) =>
			`<line x1="${(ox + (x1 / MARK_VB) * box).toFixed(2)}" y1="${(oy + (y1 / MARK_VB) * box).toFixed(2)}" x2="${(ox + (x2 / MARK_VB) * box).toFixed(2)}" y2="${(oy + (y2 / MARK_VB) * box).toFixed(2)}" stroke="${color}" stroke-width="${sw}"/>`
	).join('');
}

/**
 * An outlined glyph string placed with its alphabetic baseline at `baseline`, scaled to `size`
 * px. Paths are font units with y-up, so the y-scale is negated. `g` is either a glyph record
 * (inline the `d`, for self-contained export files) or a {ref} id (reference a shared <defs>
 * path via <use>, so the multi-tile preview embeds each outline once instead of per tile).
 * @param {{ d?: string, ref?: string }} g
 * @param {number} x @param {number} baseline @param {number} size @param {string} color
 */
export function glyphPathSVG(g, x, baseline, size, color) {
	const s = (size / UPM).toFixed(5);
	const t = `transform="translate(${x.toFixed(2)} ${baseline.toFixed(2)}) scale(${s} -${s})" fill="${color}"`;
	return g.ref ? `<use href="#${g.ref}" ${t}/>` : `<path ${t} d="${g.d}"/>`;
}

// The wordmark + tagline outlines defined once, for the preview to <use>. Emit at the top of the
// injected page so every tile's <use href> resolves to a single embedded copy of each path.
export function glyphDefs() {
	return `<svg width="0" height="0" aria-hidden="true" style="position:absolute"><defs><path id="se-word" d="${SUPEREXTRA.d}"/><path id="se-tag" d="${TAGLINE.d}"/></defs></svg>`;
}
const WORD_REF = { ref: 'se-word', adv: SUPEREXTRA.adv };
const TAG_REF = { ref: 'se-tag', adv: TAGLINE.adv };

/**
 * The full gallery-tile lockup body (mark + wordmark + tagline) in the tile's own w×h px space.
 * Both the preview SVG overlay and the SVG export render exactly this geometry. `useRefs` swaps
 * inlined wordmark/tagline paths for <use> of the shared defs (preview); exports inline them.
 * @param {number} w @param {number} h @param {number} k @param {number} m
 * @param {'lockup'|'split'|'splitbr'} layout @param {string} color @param {boolean} [useRefs]
 */
export function lockupBodySVG(w, h, k, m, layout, color, useRefs = false) {
	const g = lockupGeom(w, h, k, m, layout);
	const tagX = g.tagAnchor === 'end' ? g.tagX - glyphWidth(TAGLINE, g.tagsz) : g.tagX;
	const word = useRefs ? WORD_REF : SUPEREXTRA;
	const tag = useRefs ? TAG_REF : TAGLINE;
	return (
		markLinesSVG(g.markX, g.markY, g.markw, color) +
		glyphPathSVG(word, g.wordX, g.wordCY + BASELINE_K * g.word, g.word, color) +
		glyphPathSVG(tag, tagX, g.tagBaseline, g.tagsz, color)
	);
}
