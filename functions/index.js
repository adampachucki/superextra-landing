// Deployment entrypoint — Firebase resolves function exports from this
// module (names must match firebase.json rewrites). Handler logic lives in
// chat-handlers.js / email-handlers.js / speech-handlers.js, plus billing.js
// and watchdog.js.
import { _resetRateLimits as _resetChatRateLimits } from './chat-handlers.js';
import { _resetRateLimits as _resetEmailRateLimits } from './email-handlers.js';

export { agentStream, agentCancel, agentFeedback, agentDelete } from './chat-handlers.js';
export { intake, sendMagicLink } from './email-handlers.js';
export { sttToken, tts } from './speech-handlers.js';
export { watchdog } from './watchdog.js';
export {
	billingCheckout,
	billingConfirm,
	billingPortal,
	stripeWebhook,
	billingCheckoutTest,
	billingConfirmTest,
	billingPortalTest,
	stripeWebhookTest
} from './billing.js';

// Test-only — bypass abuse limits so each test starts from a clean slate.
export function _resetRateLimits() {
	_resetChatRateLimits();
	_resetEmailRateLimits();
}
