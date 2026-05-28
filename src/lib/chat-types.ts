/**
 * Shared types for the chat transport + rendering layer.
 *
 * These types describe the shape of data read from Firestore
 * (`sessions/{sid}/turns/{turnKey}` + `sessions/{sid}/events/*`) and
 * rendered by the chat UI. They're kept in a types-only module so the
 * durable chat-state listener code in `chat-state.svelte.ts` and the
 * presentational components can import from one place without pulling
 * in any runtime.
 */

export type ChatSourceProvider =
	| 'google_maps'
	| 'google_reviews'
	| 'google_place_signals'
	| 'tripadvisor'
	| 'facebook'
	| 'instagram'
	| 'grounding'
	| 'public_search';

export interface ChatSource {
	title: string;
	url: string;
	domain?: string;
	provider?: ChatSourceProvider;
}

export interface TurnSummary {
	startedAtMs: number;
	finishedAtMs: number;
	elapsedMs: number;
}

/** One participant's 👍/👎 on a single answer. Only the rating is stored on the
 *  turn doc (under `feedback.<uid>`) — the turns listener streams it back so the
 *  UI can show the selected state. Downvote reasons and free-text notes are kept
 *  in the server-only `feedback` collection, never on the client-readable turn. */
export interface TurnFeedback {
	rating: 'up' | 'down';
}

export type TimelineEvent =
	| {
			kind: 'detail';
			id: string;
			group: 'search' | 'platform' | 'source' | 'warning';
			family:
				| 'Searching the web'
				| 'Google Maps'
				| 'TripAdvisor'
				| 'Google reviews'
				| 'Analysis'
				| 'Public sources'
				| 'Warnings';
			text: string;
	  }
	| {
			kind: 'thought';
			id: string;
			author: string | null;
			text: string;
	  };
