import { describe, it, mock } from 'node:test';
import assert from 'node:assert/strict';

mock.module('firebase-functions/v2/https', {
	namedExports: {
		onRequest: (_opts, handler) => handler
	}
});

mock.module('firebase-functions/params', {
	namedExports: {
		defineSecret: () => ({ value: () => 'test-secret' }),
		defineString: () => ({ value: () => 'tester@example.com,*@superextra.ai' })
	}
});

mock.module('firebase-admin/auth', {
	namedExports: {
		getAuth: () => ({ verifyIdToken: mock.fn() })
	}
});

mock.module('firebase-admin/firestore', {
	namedExports: {
		getFirestore: mock.fn(),
		FieldValue: {
			serverTimestamp: () => '__server_timestamp__'
		},
		Timestamp: {
			fromMillis: (ms) => ({ __timestampMillis: ms })
		}
	}
});

const { _billingTesting } = await import('./billing.js');

describe('billing helpers', () => {
	it('normalizes unsupported markets to the USD fallback', () => {
		assert.equal(_billingTesting.normalizeMarket('pl'), 'pl');
		assert.equal(_billingTesting.normalizeMarket('de'), 'de');
		assert.equal(_billingTesting.normalizeMarket('xx'), 'other');
		assert.equal(_billingTesting.normalizeMarket(undefined), 'other');
	});

	it('keeps checkout returns on the originating app path', () => {
		assert.equal(
			_billingTesting.normalizeReturnPath('/chat?sid=abc&billing=success&session_id=cs_test_x', {
				mode: 'live'
			}),
			'/chat?sid=abc'
		);
		assert.equal(
			_billingTesting.normalizeReturnPath('/chat?sid=abc#reply', _billingTesting.LIVE_BILLING),
			'/chat?sid=abc'
		);
		assert.equal(
			_billingTesting.normalizeReturnPath('/chat?sid=abc', _billingTesting.TEST_BILLING),
			'/chat?sid=abc&billingMode=test'
		);
		assert.equal(
			_billingTesting.normalizeReturnPath(
				'https://evil.example/chat',
				_billingTesting.LIVE_BILLING
			),
			'/chat'
		);
		assert.equal(
			_billingTesting.checkoutReturnUrl(
				'https://agent.superextra.ai',
				'/chat?sid=abc',
				'success',
				true
			),
			'https://agent.superextra.ai/chat?sid=abc&billing=success&session_id={CHECKOUT_SESSION_ID}'
		);
	});

	it('keeps dunning subscriptions paid until Stripe ends access', () => {
		assert.equal(_billingTesting.planForSubscriptionStatus('active'), 'paid');
		assert.equal(_billingTesting.planForSubscriptionStatus('trialing'), 'paid');
		assert.equal(_billingTesting.planForSubscriptionStatus('past_due'), 'paid');
		assert.equal(_billingTesting.planForSubscriptionStatus('unpaid'), 'free');
		assert.equal(_billingTesting.planForSubscriptionStatus('canceled'), 'free');
	});

	it('sends existing managed subscriptions to the customer portal from checkout entry points', () => {
		assert.equal(
			_billingTesting.checkoutShouldOpenPortal({
				stripeCustomerId: 'cus_123',
				stripeSubscriptionId: 'sub_123',
				status: 'active'
			}),
			true
		);
		assert.equal(
			_billingTesting.checkoutShouldOpenPortal({
				stripeCustomerId: 'cus_123',
				stripeSubscriptionId: 'sub_123',
				status: 'unpaid'
			}),
			true
		);
		assert.equal(
			_billingTesting.checkoutShouldOpenPortal({
				stripeCustomerId: 'cus_123',
				stripeSubscriptionId: 'sub_123',
				status: 'canceled'
			}),
			false
		);
		assert.equal(
			_billingTesting.checkoutShouldOpenPortal({
				stripeCustomerId: 'cus_123',
				status: 'active'
			}),
			false
		);
		assert.equal(
			_billingTesting.checkoutShouldOpenPortal({
				stripeCustomerId: 'cus_123',
				status: 'checkout_pending'
			}),
			false
		);
		assert.equal(
			_billingTesting.checkoutShouldOpenPortal({
				stripeCustomerId: 'cus_123',
				stripeSubscriptionId: 'sub_123',
				status: 'checkout_pending'
			}),
			false
		);
	});

	it('mirrors subscription state into the user billing map', () => {
		const update = _billingTesting.subscriptionBillingUpdate({
			id: 'sub_123',
			customer: 'cus_123',
			status: 'active',
			cancel_at_period_end: true,
			current_period_end: 1_800_000_000,
			latest_invoice: 'in_123',
			metadata: { market: 'pl' },
			items: {
				data: [
					{
						price: {
							id: 'price_123',
							currency: 'pln'
						}
					}
				]
			}
		});

		assert.equal(update.plan, 'paid');
		assert.deepEqual(update.billing, {
			stripeCustomerId: 'cus_123',
			stripeSubscriptionId: 'sub_123',
			status: 'active',
			mode: 'live',
			priceId: 'price_123',
			priceLookupKey: 'superextra_unlimited_monthly',
			market: 'pl',
			currency: 'pln',
			currentPeriodEnd: { __timestampMillis: 1_800_000_000_000 },
			cancelAtPeriodEnd: true,
			latestInvoiceId: 'in_123',
			updatedAt: '__server_timestamp__'
		});
	});

	it('uses the subscription currency for multi-currency prices', () => {
		const update = _billingTesting.subscriptionBillingUpdate({
			id: 'sub_123',
			customer: 'cus_123',
			status: 'active',
			currency: 'pln',
			items: {
				data: [
					{
						price: {
							id: 'price_123',
							currency: 'usd'
						}
					}
				]
			}
		});

		assert.equal(update.billing.currency, 'pln');
	});

	it('keeps sandbox subscription mirrors out of live billing fields', () => {
		const update = _billingTesting.subscriptionBillingUpdate(
			{
				id: 'sub_123',
				customer: 'cus_123',
				status: 'active',
				currency: 'eur',
				items: { data: [{ price: { id: 'price_123', currency: 'usd' } }] }
			},
			{},
			_billingTesting.TEST_BILLING
		);

		assert.equal(update.plan, undefined);
		assert.equal(update.billing, undefined);
		assert.equal(update.planTest, 'paid');
		assert.equal(update.billingTest.mode, 'test');
		assert.equal(update.billingTest.currency, 'eur');
	});

	it('matches sandbox billing allow-list patterns', () => {
		assert.equal(_billingTesting.emailPatternMatches('ap@superextra.ai', '*@superextra.ai'), true);
		assert.equal(_billingTesting.emailPatternMatches('ap@example.com', '*@superextra.ai'), false);
		assert.equal(
			_billingTesting.emailPatternMatches('tester@example.com', 'tester@example.com'),
			true
		);
	});

	it('requires a verified allow-listed email or tester claim for sandbox billing', () => {
		assert.equal(
			_billingTesting.userCanUseTestBilling({
				email: 'ap@superextra.ai',
				emailVerified: true,
				billingTester: false
			}),
			true
		);
		assert.equal(
			_billingTesting.userCanUseTestBilling({
				email: 'ap@superextra.ai',
				emailVerified: false,
				billingTester: false
			}),
			false
		);
		assert.equal(_billingTesting.userCanUseTestBilling({ billingTester: true }), true);
	});
});
