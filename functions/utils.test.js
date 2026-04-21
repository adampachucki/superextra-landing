import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
	esc,
	row,
	confirmationHtml,
	stripMarkdown,
	checkRateLimit,
	validatePlaceContext,
	validateHistory
} from './utils.js';

// --- esc ---

describe('esc', () => {
	it('escapes &, <, >', () => {
		assert.equal(esc('a & b < c > d'), 'a &amp; b &lt; c &gt; d');
	});

	it('converts non-strings to string', () => {
		assert.equal(esc(42), '42');
		assert.equal(esc(null), 'null');
	});

	it('passes through safe strings', () => {
		assert.equal(esc('hello world'), 'hello world');
	});
});

// --- row ---

describe('row', () => {
	it('escapes value by default', () => {
		const html = row('Name', '<script>');
		assert.ok(html.includes('&lt;script&gt;'));
		assert.ok(html.includes('Name'));
	});

	it('renders raw HTML when raw=true', () => {
		const html = row('Link', '<a href="#">click</a>', true);
		assert.ok(html.includes('<a href="#">click</a>'));
	});
});

// --- confirmationHtml ---

describe('confirmationHtml', () => {
	it('extracts first name', () => {
		const html = confirmationHtml('John Doe');
		assert.ok(html.includes('Hey John,'));
	});

	it('falls back to "there" when name is empty', () => {
		const html = confirmationHtml('');
		assert.ok(html.includes('Hey there,'));
	});

	it('escapes HTML in name', () => {
		const html = confirmationHtml('<script> Doe');
		assert.ok(html.includes('&lt;script&gt;'));
		assert.ok(!html.includes('<script>'));
	});
});

// --- stripMarkdown ---

describe('stripMarkdown', () => {
	it('removes headings', () => {
		assert.equal(stripMarkdown('# Title\n## Subtitle'), 'Title\nSubtitle');
	});

	it('removes bold', () => {
		assert.equal(stripMarkdown('**bold text**'), 'bold text');
	});

	it('removes italic', () => {
		assert.equal(stripMarkdown('*italic text*'), 'italic text');
	});

	it('removes strikethrough', () => {
		assert.equal(stripMarkdown('~~deleted~~'), 'deleted');
	});

	it('removes inline code', () => {
		assert.equal(stripMarkdown('use `console.log`'), 'use');
	});

	it('converts links to text', () => {
		assert.equal(stripMarkdown('[click here](https://example.com)'), 'click here');
	});

	it('removes list markers', () => {
		assert.equal(
			stripMarkdown('- item one\n* item two\n+ item three'),
			'item one\nitem two\nitem three'
		);
	});

	it('removes ordered list markers', () => {
		assert.equal(stripMarkdown('1. first\n2. second'), 'first\nsecond');
	});

	it('removes blockquotes', () => {
		assert.equal(stripMarkdown('> quoted text'), 'quoted text');
	});

	it('collapses excess newlines', () => {
		assert.equal(stripMarkdown('a\n\n\n\nb'), 'a\n\nb');
	});
});

// --- checkRateLimit ---

describe('checkRateLimit', () => {
	it('allows requests under limit', () => {
		const map = new Map();
		const now = Date.now();
		assert.equal(checkRateLimit(map, '1.2.3.4', now, 600000, 20), true);
		assert.equal(checkRateLimit(map, '1.2.3.4', now + 1000, 600000, 20), true);
	});

	it('blocks at limit', () => {
		const map = new Map();
		const now = Date.now();
		for (let i = 0; i < 20; i++) {
			assert.equal(checkRateLimit(map, '1.2.3.4', now, 600000, 20), true);
		}
		assert.equal(checkRateLimit(map, '1.2.3.4', now, 600000, 20), false);
	});

	it('resets after window expires', () => {
		const map = new Map();
		const now = Date.now();
		for (let i = 0; i < 20; i++) {
			checkRateLimit(map, '1.2.3.4', now, 600000, 20);
		}
		assert.equal(checkRateLimit(map, '1.2.3.4', now, 600000, 20), false);
		// After window
		assert.equal(checkRateLimit(map, '1.2.3.4', now + 600001, 600000, 20), true);
	});

	it('tracks IPs independently', () => {
		const map = new Map();
		const now = Date.now();
		for (let i = 0; i < 20; i++) {
			checkRateLimit(map, '1.1.1.1', now, 600000, 20);
		}
		assert.equal(checkRateLimit(map, '1.1.1.1', now, 600000, 20), false);
		assert.equal(checkRateLimit(map, '2.2.2.2', now, 600000, 20), true);
	});
});

// --- validatePlaceContext / validateHistory ---

describe('validatePlaceContext', () => {
	it('sanitizes valid input and rejects invalid input', () => {
		// Valid
		assert.deepEqual(validatePlaceContext({ name: 'Test', placeId: 'abc', secondary: 'NY' }), {
			name: 'Test',
			placeId: 'abc',
			secondary: 'NY'
		});
		// Defaults missing optional fields
		assert.deepEqual(validatePlaceContext({ name: 'Test' }), {
			name: 'Test',
			placeId: '',
			secondary: ''
		});
		// Truncates long name
		assert.equal(validatePlaceContext({ name: 'A'.repeat(200) }).name.length, 100);
		// Rejects missing/invalid
		for (const bad of [
			null,
			undefined,
			'str',
			[1],
			{ placeId: 'x' },
			{ name: '' },
			{ name: 123 }
		]) {
			assert.equal(validatePlaceContext(bad), null, `expected null for ${JSON.stringify(bad)}`);
		}
	});
});

describe('validateHistory', () => {
	it('passes arrays through (capped at 50) and rejects non-arrays', () => {
		assert.deepEqual(validateHistory([1, 2]), [1, 2]);
		assert.equal(validateHistory(Array.from({ length: 60 })).length, 50);
		for (const bad of [null, 'str', {}, undefined]) {
			assert.deepEqual(validateHistory(bad), []);
		}
	});
});
