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
	addDoc,
	updateDoc,
	deleteDoc
} from 'firebase/firestore';
import { expect } from 'chai';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const RULES = readFileSync(join(__dirname, 'firestore.rules'), 'utf8');

let testEnv;

describe('firestore.rules (capability-URL model)', function () {
	this.timeout(10_000);

	before(async () => {
		testEnv = await initializeTestEnvironment({
			projectId: 'superextra-rules-test',
			firestore: { rules: RULES }
		});
	});

	beforeEach(async () => await testEnv.clearFirestore());

	after(async () => await testEnv.cleanup());

	async function seedSession(creatorUid, sid, { participants, nTurns = 2, nEvents = 3 } = {}) {
		const actualParticipants = participants ?? [creatorUid];
		await testEnv.withSecurityRulesDisabled(async (ctx) => {
			const db = ctx.firestore();
			await setDoc(doc(db, 'sessions', sid), {
				userId: creatorUid,
				participants: actualParticipants,
				title: 'Test',
				status: 'complete',
				lastTurnIndex: nTurns,
				createdAt: Date.now(),
				updatedAt: Date.now()
			});
			for (let i = 1; i <= nTurns; i++) {
				const idx = String(i).padStart(4, '0');
				await setDoc(doc(db, 'sessions', sid, 'turns', idx), {
					turnIndex: i,
					runId: `run-${i}`,
					userMessage: `msg ${i}`,
					status: 'complete',
					reply: `reply ${i}`,
					createdAt: Date.now()
				});
			}
			for (let i = 1; i <= nEvents; i++) {
				await addDoc(collection(db, 'sessions', sid, 'events'), {
					userId: creatorUid,
					runId: 'run-1',
					attempt: 1,
					seqInAttempt: i,
					type: 'timeline',
					ts: Date.now()
				});
			}
		});
	}

	// --- Claim: `get` on a session is open to any signed-in visitor ---
	describe('GET on /sessions/{sid}', () => {
		it('creator can GET', async () => {
			await seedSession('alice', 's1');
			const db = testEnv.authenticatedContext('alice').firestore();
			await assertSucceeds(getDoc(doc(db, 'sessions', 's1')));
		});

		it('non-participant signed-in visitor can GET (capability URL)', async () => {
			await seedSession('alice', 's1', { participants: ['alice'] });
			const db = testEnv.authenticatedContext('bob').firestore();
			await assertSucceeds(getDoc(doc(db, 'sessions', 's1')));
		});

		it('unauthenticated cannot GET', async () => {
			await seedSession('alice', 's1');
			const db = testEnv.unauthenticatedContext().firestore();
			await assertFails(getDoc(doc(db, 'sessions', 's1')));
		});
	});

	// --- Claim: `list` is participant-scoped ---
	describe('LIST on /sessions', () => {
		it('participant can list their chats with array-contains', async () => {
			await seedSession('alice', 's1', { participants: ['alice'] });
			await seedSession('alice', 's2', { participants: ['alice', 'bob'] });
			await seedSession('charlie', 's3', { participants: ['charlie'] });
			const db = testEnv.authenticatedContext('alice').firestore();
			const q = query(
				collection(db, 'sessions'),
				where('participants', 'array-contains', 'alice'),
				orderBy('updatedAt', 'desc')
			);
			const snap = await assertSucceeds(getDocs(q));
			expect(snap.size).to.equal(2);
		});

		it('list WITHOUT array-contains is denied (query must align with rule)', async () => {
			await seedSession('alice', 's1', { participants: ['alice'] });
			const db = testEnv.authenticatedContext('alice').firestore();
			const q = query(collection(db, 'sessions'));
			await assertFails(getDocs(q));
		});

		it('list with array-contains for OTHER uid returns empty (not denied)', async () => {
			await seedSession('alice', 's1', { participants: ['alice'] });
			const db = testEnv.authenticatedContext('bob').firestore();
			const q = query(
				collection(db, 'sessions'),
				where('participants', 'array-contains', 'bob'),
				orderBy('updatedAt', 'desc')
			);
			const snap = await assertSucceeds(getDocs(q));
			expect(snap.size).to.equal(0);
		});

		it('list with array-contains for another uid is denied', async () => {
			await seedSession('alice', 's1', { participants: ['alice'] });
			const db = testEnv.authenticatedContext('bob').firestore();
			const q = query(collection(db, 'sessions'), where('participants', 'array-contains', 'alice'));
			await assertFails(getDocs(q));
		});

		it('participant who contributed to shared chat can list it', async () => {
			await seedSession('alice', 's1', { participants: ['alice', 'bob'] });
			const db = testEnv.authenticatedContext('bob').firestore();
			const q = query(
				collection(db, 'sessions'),
				where('participants', 'array-contains', 'bob'),
				orderBy('updatedAt', 'desc')
			);
			const snap = await assertSucceeds(getDocs(q));
			expect(snap.size).to.equal(1);
		});
	});

	// --- Claim: turns subcollection is open signed-in read, no writes ---
	describe('turns subcollection', () => {
		it('any signed-in visitor can get a turn by path', async () => {
			await seedSession('alice', 's1', { participants: ['alice'], nTurns: 3 });
			const db = testEnv.authenticatedContext('bob').firestore();
			await assertSucceeds(getDoc(doc(db, 'sessions', 's1', 'turns', '0001')));
		});

		it('any signed-in visitor can list all turns in a session', async () => {
			await seedSession('alice', 's1', { participants: ['alice'], nTurns: 3 });
			const db = testEnv.authenticatedContext('bob').firestore();
			const q = query(collection(db, 'sessions', 's1', 'turns'), orderBy('turnIndex'));
			const snap = await assertSucceeds(getDocs(q));
			expect(snap.size).to.equal(3);
		});

		it('unauthenticated cannot read turns', async () => {
			await seedSession('alice', 's1', { participants: ['alice'] });
			const db = testEnv.unauthenticatedContext().firestore();
			await assertFails(getDoc(doc(db, 'sessions', 's1', 'turns', '0001')));
		});

		it('writes to turns are denied for all clients', async () => {
			await seedSession('alice', 's1', { participants: ['alice'] });
			const db = testEnv.authenticatedContext('alice').firestore();
			await assertFails(
				setDoc(doc(db, 'sessions', 's1', 'turns', '9999'), {
					turnIndex: 9999,
					runId: 'evil',
					userMessage: 'evil'
				})
			);
			await assertFails(
				updateDoc(doc(db, 'sessions', 's1', 'turns', '0001'), { reply: 'tampered' })
			);
			await assertFails(deleteDoc(doc(db, 'sessions', 's1', 'turns', '0001')));
		});
	});

	// --- Claim: events subcollection is open signed-in read, no writes ---
	describe('events subcollection', () => {
		it('any signed-in visitor can get an event by path', async () => {
			await seedSession('alice', 's1', { participants: ['alice'] });
			await testEnv.withSecurityRulesDisabled(async (ctx) => {
				await setDoc(doc(ctx.firestore(), 'sessions', 's1', 'events', 'e1'), {
					userId: 'alice',
					runId: 'run-1',
					type: 'timeline',
					ts: Date.now()
				});
			});
			const db = testEnv.authenticatedContext('bob').firestore();
			await assertSucceeds(getDoc(doc(db, 'sessions', 's1', 'events', 'e1')));
		});

		it('any signed-in visitor can list + filter events of a session', async () => {
			await seedSession('alice', 's1', { participants: ['alice'] });
			const db = testEnv.authenticatedContext('bob').firestore();
			const q = query(
				collection(db, 'sessions', 's1', 'events'),
				where('runId', '==', 'run-1'),
				orderBy('attempt'),
				orderBy('seqInAttempt')
			);
			const snap = await assertSucceeds(getDocs(q));
			expect(snap.size).to.be.at.least(1);
		});

		it('writes to events are denied for all clients', async () => {
			await seedSession('alice', 's1', { participants: ['alice'] });
			const db = testEnv.authenticatedContext('alice').firestore();
			await assertFails(
				addDoc(collection(db, 'sessions', 's1', 'events'), {
					userId: 'alice',
					runId: 'run-1',
					type: 'timeline'
				})
			);
		});
	});

	// --- Claim: session doc writes are server-only even for creator ---
	describe('session doc writes', () => {
		it('creator cannot write session doc', async () => {
			await seedSession('alice', 's1', { participants: ['alice'] });
			const db = testEnv.authenticatedContext('alice').firestore();
			await assertFails(updateDoc(doc(db, 'sessions', 's1'), { title: 'hacked' }));
		});

		it('non-creator cannot write session doc', async () => {
			await seedSession('alice', 's1', { participants: ['alice', 'bob'] });
			const db = testEnv.authenticatedContext('bob').firestore();
			await assertFails(updateDoc(doc(db, 'sessions', 's1'), { title: 'hacked' }));
		});

		it('nobody can create a session doc from the client', async () => {
			const db = testEnv.authenticatedContext('alice').firestore();
			await assertFails(
				setDoc(doc(db, 'sessions', 'fresh'), {
					userId: 'alice',
					participants: ['alice']
				})
			);
		});

		it('nobody can delete a session doc from the client', async () => {
			await seedSession('alice', 's1', { participants: ['alice'] });
			const db = testEnv.authenticatedContext('alice').firestore();
			await assertFails(deleteDoc(doc(db, 'sessions', 's1')));
		});
	});

	// --- Edge cases that matter for the plan ---
	describe('edge cases', () => {
		it('GET on a session with empty participants array still allowed to signed-in visitor', async () => {
			await seedSession('alice', 's-empty', { participants: [] });
			const db = testEnv.authenticatedContext('bob').firestore();
			await assertSucceeds(getDoc(doc(db, 'sessions', 's-empty')));
		});

		it('GET on a nonexistent session returns exists()=false, not permission-denied', async () => {
			const db = testEnv.authenticatedContext('alice').firestore();
			// Under the proposed `allow get: if request.auth != null` rule, a GET on
			// a nonexistent doc should succeed with `exists()=false`. This is the
			// shift from Appendix C Test 1 (creator-only rules return
			// permission-denied) to the plan's clean missing-doc read.
			const snap = await assertSucceeds(getDoc(doc(db, 'sessions', 'nonexistent')));
			expect(snap.exists()).to.equal(false);
		});

		it('sidebar query with array-contains but without orderBy still works', async () => {
			await seedSession('alice', 's1', { participants: ['alice'] });
			const db = testEnv.authenticatedContext('alice').firestore();
			const q = query(collection(db, 'sessions'), where('participants', 'array-contains', 'alice'));
			const snap = await assertSucceeds(getDocs(q));
			expect(snap.size).to.equal(1);
		});
	});
});
