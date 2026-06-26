// Source of truth for paid-social ad campaigns and organic FB seed posts.
// The studio at /brand/ads reads from this; the campaign build (Meta) reads the
// same values. Edit live in the studio (session-only) and use its "Export JSON"
// button to hand the JSON back to commit changes here.

export type Bg = 'white' | 'black' | 'color';

export type ColorTheme =
	| 'periwinkle'
	| 'lavender-pink'
	| 'violet-cyan'
	| 'blue-teal'
	| 'indigo-violet'
	| 'mint'
	| 'dusk';

// Meta feed CTA buttons — fixed dropdown, not free text.
export const CTAS = [
	'Get Started',
	'Book Now',
	'Request Time',
	'Apply Now',
	'Learn More',
	'Sign Up'
] as const;
export type Cta = (typeof CTAS)[number];

export const COLOR_THEMES: { key: ColorTheme; label: string }[] = [
	{ key: 'periwinkle', label: 'Periwinkle' },
	{ key: 'lavender-pink', label: 'Lavender → Pink' },
	{ key: 'violet-cyan', label: 'Violet → Cyan' },
	{ key: 'blue-teal', label: 'Blue → Teal' },
	{ key: 'indigo-violet', label: 'Indigo → Violet' },
	{ key: 'mint', label: 'Mint' },
	{ key: 'dusk', label: 'Dusk' }
];

export type Ad = {
	id: string;
	note: string; // internal territory label
	hero: string; // in-image headline; <br> for line breaks
	taglineOnCard: boolean; // show the tagline under the wordmark (off when the hero already is it)
	primary: string; // Meta primary text / organic post caption
	headline: string; // Meta headline field (under the image); empty for organic posts
	cta: Cta;
	bg: Bg;
	colorTheme: ColorTheme;
};

export type Campaign = {
	name: string;
	destinationUrl: string;
	ads: Ad[];
};

const base = {
	cta: 'Get Started' as Cta,
	bg: 'color' as Bg,
	colorTheme: 'indigo-violet' as ColorTheme
};

// Organic FB seed posts reuse the paid creatives' artwork but carry the full
// post caption in `primary` (multi-line) and no link headline — the studio shows
// the image and caption together so both can be grabbed from one place.
const orgBase = {
	headline: '',
	cta: 'Learn More' as Cta,
	bg: 'color' as Bg,
	colorTheme: 'indigo-violet' as ColorTheme
};

export const campaigns: Campaign[] = [
	{
		name: 'US Leads — restaurants',
		destinationUrl: 'https://agent.superextra.ai/',
		ads: [
			{
				id: 'A',
				note: 'why is it happening',
				hero: 'Why your<br>restaurant<br>slowed down?',
				taglineOnCard: true,
				primary:
					'Sales drop and no one can say why. Superextra shows what changed around you — find the fix before it sticks.',
				headline: 'Know what changed — and why',
				...base
			},
			{
				id: 'B',
				note: 'the big decisions',
				hero: 'AI consultant<br>for every<br>restaurant.',
				taglineOnCard: false,
				primary:
					'Where to open. What to serve. When to advertise. Superextra answers the decisions that make or break a restaurant — with live data from the market around you.',
				headline: 'AI consultant for every restaurant',
				...base
			},
			{
				id: 'C',
				note: 'beat the competitor',
				hero: 'Beat the<br>restaurant<br>next door.',
				taglineOnCard: true,
				primary:
					"See how the restaurants near you advertise, what their guests love, and where they're winning. Superextra keeps you one step ahead of the competition next door.",
				headline: 'Beat the restaurant next door',
				...base
			},
			{
				id: 'D',
				note: 'pricing',
				hero: 'Your menu.<br>More guests.<br>Better margins.',
				taglineOnCard: true,
				primary:
					"See every competitor's prices. Set yours to win. Superextra benchmarks your whole menu against the local market in minutes.",
				headline: 'Price like you can see the market',
				...base
			}
		]
	},
	{
		name: 'FB seed posts — organic',
		destinationUrl: 'https://agent.superextra.ai/',
		ads: [
			{
				id: '1',
				note: 'pinned intro',
				hero: 'AI consultant<br>for every<br>restaurant.',
				taglineOnCard: false,
				primary: `Meet Superextra — an AI consultant for every restaurant.

Where to open. How to price. When to hire. What's shifting next door. Superextra reads the market around a restaurant — competitors, pricing, guest reviews, delivery, demand — and turns it into clear, operator-ready answers.

Ask it anything → agent.superextra.ai`,
				...orgBase
			},
			{
				id: '2',
				note: 'why sales slowed',
				hero: 'Why your<br>restaurant<br>slowed down?',
				taglineOnCard: true,
				primary: `Sales slip and no one can say why.

Superextra shows what changed around a restaurant — a competitor's new promo, a pricing shift, a wave of reviews — so the fix happens before the dip sticks.

agent.superextra.ai`,
				...orgBase
			},
			{
				id: '3',
				note: 'beat next door',
				hero: 'Beat the<br>restaurant<br>next door.',
				taglineOnCard: true,
				primary: `Know the restaurant next door better than they do.

How they advertise, what their guests rave about, where they're winning — Superextra keeps the competition in full view.

agent.superextra.ai`,
				...orgBase
			},
			{
				id: '4',
				note: 'menu pricing',
				hero: 'Your menu.<br>More guests.<br>Better margins.',
				taglineOnCard: true,
				primary: `Price your menu like you can see the whole market — because now you can.

Superextra benchmarks every item against local competitors in minutes. More guests, better margins.

agent.superextra.ai`,
				...orgBase
			}
		]
	}
];

export const newAd = (id: string): Ad => ({
	id,
	note: 'new ad',
	hero: 'Headline<br>goes here',
	taglineOnCard: true,
	primary: '',
	headline: '',
	...base
});
