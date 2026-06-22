// Shared brand-area PIN check. Verifies the 4-digit PIN by decrypting the brand blob —
// same secret and crypto as the /brand page — so internal /brand/* tools gate on one PIN.
import { BRAND_SALT, BRAND_IV, BRAND_CIPHERTEXT, BRAND_ITERATIONS } from './brand-encrypted';

const b64 = (s: string): Uint8Array<ArrayBuffer> =>
	Uint8Array.from(atob(s), (c) => c.charCodeAt(0)) as Uint8Array<ArrayBuffer>;

/** Returns the decrypted brand HTML if the PIN is correct, else null. */
export async function unlock(pin: string): Promise<string | null> {
	try {
		const km = await crypto.subtle.importKey(
			'raw',
			new TextEncoder().encode(pin),
			'PBKDF2',
			false,
			['deriveKey']
		);
		const key = await crypto.subtle.deriveKey(
			{ name: 'PBKDF2', salt: b64(BRAND_SALT), iterations: BRAND_ITERATIONS, hash: 'SHA-256' },
			km,
			{ name: 'AES-GCM', length: 256 },
			false,
			['decrypt']
		);
		const dec = await crypto.subtle.decrypt(
			{ name: 'AES-GCM', iv: b64(BRAND_IV) },
			key,
			b64(BRAND_CIPHERTEXT)
		);
		return new TextDecoder().decode(dec);
	} catch {
		return null;
	}
}
