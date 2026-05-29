#!/usr/bin/env node
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import { createRequire } from 'node:module';

const require = createRequire(new URL('../functions/package.json', import.meta.url));
const admin = require('firebase-admin');
const Stripe = require('stripe');

const PROJECT_ID = process.env.PROJECT_ID || 'superextra-site';
const BASE_URL = process.env.BASE_URL || 'https://agent.superextra.ai';

function readLiveStripeKey() {
	return execFileSync(
		'gcloud',
		[
			'secrets',
			'versions',
			'access',
			'latest',
			'--secret=STRIPE_LIVE_SECRET_KEY',
			`--project=${PROJECT_ID}`
		],
		{ encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'] }
	).trim();
}

function readTestStripeKey() {
	if (process.env.STRIPE_TEST_SECRET_KEY) return process.env.STRIPE_TEST_SECRET_KEY;
	const configPath = `${os.homedir()}/.config/stripe/config.toml`;
	const config = fs.readFileSync(configPath, 'utf8');
	const match = config.match(/sk_test_[A-Za-z0-9_]+/);
	if (!match) throw new Error(`Stripe test key not found in ${configPath}`);
	return match[0];
}

async function firebaseWebApiKey() {
	const response = await fetch(`${BASE_URL}/__/firebase/init.json`);
	if (!response.ok) throw new Error(`Firebase init failed: ${response.status}`);
	const config = await response.json();
	if (!config.apiKey) throw new Error('Firebase init response did not include apiKey');
	return config.apiKey;
}

async function idTokenFor(uid) {
	const token = await admin.auth().createCustomToken(uid, { billingTester: true });
	const apiKey = await firebaseWebApiKey();
	const response = await fetch(
		`https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=${apiKey}`,
		{
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ token, returnSecureToken: true })
		}
	);
	const payload = await response.json();
	if (!response.ok || !payload.idToken) {
		throw new Error(`Custom token exchange failed: ${response.status} ${JSON.stringify(payload)}`);
	}
	return payload.idToken;
}

async function postBilling(path, idToken, body = {}) {
	const response = await fetch(`${BASE_URL}${path}`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${idToken}`
		},
		body: JSON.stringify(body)
	});
	const payload = await response.json().catch(() => null);
	if (!response.ok || !payload?.url) {
		throw new Error(`${path} failed: ${response.status} ${JSON.stringify(payload)}`);
	}
	return payload.url;
}

async function expectBillingError(path, idToken, expectedError) {
	const response = await fetch(`${BASE_URL}${path}`, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${idToken}`
		},
		body: '{}'
	});
	const payload = await response.json().catch(() => null);
	if (response.ok || payload?.error !== expectedError) {
		throw new Error(
			`${path} expected ${expectedError}: ${response.status} ${JSON.stringify(payload)}`
		);
	}
}

function checkoutSessionIdFromUrl(url) {
	const parsed = new URL(url);
	const queryId = parsed.searchParams.get('session_id');
	if (queryId) return queryId;
	const pathMatch = parsed.pathname.match(/\/(cs_(test|live)_[^/?#]+)/);
	return pathMatch?.[1] ?? null;
}

async function checkoutSmoke({ mode, market, stripe, idToken, returnPath }) {
	const prefix = mode === 'test' ? '/api/billing/test' : '/api/billing';
	const checkoutUrl = await postBilling(`${prefix}/checkout`, idToken, { market, returnPath });
	const sessionId = checkoutSessionIdFromUrl(checkoutUrl);
	if (!sessionId) throw new Error(`${mode} Checkout URL did not include session_id`);
	const session = await stripe.checkout.sessions.retrieve(sessionId);
	const lineItems = await stripe.checkout.sessions.listLineItems(sessionId, {
		limit: 1,
		expand: ['data.price.product']
	});
	const product = lineItems.data[0]?.price?.product;
	const customerId = typeof session.customer === 'string' ? session.customer : session.customer?.id;
	const customer = customerId ? await stripe.customers.retrieve(customerId) : null;
	await expectBillingError(`${prefix}/portal`, idToken, 'stripe_subscription_missing');
	return {
		sessionId: session.id,
		customerId,
		customerCountry: customer && !customer.deleted ? customer.address?.country : null,
		livemode: session.livemode,
		mode: session.mode,
		currency: session.currency,
		amountTotal: session.amount_total,
		productName: typeof product === 'object' && product ? product.name : null,
		successUrl: session.success_url,
		cancelUrl: session.cancel_url,
		portal: 'blocked_until_subscription'
	};
}

async function main() {
	if (!admin.apps.length) admin.initializeApp({ projectId: PROJECT_ID });

	const liveStripe = new Stripe(readLiveStripeKey());
	const testStripe = new Stripe(readTestStripeKey());
	const uid = `codex-billing-mode-smoke-${Date.now()}`;
	const email = `${uid}@superextra.ai`;
	const auth = admin.auth();
	const db = admin.firestore();
	let liveCustomerId = null;
	let testCustomerId = null;

	try {
		await auth.createUser({ uid, email, emailVerified: true });
		const idToken = await idTokenFor(uid);

		const test = await checkoutSmoke({
			mode: 'test',
			market: 'de',
			stripe: testStripe,
			idToken,
			returnPath: '/chat?sid=smoke-test&billing=success&session_id=old'
		});
		testCustomerId = test.customerId;

		const live = await checkoutSmoke({
			mode: 'live',
			market: 'pl',
			stripe: liveStripe,
			idToken,
			returnPath: '/chat?sid=smoke-live'
		});
		liveCustomerId = live.customerId;

		if (test.livemode !== false || test.currency !== 'eur' || test.amountTotal !== 900) {
			throw new Error(`Unexpected test checkout session: ${JSON.stringify(test)}`);
		}
		if (live.livemode !== true || live.currency !== 'pln' || live.amountTotal !== 1900) {
			throw new Error(`Unexpected live checkout session: ${JSON.stringify(live)}`);
		}
		if (test.productName !== 'Superextra Pro') {
			throw new Error(`Unexpected test product name: ${JSON.stringify(test)}`);
		}
		if (live.productName !== 'Superextra Pro') {
			throw new Error(`Unexpected live product name: ${JSON.stringify(live)}`);
		}
		if (test.customerCountry !== 'DE') {
			throw new Error(`Unexpected test customer country: ${JSON.stringify(test)}`);
		}
		if (live.customerCountry !== 'PL') {
			throw new Error(`Unexpected live customer country: ${JSON.stringify(live)}`);
		}
		if (
			test.successUrl !==
			`${BASE_URL}/chat?sid=smoke-test&billingMode=test&billing=success&session_id={CHECKOUT_SESSION_ID}`
		) {
			throw new Error(`Unexpected test success URL: ${test.successUrl}`);
		}
		if (
			live.successUrl !==
			`${BASE_URL}/chat?sid=smoke-live&billing=success&session_id={CHECKOUT_SESSION_ID}`
		) {
			throw new Error(`Unexpected live success URL: ${live.successUrl}`);
		}

		process.stdout.write(`${JSON.stringify({ ok: true, uid, test, live }, null, 2)}\n`);
	} finally {
		await Promise.allSettled([
			liveCustomerId ? liveStripe.customers.del(liveCustomerId) : null,
			testCustomerId ? testStripe.customers.del(testCustomerId) : null,
			db.collection('users').doc(uid).delete(),
			auth.deleteUser(uid)
		]);
	}
}

main().catch((err) => {
	console.error(err);
	process.exitCode = 1;
});
