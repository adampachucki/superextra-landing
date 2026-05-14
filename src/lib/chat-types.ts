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

export type ChatSourceProvider = 'google_maps' | 'google_reviews' | 'tripadvisor';

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
	diagnostics?: {
		timelineEvents: number;
		thoughts: number;
		details: number;
		warnings: number;
		modelCalls: number;
		toolCalls: number;
		toolResults: number;
		toolErrors: number;
		sourceCount: number;
		agents: string[];
		models: string[];
		tools: string[];
		msToFirstEvent?: number;
		msToFirstThought?: number;
	};
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
