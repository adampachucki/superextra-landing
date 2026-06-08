import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import { detectLanguage } from './detect-language.js';

describe('detectLanguage', () => {
	it('returns the model-detected ISO code', async () => {
		const generate = async () => ({ language: 'pl' });
		assert.equal(await detectLanguage({ message: 'Gdzie otworzyć pizzerię?', generate }), 'pl');
	});

	it('lowercases and trims a noisy code', async () => {
		const generate = async () => ({ language: ' DE ' });
		assert.equal(await detectLanguage({ message: 'Wo?', generate }), 'de');
	});

	it("falls back to the UI locale on 'und'", async () => {
		const generate = async () => ({ language: 'und' });
		assert.equal(await detectLanguage({ message: 'Trattoria', fallback: 'de', generate }), 'de');
	});

	it('falls back on an unusable model value', async () => {
		const generate = async () => ({ language: '123' });
		assert.equal(await detectLanguage({ message: 'x', fallback: 'pl', generate }), 'pl');
	});

	it('fails open to the fallback when the model throws', async () => {
		const generate = async () => {
			throw new Error('vertex_down');
		};
		assert.equal(await detectLanguage({ message: 'hello', fallback: 'de', generate }), 'de');
	});

	it('returns the fallback for empty input without calling the model', async () => {
		let called = false;
		const generate = async () => {
			called = true;
			return { language: 'pl' };
		};
		assert.equal(await detectLanguage({ message: '   ', fallback: 'de', generate }), 'de');
		assert.equal(called, false);
	});

	it("defaults the fallback to 'en' when none is usable", async () => {
		const generate = async () => ({ language: 'und' });
		assert.equal(await detectLanguage({ message: '???', fallback: '!!', generate }), 'en');
	});
});
