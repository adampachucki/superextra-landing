// Source of truth for paid-social ad campaigns. Versioned here so the studio at
// /brand/ads reads from it and the campaign build (Meta) reads the same values.
// The studio lets you edit live (kept in localStorage); use its "Export" button to
// hand the JSON back to commit changes here.

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
	primary: string; // Meta primary text
	headline: string; // Meta headline field (under the image)
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

export const campaign: Campaign = {
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
};

export const newAd = (id: string): Ad => ({
	id,
	note: 'new ad',
	hero: 'Headline<br>goes here',
	taglineOnCard: true,
	primary: '',
	headline: '',
	...base
});
