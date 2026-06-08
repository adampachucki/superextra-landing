// Localizes the live-activity feed (status labels, thought-step authors,
// tool detail rows, idle/chrome strings) to the prompt language detected for
// the session — falling back to the UI locale, then English. The backend emits
// stable identifiers and `labelKey` + `vars`; the words live here in Paraglide.

import * as m from '$lib/paraglide/messages';
import { getLocale } from '$lib/paraglide/runtime';
import type { TimelineEvent } from '$lib/chat-types';

type DetailEvent = Extract<TimelineEvent, { kind: 'detail' }>;

export const LABEL_LOCALES = ['en', 'de', 'pl'] as const;
export type LabelLocale = (typeof LABEL_LOCALES)[number];

type MsgFn = (inputs?: Record<string, unknown>, options?: { locale?: LabelLocale }) => string;
const messages = m as unknown as Record<string, MsgFn>;

function isLabelLocale(value: string | null | undefined): value is LabelLocale {
	return !!value && (LABEL_LOCALES as readonly string[]).includes(value);
}

/**
 * Resolve which catalog to render activity labels in. The backend already
 * collapses an unclassifiable prompt into the UI locale during detection, so a
 * present `language` is a real detected language: render it if we ship that
 * catalog, otherwise floor to English (NOT the UI locale — Polish labels on a
 * Spanish report would be worse than English). Only a missing `language`
 * (legacy session / not yet written) falls back to the UI locale.
 */
export function labelLocale(language?: string | null): LabelLocale {
	if (isLabelLocale(language)) return language;
	if (language) return 'en';
	const ui = getLocale();
	return isLabelLocale(ui) ? ui : 'en';
}

function call(key: string, locale: LabelLocale, vars?: Record<string, unknown>): string | null {
	const fn = messages[key];
	return fn ? fn(vars ?? {}, { locale }) : null;
}

const AGENT_KEY: Record<string, string> = {
	router: 'act_agent_router',
	context_enricher: 'act_agent_context_enricher',
	research_lead: 'act_agent_research_lead',
	report_writer: 'act_agent_report_writer',
	continue_research: 'act_agent_continue_research',
	market_landscape: 'act_agent_market_landscape',
	menu_pricing: 'act_agent_menu_pricing',
	revenue_sales: 'act_agent_revenue_sales',
	guest_intelligence: 'act_agent_guest_intelligence',
	location_traffic: 'act_agent_location_traffic',
	operations: 'act_agent_operations',
	marketing_brand: 'act_agent_marketing_brand',
	review_analyst: 'act_agent_review_analyst',
	social_analyst: 'act_agent_social_analyst',
	dynamic_researcher_1: 'act_agent_dynamic_researcher',
	dynamic_researcher_2: 'act_agent_dynamic_researcher',
	dynamic_researcher_3: 'act_agent_dynamic_researcher'
};

const STAGE_KEY: Record<string, string> = {
	routing: 'act_stage_routing',
	building_context: 'act_stage_building_context',
	planning_research: 'act_stage_planning_research',
	writing_final_report: 'act_stage_writing_final_report',
	continuing_research: 'act_stage_continuing_research',
	specialist_research: 'act_stage_specialist_research',
	agent_work: 'act_stage_agent_work'
};

const AUTHOR_KEY: Record<string, string> = {
	router: 'act_author_router',
	context_enricher: 'act_author_context_enricher',
	research_lead: 'act_author_research_lead',
	report_writer: 'act_author_report_writer',
	continue_research: 'act_author_continue_research',
	market_landscape: 'act_author_market_landscape',
	menu_pricing: 'act_author_menu_pricing',
	revenue_sales: 'act_author_revenue_sales',
	guest_intelligence: 'act_author_guest_intelligence',
	location_traffic: 'act_author_location_traffic',
	operations: 'act_author_operations',
	marketing_brand: 'act_author_marketing_brand',
	review_analyst: 'act_author_review_analyst',
	dynamic_researcher_1: 'act_author_dynamic_researcher',
	dynamic_researcher_2: 'act_author_dynamic_researcher',
	dynamic_researcher_3: 'act_author_dynamic_researcher'
};

const FAMILY_KEY: Record<DetailEvent['family'], string> = {
	'Google Maps': 'act_family_google_maps',
	'Google reviews': 'act_family_google_reviews',
	TripAdvisor: 'act_family_tripadvisor',
	'Searching the web': 'act_family_searching_web',
	Analysis: 'act_family_analysis',
	'Public sources': 'act_family_public_sources',
	Warnings: 'act_family_warnings'
};

/** Live status label for the running agent/stage, or null. */
export function liveStatusLabel(
	activeAgent: string | null,
	activeStage: string | null,
	locale: LabelLocale
): string | null {
	const agentKey = activeAgent ? AGENT_KEY[activeAgent] : null;
	if (agentKey) return call(agentKey, locale);
	const stageKey = activeStage ? STAGE_KEY[activeStage] : null;
	return stageKey ? call(stageKey, locale) : null;
}

export function familyLabel(family: DetailEvent['family'], locale: LabelLocale): string {
	return call(FAMILY_KEY[family], locale) ?? family;
}

export function authorLabel(author: string | null | undefined, locale: LabelLocale): string {
	if (!author) return call('act_author_fallback', locale) ?? 'Reasoning';
	const key = AUTHOR_KEY[author];
	return (key ? call(key, locale) : null) ?? call('act_author_default', locale) ?? 'Researching';
}

/**
 * Localized text for a detail row. Prose rows carry `labelKey` (+ optional
 * `vars`); pure-data rows (queries, URLs) fall back to the verbatim `text`.
 */
export function detailText(event: DetailEvent, locale: LabelLocale): string {
	if (event.labelKey) {
		const rendered = call(event.labelKey, locale, event.vars);
		if (rendered) return rendered;
	}
	return event.text;
}

/** Headline label for a run-start/Analysis status row. */
export function statusDetailLabel(event: DetailEvent, locale: LabelLocale): string {
	if (event.labelKey) {
		const rendered = call(event.labelKey, locale, event.vars);
		if (rendered) return rendered;
	}
	return event.family === 'Analysis' ? event.text : familyLabel(event.family, locale);
}

export function idleLabels(locale: LabelLocale): string[] {
	return [
		call('act_idle_thinking', locale) ?? 'Thinking',
		call('act_idle_working', locale) ?? 'Working',
		call('act_idle_analyzing', locale) ?? 'Analyzing'
	];
}
