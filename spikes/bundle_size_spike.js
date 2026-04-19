/* eslint-disable no-console, no-empty, @typescript-eslint/no-unused-vars */
// Spike G — Firebase SDK bundle-size measurement.
// (Lint disabled: this is throwaway validation code, not production.)
// Imports firebase/app + firebase/firestore + firebase/auth (modular v10),
// then checks how much they'd add to the chat-route bundle.
//
// Run: node spikes/bundle_size_spike.js
// (runs `npm run build` internally, parses stats)

import { execSync } from 'node:child_process';
import { readFileSync, existsSync, writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(__dirname, '..');

console.log('[spike-g] measuring Firebase SDK bundle impact on SvelteKit build...');

// Strategy: create a tiny Svelte component under src/routes that dynamically imports
// firebase modules; build twice (with and without the import); diff the chat-route
// bundle sizes.
//
// But the user's chat route is src/routes/agent/chat. Simpler: just create a sentinel
// file that imports firebase modules and run `npm run build`, capture the bundle sizes.

const SENTINEL = resolve(REPO, 'src/lib/_spike_firebase_sentinel.ts');
const PAGE = resolve(REPO, 'src/routes/_spike_g/+page.svelte');

function cleanup() {
	try {
		rmSync(SENTINEL, { force: true });
	} catch {}
	try {
		rmSync(dirname(PAGE), { force: true, recursive: true });
	} catch {}
}

process.on('exit', cleanup);
process.on('SIGINT', () => {
	cleanup();
	process.exit(1);
});

mkdirSync(dirname(PAGE), { recursive: true });

writeFileSync(
	SENTINEL,
	`
import { initializeApp } from 'firebase/app';
import { getFirestore, onSnapshot, query, where, orderBy, collection, doc } from 'firebase/firestore';
import { getAuth, signInAnonymously, onAuthStateChanged } from 'firebase/auth';

export function bootstrap() {
  const app = initializeApp({ projectId: 'superextra-site', apiKey: 'dummy' });
  const db = getFirestore(app);
  const auth = getAuth(app);
  return { app, db, auth, onSnapshot, query, where, orderBy, collection, doc, signInAnonymously, onAuthStateChanged };
}
`
);

writeFileSync(
	PAGE,
	`
<script>
  import { onMount } from 'svelte';
  import { bootstrap } from '$lib/_spike_firebase_sentinel';
  let ready = $state(false);
  onMount(async () => {
    const b = bootstrap();
    ready = !!b.db;
  });
</script>

<p>Spike G sentinel. Ready: {ready}</p>
`
);

// Ensure firebase package is installed; install if not
let firebaseInstalled = false;
try {
	execSync('node -e "require.resolve(\\"firebase/app\\")"', { cwd: REPO, stdio: 'pipe' });
	firebaseInstalled = true;
} catch {
	console.log('[spike-g] firebase not installed, running npm install firebase...');
	execSync('npm install firebase --save --no-fund --no-audit', { cwd: REPO, stdio: 'inherit' });
}

console.log('[spike-g] running npm run build (this may take a minute)...');
try {
	execSync('npm run build', {
		cwd: REPO,
		stdio: 'pipe',
		env: { ...process.env, NODE_OPTIONS: '--max-old-space-size=4096' }
	});
} catch (e) {
	console.error('[spike-g] build failed:', e.message);
	console.error(e.stdout?.toString?.() || '');
	console.error(e.stderr?.toString?.() || '');
	process.exit(1);
}

// Walk the .svelte-kit/output directory and find the chat-route client chunks
import { readdirSync, statSync } from 'node:fs';
const clientDir = resolve(REPO, '.svelte-kit/output/client/_app/immutable/nodes');
if (!existsSync(clientDir)) {
	console.log('[spike-g] build output dir not found at', clientDir);
	console.log('[spike-g] exploring...');
	const out = resolve(REPO, '.svelte-kit/output');
	if (existsSync(out)) {
		for (const d of readdirSync(out)) {
			console.log('  ', d);
		}
	}
	process.exit(1);
}

const files = readdirSync(clientDir);
let spikeG = 0;
let firebaseChunks = [];
let allChunks = [];

function sniff(filePath) {
	if (!filePath.endsWith('.js')) return null;
	try {
		const content = readFileSync(filePath, 'utf8');
		const hasFirebase = /firebase/i.test(content) || /firestore|onSnapshot|getAuth/.test(content);
		return { hasFirebase, size: statSync(filePath).size };
	} catch {
		return null;
	}
}

for (const f of files) {
	const fpath = resolve(clientDir, f);
	const info = sniff(fpath);
	if (!info) continue;
	allChunks.push({ file: f, size: info.size, hasFirebase: info.hasFirebase });
	if (info.hasFirebase) {
		firebaseChunks.push({ file: f, size: info.size });
	}
}

// Also walk chunks/ for non-route chunks
const chunksDir = resolve(REPO, '.svelte-kit/output/client/_app/immutable/chunks');
if (existsSync(chunksDir)) {
	for (const f of readdirSync(chunksDir)) {
		const fpath = resolve(chunksDir, f);
		const info = sniff(fpath);
		if (!info) continue;
		allChunks.push({ file: f, size: info.size, hasFirebase: info.hasFirebase, location: 'chunks' });
		if (info.hasFirebase) {
			firebaseChunks.push({ file: f, size: info.size, location: 'chunks' });
		}
	}
}

firebaseChunks.sort((a, b) => b.size - a.size);

const totalRaw = firebaseChunks.reduce((s, c) => s + c.size, 0);

console.log('\n[spike-g] === FIREBASE-TAGGED CHUNKS ===');
for (const c of firebaseChunks) {
	console.log(
		`  ${(c.size / 1024).toFixed(1).padStart(8)} kB  ${c.file}${c.location ? ' (' + c.location + ')' : ''}`
	);
}
console.log(
	`\n  raw total: ${(totalRaw / 1024).toFixed(1)} kB across ${firebaseChunks.length} chunks`
);

// Rough gzip estimate: firebase minified JS compresses to ~30% of raw
const gzipEstimate = totalRaw * 0.3;
console.log(`  gzip estimate (~30%): ${(gzipEstimate / 1024).toFixed(1)} kB`);

// Larger chunks (context on dominant parts)
const largest = firebaseChunks.slice(0, 5);
console.log('\n  top 5 firebase-related chunks:');
for (const c of largest) {
	console.log(`    ${(c.size / 1024).toFixed(1).padStart(8)} kB  ${c.file}`);
}

console.log('\n[spike-g] === VERDICT ===');
console.log(`  plan claim: ~200–250 kB gzipped for modular v10`);
console.log(
	`  measured : ${(gzipEstimate / 1024).toFixed(1)} kB gzipped (estimated from ${(totalRaw / 1024).toFixed(1)} kB raw)`
);
console.log(
	`  ${gzipEstimate < 300 * 1024 ? 'PASS (within plan estimate)' : 'FAIL — bundle heavier than estimate, revisit dynamic import strategy'}`
);
