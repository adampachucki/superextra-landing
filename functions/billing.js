import Stripe from 'stripe';
import { onRequest } from 'firebase-functions/v2/https';
import { defineSecret, defineString } from 'firebase-functions/params';
import { getAuth } from 'firebase-admin/auth';
import { getFirestore, FieldValue, Timestamp } from 'firebase-admin/firestore';

const stripeLiveSecretKey = defineSecret('STRIPE_LIVE_SECRET_KEY');
const stripeLiveWebhookSecret = defineSecret('STRIPE_LIVE_WEBHOOK_SECRET');
const stripeTestSecretKey = defineSecret('STRIPE_TEST_SECRET_KEY');
const stripeTestWebhookSecret = defineSecret('STRIPE_TEST_WEBHOOK_SECRET');
const billingTestAllowedEmails = defineString('BILLING_TEST_ALLOWED_EMAILS', { default: '' });

const PRICE_LOOKUP_KEY = 'superextra_unlimited_monthly';
const PAID_STATUSES = new Set(['active', 'trialing', 'past_due']);
const PORTAL_SUBSCRIPTION_STATUSES = new Set([
	'active',
	'trialing',
	'past_due',
	'unpaid',
	'paused',
	'incomplete'
]);
const CHECKOUT_ALLOWED_ORIGINS = new Set(['https://agent.superextra.ai', 'http://localhost:5199']);
const MARKET_TO_CURRENCY = {
	us: 'usd',
	pl: 'pln',
	de: 'eur',
	other: 'usd'
};

const LIVE_BILLING = Object.freeze({
	mode: 'live',
	secretKey: stripeLiveSecretKey,
	webhookSecret: stripeLiveWebhookSecret,
	billingField: 'billing',
	planField: 'plan',
	eventCollection: 'stripeEvents',
	requiresTestAccess: false
});

const TEST_BILLING = Object.freeze({
	mode: 'test',
	secretKey: stripeTestSecretKey,
	webhookSecret: stripeTestWebhookSecret,
	billingField: 'billingTest',
	planField: 'planTest',
	eventCollection: 'stripeTestEvents',
	requiresTestAccess: true
});

const stripeClients = new Map();
const cachedPriceIds = new Map();

function stripe(config) {
	let client = stripeClients.get(config.mode);
	if (!client) {
		client = new Stripe(config.secretKey.value());
		stripeClients.set(config.mode, client);
	}
	return client;
}

function db() {
	return getFirestore();
}

function resetStripeClientForTests() {
	stripeClients.clear();
	cachedPriceIds.clear();
}

function authError(res, status, error) {
	res.status(status).json({ ok: false, error });
}

async function requireUser(req, res) {
	const authHeader = req.headers.authorization || '';
	const tokenMatch = /^Bearer\s+(.+)$/i.exec(authHeader);
	if (!tokenMatch) {
		authError(res, 401, 'Authorization header required');
		return null;
	}
	try {
		const decoded = await getAuth().verifyIdToken(tokenMatch[1]);
		if (decoded?.firebase?.sign_in_provider === 'anonymous') {
			authError(res, 401, 'AUTH_REQUIRED');
			return null;
		}
		return {
			uid: decoded.uid,
			email: typeof decoded.email === 'string' ? decoded.email : null,
			emailVerified: decoded.email_verified === true,
			displayName: typeof decoded.name === 'string' ? decoded.name : null,
			photoURL: typeof decoded.picture === 'string' ? decoded.picture : null,
			billingTester: decoded.billingTester === true || decoded.admin === true
		};
	} catch (err) {
		console.warn('billing auth rejected:', err.code || err.message);
		authError(res, 401, 'Invalid auth token');
		return null;
	}
}

function requestBaseUrl(req) {
	const origin = typeof req.headers.origin === 'string' ? req.headers.origin : '';
	if (CHECKOUT_ALLOWED_ORIGINS.has(origin)) return origin;
	return 'https://agent.superextra.ai';
}

function normalizeMarket(value) {
	return Object.hasOwn(MARKET_TO_CURRENCY, value) ? value : 'other';
}

function billingModeLabel(config) {
	return config.mode === 'test' ? 'test' : 'live';
}

function emailPatternMatches(email, pattern) {
	if (pattern === '*') return true;
	if (pattern.startsWith('*@')) return email.endsWith(pattern.slice(1));
	return email === pattern;
}

function testBillingAllowedEmailPatterns() {
	return billingTestAllowedEmails
		.value()
		.split(/[\s,]+/)
		.map((value) => value.trim().toLowerCase())
		.filter(Boolean);
}

function userCanUseTestBilling(user) {
	if (user.billingTester) return true;
	if (!user.email || !user.emailVerified) return false;
	const email = user.email.toLowerCase();
	return testBillingAllowedEmailPatterns().some((pattern) => emailPatternMatches(email, pattern));
}

function requireBillingModeAccess(config, user, res) {
	if (!config.requiresTestAccess || userCanUseTestBilling(user)) return true;
	authError(res, 403, 'test_billing_forbidden');
	return false;
}

async function resolvePriceId(config) {
	const cachedPriceId = cachedPriceIds.get(config.mode);
	if (cachedPriceId) return cachedPriceId;
	const prices = await stripe(config).prices.list({
		active: true,
		lookup_keys: [PRICE_LOOKUP_KEY],
		limit: 1
	});
	const price = prices.data[0];
	if (!price) throw new Error('stripe_price_missing');
	cachedPriceIds.set(config.mode, price.id);
	return price.id;
}

function idOf(value) {
	if (!value) return null;
	if (typeof value === 'string') return value;
	if (typeof value === 'object' && typeof value.id === 'string') return value.id;
	return null;
}

function timestampFromSeconds(value) {
	return typeof value === 'number' && Number.isFinite(value)
		? Timestamp.fromMillis(value * 1000)
		: null;
}

function firstSubscriptionItem(subscription) {
	return Array.isArray(subscription?.items?.data) ? subscription.items.data[0] : null;
}

function subscriptionPeriodEnd(subscription) {
	return (
		subscription.current_period_end ??
		firstSubscriptionItem(subscription)?.current_period_end ??
		null
	);
}

function subscriptionPrice(subscription) {
	return firstSubscriptionItem(subscription)?.price ?? null;
}

function planForSubscriptionStatus(status) {
	return PAID_STATUSES.has(status) ? 'paid' : 'free';
}

function billingMapFromUserData(userData, config = LIVE_BILLING) {
	const value = userData[config.billingField];
	return value && typeof value === 'object' ? value : {};
}

function stripeCustomerIdFromBilling(billing) {
	return typeof billing.stripeCustomerId === 'string' ? billing.stripeCustomerId : null;
}

function checkoutShouldOpenPortal(billing) {
	const status = typeof billing.status === 'string' ? billing.status : null;
	const subscriptionId =
		typeof billing.stripeSubscriptionId === 'string' ? billing.stripeSubscriptionId : null;
	return Boolean(
		stripeCustomerIdFromBilling(billing) &&
		subscriptionId &&
		PORTAL_SUBSCRIPTION_STATUSES.has(status)
	);
}

function subscriptionBillingUpdate(subscription, extra = {}, config = LIVE_BILLING) {
	const price = subscriptionPrice(subscription);
	const status = subscription.status || 'incomplete';
	return {
		[config.planField]: planForSubscriptionStatus(status),
		[config.billingField]: {
			stripeCustomerId: idOf(subscription.customer),
			stripeSubscriptionId: subscription.id,
			status,
			mode: billingModeLabel(config),
			priceId: idOf(price),
			priceLookupKey: PRICE_LOOKUP_KEY,
			market: subscription.metadata?.market || extra.market || null,
			currency: subscription.currency || price?.currency || extra.currency || null,
			currentPeriodEnd: timestampFromSeconds(subscriptionPeriodEnd(subscription)),
			cancelAtPeriodEnd: Boolean(subscription.cancel_at_period_end),
			latestInvoiceId: idOf(subscription.latest_invoice) || extra.latestInvoiceId || null,
			updatedAt: FieldValue.serverTimestamp()
		}
	};
}

async function getOrCreateCustomer(user, config) {
	const userRef = db().collection('users').doc(user.uid);
	const snap = await userRef.get();
	const data = snap.exists ? snap.data() || {} : {};
	const billing = billingMapFromUserData(data, config);
	const existing = billing.stripeCustomerId;
	if (existing) return existing;

	const customer = await stripe(config).customers.create(
		{
			email: user.email || undefined,
			name: user.displayName || undefined,
			metadata: {
				firebaseUid: user.uid,
				app: 'superextra',
				stripeMode: billingModeLabel(config)
			}
		},
		{
			idempotencyKey: `superextra.${billingModeLabel(config)}.customer.${user.uid}`
		}
	);

	const baseUser = snap.exists
		? {}
		: {
				plan: 'free',
				planTest: 'free',
				limitOverrides: null,
				createdAt: FieldValue.serverTimestamp()
			};
	await userRef.set(
		{
			...baseUser,
			email: user.email,
			displayName: user.displayName,
			photoURL: user.photoURL,
			[config.billingField]: {
				stripeCustomerId: customer.id,
				status: billing.status || 'none',
				mode: billingModeLabel(config),
				updatedAt: FieldValue.serverTimestamp()
			},
			updatedAt: FieldValue.serverTimestamp()
		},
		{ merge: true }
	);
	return customer.id;
}

async function createPortalSessionUrl(customerId, baseUrl, config) {
	const session = await stripe(config).billingPortal.sessions.create({
		customer: customerId,
		return_url: `${baseUrl}/chat`
	});
	return session.url;
}

async function userRefForSubscription(subscription, config) {
	const metadataUid = subscription.metadata?.firebaseUid || subscription.metadata?.uid;
	if (metadataUid) return db().collection('users').doc(metadataUid);
	const customerId = idOf(subscription.customer);
	if (!customerId) return null;
	const snap = await db()
		.collection('users')
		.where(`${config.billingField}.stripeCustomerId`, '==', customerId)
		.limit(1)
		.get();
	return snap.empty ? null : snap.docs[0].ref;
}

async function recordStripeEvent(event, userRef, update, config) {
	const eventRef = db().collection(config.eventCollection).doc(event.id);
	await db().runTransaction(async (tx) => {
		const existing = await tx.get(eventRef);
		if (existing.exists) return;
		tx.create(eventRef, {
			type: event.type,
			mode: billingModeLabel(config),
			processedAt: FieldValue.serverTimestamp()
		});
		if (userRef && update) tx.set(userRef, update, { merge: true });
	});
}

async function retrieveSubscription(subscriptionId, config) {
	return stripe(config).subscriptions.retrieve(subscriptionId, {
		expand: ['items.data.price']
	});
}

async function handleCheckoutCompleted(event, config) {
	const session = event.data.object;
	const uid = session.metadata?.uid || session.client_reference_id;
	const subscriptionId = idOf(session.subscription);
	if (!uid || !subscriptionId) {
		await recordStripeEvent(event, null, null, config);
		return;
	}
	const subscription = await retrieveSubscription(subscriptionId, config);
	const userRef = db().collection('users').doc(uid);
	await recordStripeEvent(
		event,
		userRef,
		{
			...subscriptionBillingUpdate(
				subscription,
				{
					market: session.metadata?.market || null,
					latestInvoiceId: idOf(session.invoice)
				},
				config
			),
			[`${config.billingField}.checkoutSessionId`]: session.id
		},
		config
	);
}

async function handleSubscriptionEvent(event, config) {
	const subscription = event.data.object;
	const userRef = await userRefForSubscription(subscription, config);
	if (event.type === 'customer.subscription.deleted') {
		const update = subscriptionBillingUpdate(subscription, {}, config);
		await recordStripeEvent(
			event,
			userRef,
			{
				...update,
				[config.planField]: 'free',
				[config.billingField]: {
					...update[config.billingField],
					status: 'canceled',
					currentPeriodEnd: timestampFromSeconds(subscriptionPeriodEnd(subscription))
				}
			},
			config
		);
		return;
	}
	await recordStripeEvent(
		event,
		userRef,
		subscriptionBillingUpdate(subscription, {}, config),
		config
	);
}

async function handleInvoiceEvent(event, config) {
	const invoice = event.data.object;
	const subscriptionId = idOf(invoice.subscription);
	if (!subscriptionId) {
		await recordStripeEvent(event, null, null, config);
		return;
	}
	const subscription = await retrieveSubscription(subscriptionId, config);
	const userRef = await userRefForSubscription(subscription, config);
	const update = subscriptionBillingUpdate(subscription, { latestInvoiceId: invoice.id }, config);
	await recordStripeEvent(
		event,
		userRef,
		{
			...update,
			[config.billingField]: {
				...update[config.billingField],
				latestInvoiceId: invoice.id
			}
		},
		config
	);
}

function createCheckoutFunction(config) {
	return onRequest({ cors: true, secrets: [config.secretKey] }, async (req, res) => {
		if (req.method !== 'POST') {
			res.status(405).json({ ok: false, error: 'Method not allowed' });
			return;
		}
		const user = await requireUser(req, res);
		if (!user) return;
		if (!requireBillingModeAccess(config, user, res)) return;

		const market = normalizeMarket(req.body?.market);
		const currency = MARKET_TO_CURRENCY[market];
		const userRef = db().collection('users').doc(user.uid);
		const userSnap = await userRef.get();
		const userData = userSnap.exists ? userSnap.data() || {} : {};
		const billing = billingMapFromUserData(userData, config);
		if (checkoutShouldOpenPortal(billing)) {
			const customerId = stripeCustomerIdFromBilling(billing);
			try {
				const url = await createPortalSessionUrl(customerId, requestBaseUrl(req), config);
				res.json({ ok: true, url });
			} catch (err) {
				console.error('billingCheckout portal redirect failed:', err);
				res.status(500).json({ ok: false, error: 'portal_failed' });
			}
			return;
		}

		try {
			const [customerId, priceId] = await Promise.all([
				getOrCreateCustomer(user, config),
				resolvePriceId(config)
			]);
			const baseUrl = requestBaseUrl(req);
			const session = await stripe(config).checkout.sessions.create({
				mode: 'subscription',
				customer: customerId,
				client_reference_id: user.uid,
				line_items: [{ price: priceId, quantity: 1 }],
				currency,
				success_url: `${baseUrl}/chat?billing=success`,
				cancel_url: `${baseUrl}/chat?billing=cancelled`,
				automatic_tax: { enabled: true },
				tax_id_collection: { enabled: true },
				billing_address_collection: 'required',
				customer_update: { name: 'auto', address: 'auto' },
				metadata: {
					uid: user.uid,
					market,
					app: 'superextra',
					stripeMode: billingModeLabel(config)
				},
				subscription_data: {
					metadata: {
						firebaseUid: user.uid,
						market,
						app: 'superextra',
						stripeMode: billingModeLabel(config)
					}
				}
			});
			await userRef.set(
				{
					[config.billingField]: {
						stripeCustomerId: customerId,
						status: 'checkout_pending',
						mode: billingModeLabel(config),
						market,
						currency,
						priceLookupKey: PRICE_LOOKUP_KEY,
						updatedAt: FieldValue.serverTimestamp()
					}
				},
				{ merge: true }
			);
			res.json({ ok: true, url: session.url });
		} catch (err) {
			console.error('billingCheckout failed:', err);
			res.status(500).json({ ok: false, error: 'checkout_failed' });
		}
	});
}

function createPortalFunction(config) {
	return onRequest({ cors: true, secrets: [config.secretKey] }, async (req, res) => {
		if (req.method !== 'POST') {
			res.status(405).json({ ok: false, error: 'Method not allowed' });
			return;
		}
		const user = await requireUser(req, res);
		if (!user) return;
		if (!requireBillingModeAccess(config, user, res)) return;
		const snap = await db().collection('users').doc(user.uid).get();
		const billing = snap.exists ? billingMapFromUserData(snap.data() || {}, config) : {};
		if (!checkoutShouldOpenPortal(billing)) {
			const error = stripeCustomerIdFromBilling(billing)
				? 'stripe_subscription_missing'
				: 'stripe_customer_missing';
			res.status(404).json({ ok: false, error });
			return;
		}
		const customerId = stripeCustomerIdFromBilling(billing);
		try {
			const url = await createPortalSessionUrl(customerId, requestBaseUrl(req), config);
			res.json({ ok: true, url });
		} catch (err) {
			console.error('billingPortal failed:', err);
			res.status(500).json({ ok: false, error: 'portal_failed' });
		}
	});
}

function createWebhookFunction(config) {
	return onRequest({ secrets: [config.secretKey, config.webhookSecret] }, async (req, res) => {
		if (req.method !== 'POST') {
			res.status(405).send('Method not allowed');
			return;
		}
		const signature = req.headers['stripe-signature'];
		let event;
		try {
			event = stripe(config).webhooks.constructEvent(
				req.rawBody,
				signature,
				config.webhookSecret.value()
			);
		} catch (err) {
			console.warn('stripeWebhook signature rejected:', err.message);
			res.status(400).send('Webhook signature verification failed');
			return;
		}

		try {
			switch (event.type) {
				case 'checkout.session.completed':
					await handleCheckoutCompleted(event, config);
					break;
				case 'customer.subscription.updated':
				case 'customer.subscription.deleted':
					await handleSubscriptionEvent(event, config);
					break;
				case 'invoice.paid':
				case 'invoice.payment_failed':
					await handleInvoiceEvent(event, config);
					break;
				default:
					await recordStripeEvent(event, null, null, config);
			}
			res.json({ received: true });
		} catch (err) {
			console.error('stripeWebhook failed:', event.type, event.id, err);
			res.status(500).send('Webhook processing failed');
		}
	});
}

export const billingCheckout = createCheckoutFunction(LIVE_BILLING);
export const billingPortal = createPortalFunction(LIVE_BILLING);
export const stripeWebhook = createWebhookFunction(LIVE_BILLING);

export const billingCheckoutTest = createCheckoutFunction(TEST_BILLING);
export const billingPortalTest = createPortalFunction(TEST_BILLING);
export const stripeWebhookTest = createWebhookFunction(TEST_BILLING);

export const _billingTesting = {
	LIVE_BILLING,
	TEST_BILLING,
	normalizeMarket,
	planForSubscriptionStatus,
	checkoutShouldOpenPortal,
	subscriptionBillingUpdate,
	emailPatternMatches,
	userCanUseTestBilling,
	resetStripeClientForTests
};
