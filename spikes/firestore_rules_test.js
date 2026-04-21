// Spike F — Firestore rules emulator test starter.
//
// Run via:
//   cd spikes
//   npm install --save-dev @firebase/rules-unit-testing mocha chai@4
//   firebase emulators:exec --only firestore "npx mocha spikes/firestore_rules_test.js --timeout 10000"
//
// This is a STARTER file for Phase 1 implementation. Save as
// firestore.rules.spec.js in the repo root during Phase 1 and extend.

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

const RULES = `
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /sessions/{sid} {
      allow read: if request.auth != null
                  && request.auth.uid == resource.data.userId;
      allow write: if false;
    }

    // Collection-group match for events (see Spike D finding D.1)
    match /{path=**}/events/{eid} {
      allow read: if request.auth != null
                  && request.auth.uid == resource.data.userId;
      allow write: if false;
    }
  }
}
`;

let testEnv;

describe('Firestore rules for pipeline-decoupling plan', () => {
	before(async () => {
		testEnv = await initializeTestEnvironment({
			projectId: 'spike-rules-test',
			firestore: { rules: RULES }
		});
	});

	beforeEach(async () => await testEnv.clearFirestore());

	after(async () => await testEnv.cleanup());

	async function seedSession(uid, sid) {
		await testEnv.withSecurityRulesDisabled(async (ctx) => {
			const db = ctx.firestore();
			await setDoc(doc(db, 'sessions', sid), {
				userId: uid,
				createdAt: Date.now(),
				queuedAt: Date.now(),
				status: 'running',
				currentRunId: 'run-1',
				currentAttempt: 1
			});
			// Seed 5 events in the subcollection
			for (let i = 1; i <= 5; i++) {
				await addDoc(collection(db, 'sessions', sid, 'events'), {
					userId: uid,
					runId: 'run-1',
					attempt: 1,
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

		it('owner cannot write (server-only)', async () => {
			await seedSession('alice', 'sid-alice');
			const db = testEnv.authenticatedContext('alice').firestore();
			await assertFails(updateDoc(doc(db, 'sessions', 'sid-alice'), { status: 'complete' }));
		});
	});

	describe('events collection-group', () => {
		it('owner can run collection-group query for their own runId', async () => {
			await seedSession('alice', 'sid-alice');
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

		it('non-owner query returns no results (filtered by userId + rule)', async () => {
			await seedSession('alice', 'sid-alice');
			const db = testEnv.authenticatedContext('bob').firestore();
			// Bob queries for his own userId — returns empty, which is fine.
			const q = query(
				collectionGroup(db, 'events'),
				where('userId', '==', 'bob'),
				where('runId', '==', 'run-1')
			);
			const snap = await assertSucceeds(getDocs(q));
			expect(snap.size).to.equal(0);
		});

		it('non-owner query attempting to read others events is denied', async () => {
			await seedSession('alice', 'sid-alice');
			const db = testEnv.authenticatedContext('bob').firestore();
			// Bob tries to query alice's events — rule denies because resource.data.userId != bob
			const q = query(
				collectionGroup(db, 'events'),
				where('userId', '==', 'alice'),
				where('runId', '==', 'run-1')
			);
			await assertFails(getDocs(q));
		});

		it('owner cannot write events', async () => {
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
