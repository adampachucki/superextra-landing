import { describe, expect, it } from 'vitest';

import { renderMarkdown } from './markdown';

describe('renderMarkdown', () => {
	it('exposes markdown table column count for responsive sizing', () => {
		const html = renderMarkdown('| A | B | C |\n| - | - | - |\n| 1 | 2 | 3 |');

		expect(html).toContain('class="markdown-table-scroll"');
		expect(html).toContain('style="--markdown-table-columns:3"');
	});
});
