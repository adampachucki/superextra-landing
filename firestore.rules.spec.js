// Firestore rules emulator test suite.
//
// Run:  npm run test:rules
// (wrapper runs `firebase emulators:exec --only firestore "mocha firestore.rules.spec.js"`)
//
// Rules source: firestore.rules — the test loads that file directly so the spec
// stays aligned with what's deployed.

import {
	initializeTestEnvironment,
	assertFails,
	assertSucceeds
} from '@firebase/rules-unit-testing';
import {
	doc,
	getDoc,
	setDoc,
	collection,
	getDocs,
	query,
	where,
	orderBy,
	collectionGroup,
	addDoc,
	updateDoc
} from 'firebase/firestore';
import { expect } from 'chai';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const RULES = readFileSync(join(__dirname, 'firestore.rules'), 'utf8');

let testEnv;

describe('firestore.rules', function () {
	this.timeout(10_000);

	before(async () => {
		testEnv = await initializeTestEnvironment({
			projectId: 'superextra-rules-test',
			firestore: { rules: RULES }
		});
	});

	beforeEach(async () => await testEnv.clearFirestore());

	after(async () => await testEnv.cleanup());

	async function seedSession(uid, sid, { runId = 'run-1', attempt = 1, nEvents = 5 } = {}) {
		await testEnv.withSecurityRulesDisabled(async (ctx) => {
			const db = ctx.firestore();
			await setDoc(doc(db, 'sessions', sid), {
				userId: uid,
				createdAt: Date.now(),
				queuedAt: Date.now(),
				status: 'running',
				currentRunId: runId,
				currentAttempt: attempt
			});
			for (let i = 1; i <= nEvents; i++) {
				await addDoc(collection(db, 'sessions', sid, 'events'), {
					userId: uid,
					runId,
					attempt,
					seqInAttempt: i,
					type: 'progress',
					ts: Date.now()
				});
			}
		});
	}

	describe('sessions/{sid}', () => {
		it('owner can read their own session', async () => {
			await seedSession('alice', 'sid-alice');
			const db = testEnv.authenticatedContext('alice').firestore();
			await assertSucceeds(getDoc(doc(db, 'sessions', 'sid-alice')));
		});

		it('non-owner cannot read', async () => {
			await seedSession('alice', 'sid-alice');
			const db = testEnv.authenticatedContext('bob').firestore();
			await assertFails(getDoc(doc(db, 'sessions', 'sid-alice')));
		});

		it('unauthenticated cannot read', async () => {
			await seedSession('alice', 'sid-alice');
			const db = testEnv.unauthenticatedContext().firestore();
			await assertFails(getDoc(doc(db, 'sessions', 'sid-alice')));
		});

		it('owner cannot write (server-only model)', async () => {
			await seedSession('alice', 'sid-alice');
			const db = testEnv.authenticatedContext('alice').firestore();
			await assertFails(updateDoc(doc(db, 'sessions', 'sid-alice'), { status: 'complete' }));
		});

		it('owner cannot create a new session doc', async () => {
			const db = testEnv.authenticatedContext('alice').firestore();
			await assertFails(
				setDoc(doc(db, 'sessions', 'sid-new'), {
					userId: 'alice',
					createdAt: Date.now()
				})
			);
		});
	});

	describe('events collection-group', () => {
		it('owner can run collection-group query for their runId', async () => {
			await seedSession('alice', 'sid-alice', { nEvents: 5 });
			const db = testEnv.authenticatedContext('alice').firestore();
			const q = query(
				collectionGroup(db, 'events'),
				where('userId', '==', 'alice'),
				where('runId', '==', 'run-1'),
				orderBy('attempt'),
				orderBy('seqInAttempt')
			);
			const snap = await assertSucceeds(getDocs(q));
			expect(snap.size).to.equal(5);
		});

		it('non-owner querying their own userId returns empty (no data for them)', async () => {
			await seedSession('alice', 'sid-alice');
			const db = testEnv.authenticatedContext('bob').firestore();
			const q = query(
				collectionGroup(db, 'events'),
				where('userId', '==', 'bob'),
				where('runId', '==', 'run-1')
			);
			const snap = await assertSucceeds(getDocs(q));
			expect(snap.size).to.equal(0);
		});

		it("non-owner querying another's userId is denied", async () => {
			await seedSession('alice', 'sid-alice');
			const db = testEnv.authenticatedContext('bob').firestore();
			const q = query(
				collectionGroup(db, 'events'),
				where('userId', '==', 'alice'),
				where('runId', '==', 'run-1')
			);
			await assertFails(getDocs(q));
		});

		it('unauthenticated collection-group query is denied', async () => {
			await seedSession('alice', 'sid-alice');
			const db = testEnv.unauthenticatedContext().firestore();
			const q = query(
				collectionGroup(db, 'events'),
				where('userId', '==', 'alice'),
				where('runId', '==', 'run-1')
			);
			await assertFails(getDocs(q));
		});

		it('owner cannot write events (server-only)', async () => {
			await seedSession('alice', 'sid-alice');
			const db = testEnv.authenticatedContext('alice').firestore();
			await assertFails(
				addDoc(collection(db, 'sessions', 'sid-alice', 'events'), {
					userId: 'alice',
					runId: 'run-1',
					attempt: 1,
					seqInAttempt: 99
				})
			);
		});
	});
});
