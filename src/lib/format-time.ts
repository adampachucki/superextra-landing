/** Sidebar + recent-chats list relative-time formatting.
 *  Returns strings like "just now", "5m ago", "3h ago", "yesterday",
 *  "6d ago", or "Apr 17" for older timestamps. */
export function formatRelativeTime(ts: number, now = Date.now()): string {
	const diff = now - ts;
	const minutes = Math.floor(diff / 60000);
	if (minutes < 1) return 'just now';
	if (minutes < 60) return `${minutes}m ago`;
	const hours = Math.floor(minutes / 60);
	if (hours < 24) return `${hours}h ago`;
	const days = Math.floor(hours / 24);
	if (days === 1) return 'yesterday';
	if (days < 7) return `${days}d ago`;
	return new Date(ts).toLocaleDateString('en-GB', { month: 'short', day: 'numeric' });
}
