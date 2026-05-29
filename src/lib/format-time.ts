import * as m from '$lib/paraglide/messages';
import { getLocale } from '$lib/paraglide/runtime';

// Map app locale → BCP47 tag for Intl date formatting.
const DATE_LOCALE: Record<string, string> = {
	en: 'en-GB',
	de: 'de-DE',
	pl: 'pl-PL'
};

/** Sidebar + recent-chats list relative-time formatting.
 *  Returns localized strings like "just now", "5m ago", "3h ago", "yesterday",
 *  "6d ago", or a short date ("17 Apr") for older timestamps. */
export function formatRelativeTime(ts: number, now = Date.now()): string {
	const diff = now - ts;
	const minutes = Math.floor(diff / 60000);
	if (minutes < 1) return m.time_just_now();
	if (minutes < 60) return m.time_min_ago({ count: minutes });
	const hours = Math.floor(minutes / 60);
	if (hours < 24) return m.time_hr_ago({ count: hours });
	const days = Math.floor(hours / 24);
	if (days === 1) return m.time_yesterday();
	if (days < 7) return m.time_days_ago({ count: days });
	return new Date(ts).toLocaleDateString(DATE_LOCALE[getLocale()] ?? 'en-GB', {
		month: 'short',
		day: 'numeric'
	});
}
