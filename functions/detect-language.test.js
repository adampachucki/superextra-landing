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

	it("returns null on 'und' (only a place/proper name) so the caller keeps the established language", async () => {
		const generate = async () => ({ language: 'und' });
		assert.equal(await detectLanguage({ message: 'Garnizon Gdańsk', generate }), null);
	});

	it('returns null on an unusable model value', async () => {
		const generate = async () => ({ language: '123' });
		assert.equal(await detectLanguage({ message: 'x', generate }), null);
	});

	it('fails open to null when the model throws', async () => {
		const generate = async () => {
			throw new Error('vertex_down');
		};
		assert.equal(await detectLanguage({ message: 'hello', generate }), null);
	});

	it('returns null for empty input without calling the model', async () => {
		let called = false;
		const generate = async () => {
			called = true;
			return { language: 'pl' };
		};
		assert.equal(await detectLanguage({ message: '   ', generate }), null);
		assert.equal(called, false);
	});
});
