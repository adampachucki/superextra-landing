import Stripe from 'stripe';
import { onRequest } from 'firebase-functions/v2/https';
import { defineSecret } from 'firebase-functions/params';
import { getAuth } from 'firebase-admin/auth';
import { getFirestore, FieldValue, Timestamp } from 'firebase-admin/firestore';

const stripeSecretKey = defineSecret('STRIPE_SECRET_KEY');
const stripeWebhookSecret = defineSecret('STRIPE_WEBHOOK_SECRET');

const PRICE_LOOKUP_KEY = 'superextra_unlimited_monthly';
const PAID_STATUSES = new Set(['active', 'trialing', 'past_due']);
const TERMINAL_SUBSCRIPTION_STATUSES = new Set(['canceled', 'incomplete_expired']);
const CHECKOUT_ALLOWED_ORIGINS = new Set(['https://agent.superextra.ai', 'http://localhost:5199']);
const MARKET_TO_CURRENCY = {
	us: 'usd',
	pl: 'pln',
	de: 'eur',
	other: 'usd'
};

let stripeClient = null;
let cachedPriceId = null;

function stripe() {
	if (!stripeClient) {
		stripeClient = new Stripe(stripeSecretKey.value());
	}
	return stripeClient;
}

function db() {
	return getFirestore();
}

function resetStripeClientForTests() {
	stripeClient = null;
	cachedPriceId = null;
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
			displayName: typeof decoded.name === 'string' ? decoded.name : null,
			photoURL: typeof decoded.picture === 'string' ? decoded.picture : null
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

async function resolvePriceId() {
	if (cachedPriceId) return cachedPriceId;
	const prices = await stripe().prices.list({
		active: true,
		lookup_keys: [PRICE_LOOKUP_KEY],
		limit: 1
	});
	const price = prices.data[0];
	if (!price) throw new Error('stripe_price_missing');
	cachedPriceId = price.id;
	return cachedPriceId;
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

function billingMapFromUserData(userData) {
	return userData.billing && typeof userData.billing === 'object' ? userData.billing : {};
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
		(PAID_STATUSES.has(status) || (subscriptionId && !TERMINAL_SUBSCRIPTION_STATUSES.has(status)))
	);
}

function subscriptionBillingUpdate(subscription, extra = {}) {
	const price = subscriptionPrice(subscription);
	const status = subscription.status || 'incomplete';
	return {
		plan: planForSubscriptionStatus(status),
		billing: {
			stripeCustomerId: idOf(subscription.customer),
			stripeSubscriptionId: subscription.id,
			status,
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

async function getOrCreateCustomer(user) {
	const userRef = db().collection('users').doc(user.uid);
	const snap = await userRef.get();
	const data = snap.exists ? snap.data() || {} : {};
	const existing = data.billing?.stripeCustomerId;
	if (existing) return existing;

	const customer = await stripe().customers.create(
		{
			email: user.email || undefined,
			name: user.displayName || undefined,
			metadata: {
				firebaseUid: user.uid,
				app: 'superextra'
			}
		},
		{
			idempotencyKey: `superextra.customer.${user.uid}`
		}
	);

	const baseUser = snap.exists
		? {}
		: {
				plan: 'free',
				limitOverrides: null,
				createdAt: FieldValue.serverTimestamp()
			};
	await userRef.set(
		{
			...baseUser,
			email: user.email,
			displayName: user.displayName,
			photoURL: user.photoURL,
			billing: {
				stripeCustomerId: customer.id,
				status: data.billing?.status || 'none',
				updatedAt: FieldValue.serverTimestamp()
			},
			updatedAt: FieldValue.serverTimestamp()
		},
		{ merge: true }
	);
	return customer.id;
}

async function createPortalSessionUrl(customerId, baseUrl) {
	const session = await stripe().billingPortal.sessions.create({
		customer: customerId,
		return_url: `${baseUrl}/chat`
	});
	return session.url;
}

async function userRefForSubscription(subscription) {
	const metadataUid = subscription.metadata?.firebaseUid || subscription.metadata?.uid;
	if (metadataUid) return db().collection('users').doc(metadataUid);
	const customerId = idOf(subscription.customer);
	if (!customerId) return null;
	const snap = await db()
		.collection('users')
		.where('billing.stripeCustomerId', '==', customerId)
		.limit(1)
		.get();
	return snap.empty ? null : snap.docs[0].ref;
}

async function recordStripeEvent(event, userRef, update) {
	const eventRef = db().collection('stripeEvents').doc(event.id);
	await db().runTransaction(async (tx) => {
		const existing = await tx.get(eventRef);
		if (existing.exists) return;
		tx.create(eventRef, {
			type: event.type,
			processedAt: FieldValue.serverTimestamp()
		});
		if (userRef && update) tx.set(userRef, update, { merge: true });
	});
}

async function retrieveSubscription(subscriptionId) {
	return stripe().subscriptions.retrieve(subscriptionId, {
		expand: ['items.data.price']
	});
}

async function handleCheckoutCompleted(event) {
	const session = event.data.object;
	const uid = session.metadata?.uid || session.client_reference_id;
	const subscriptionId = idOf(session.subscription);
	if (!uid || !subscriptionId) {
		await recordStripeEvent(event, null, null);
		return;
	}
	const subscription = await retrieveSubscription(subscriptionId);
	const userRef = db().collection('users').doc(uid);
	await recordStripeEvent(event, userRef, {
		...subscriptionBillingUpdate(subscription, {
			market: session.metadata?.market || null,
			latestInvoiceId: idOf(session.invoice)
		}),
		'billing.checkoutSessionId': session.id
	});
}

async function handleSubscriptionEvent(event) {
	const subscription = event.data.object;
	const userRef = await userRefForSubscription(subscription);
	if (event.type === 'customer.subscription.deleted') {
		const update = subscriptionBillingUpdate(subscription);
		await recordStripeEvent(event, userRef, {
			...update,
			plan: 'free',
			billing: {
				...update.billing,
				status: 'canceled',
				currentPeriodEnd: timestampFromSeconds(subscriptionPeriodEnd(subscription))
			}
		});
		return;
	}
	await recordStripeEvent(event, userRef, subscriptionBillingUpdate(subscription));
}

async function handleInvoiceEvent(event) {
	const invoice = event.data.object;
	const subscriptionId = idOf(invoice.subscription);
	if (!subscriptionId) {
		await recordStripeEvent(event, null, null);
		return;
	}
	const subscription = await retrieveSubscription(subscriptionId);
	const userRef = await userRefForSubscription(subscription);
	const update = subscriptionBillingUpdate(subscription, { latestInvoiceId: invoice.id });
	await recordStripeEvent(event, userRef, {
		...update,
		billing: {
			...update.billing,
			latestInvoiceId: invoice.id
		}
	});
}

export const billingCheckout = onRequest(
	{ cors: true, secrets: [stripeSecretKey] },
	async (req, res) => {
		if (req.method !== 'POST') {
			res.status(405).json({ ok: false, error: 'Method not allowed' });
			return;
		}
		const user = await requireUser(req, res);
		if (!user) return;

		const market = normalizeMarket(req.body?.market);
		const currency = MARKET_TO_CURRENCY[market];
		const userRef = db().collection('users').doc(user.uid);
		const userSnap = await userRef.get();
		const userData = userSnap.exists ? userSnap.data() || {} : {};
		const billing = billingMapFromUserData(userData);
		if (checkoutShouldOpenPortal(billing)) {
			const customerId = stripeCustomerIdFromBilling(billing);
			try {
				const url = await createPortalSessionUrl(customerId, requestBaseUrl(req));
				res.json({ ok: true, url });
			} catch (err) {
				console.error('billingCheckout portal redirect failed:', err);
				res.status(500).json({ ok: false, error: 'portal_failed' });
			}
			return;
		}

		try {
			const [customerId, priceId] = await Promise.all([
				getOrCreateCustomer(user),
				resolvePriceId()
			]);
			const baseUrl = requestBaseUrl(req);
			const session = await stripe().checkout.sessions.create({
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
				metadata: { uid: user.uid, market, app: 'superextra' },
				subscription_data: {
					metadata: { firebaseUid: user.uid, market, app: 'superextra' }
				}
			});
			await userRef.set(
				{
					billing: {
						stripeCustomerId: customerId,
						status: 'checkout_pending',
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
	}
);

export const billingPortal = onRequest(
	{ cors: true, secrets: [stripeSecretKey] },
	async (req, res) => {
		if (req.method !== 'POST') {
			res.status(405).json({ ok: false, error: 'Method not allowed' });
			return;
		}
		const user = await requireUser(req, res);
		if (!user) return;
		const snap = await db().collection('users').doc(user.uid).get();
		const customerId = snap.exists ? snap.data()?.billing?.stripeCustomerId : null;
		if (!customerId) {
			res.status(404).json({ ok: false, error: 'stripe_customer_missing' });
			return;
		}
		try {
			const url = await createPortalSessionUrl(customerId, requestBaseUrl(req));
			res.json({ ok: true, url });
		} catch (err) {
			console.error('billingPortal failed:', err);
			res.status(500).json({ ok: false, error: 'portal_failed' });
		}
	}
);

export const stripeWebhook = onRequest(
	{ secrets: [stripeSecretKey, stripeWebhookSecret] },
	async (req, res) => {
		if (req.method !== 'POST') {
			res.status(405).send('Method not allowed');
			return;
		}
		const signature = req.headers['stripe-signature'];
		let event;
		try {
			event = stripe().webhooks.constructEvent(req.rawBody, signature, stripeWebhookSecret.value());
		} catch (err) {
			console.warn('stripeWebhook signature rejected:', err.message);
			res.status(400).send('Webhook signature verification failed');
			return;
		}

		try {
			switch (event.type) {
				case 'checkout.session.completed':
					await handleCheckoutCompleted(event);
					break;
				case 'customer.subscription.updated':
				case 'customer.subscription.deleted':
					await handleSubscriptionEvent(event);
					break;
				case 'invoice.paid':
				case 'invoice.payment_failed':
					await handleInvoiceEvent(event);
					break;
				default:
					await recordStripeEvent(event, null, null);
			}
			res.json({ received: true });
		} catch (err) {
			console.error('stripeWebhook failed:', event.type, event.id, err);
			res.status(500).send('Webhook processing failed');
		}
	}
);

export const _billingTesting = {
	normalizeMarket,
	planForSubscriptionStatus,
	checkoutShouldOpenPortal,
	subscriptionBillingUpdate,
	resetStripeClientForTests
};
