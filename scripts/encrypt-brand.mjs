/**
 * Encrypts src/lib/brand/brand-content.html with AES-256-GCM using a PBKDF2-derived
 * key from the PIN, mirroring the memo page in the superextra/ repo.
 *
 * Usage:  node scripts/encrypt-brand.mjs <PIN>
 * Output: src/lib/brand/brand-encrypted.ts
 *
 * (Re-run after editing the page: `node scripts/build-brand-content.mjs` then this.)
 */
import { readFileSync, writeFileSync } from 'fs';
import { randomBytes, pbkdf2Sync, createCipheriv } from 'crypto';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

const pin = process.argv[2];
if (!pin) {
	console.error('Usage: node scripts/encrypt-brand.mjs <PIN>');
	process.exit(1);
}

const ITERATIONS = 600_000;
const html = readFileSync(join(root, 'src/lib/brand/brand-content.html'), 'utf-8');

const salt = randomBytes(16);
const iv = randomBytes(12);
const key = pbkdf2Sync(pin, salt, ITERATIONS, 32, 'sha256');

const cipher = createCipheriv('aes-256-gcm', key, iv);
const encrypted = Buffer.concat([cipher.update(html, 'utf-8'), cipher.final()]);
const tag = cipher.getAuthTag();
const ciphertext = Buffer.concat([encrypted, tag]); // Web Crypto expects ciphertext+tag concatenated

const out = `// Auto-generated — do not edit. Run: npm run encrypt-brand <PIN>
export const BRAND_SALT = '${salt.toString('base64')}';
export const BRAND_IV = '${iv.toString('base64')}';
export const BRAND_CIPHERTEXT = '${ciphertext.toString('base64')}';
export const BRAND_ITERATIONS = ${ITERATIONS};
`;

writeFileSync(join(root, 'src/lib/brand/brand-encrypted.ts'), out);
console.log('Encrypted brand content written to src/lib/brand/brand-encrypted.ts');
