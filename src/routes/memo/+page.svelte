<script lang="ts">
	import Navbar from '$lib/components/Navbar.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import HeroCanvas from '$lib/components/HeroCanvas.svelte';
</script>

<svelte:head>
	<title>Memo - Superextra</title>
	<meta
		name="description"
		content="Superextra — the market intelligence layer restaurants have been missing."
	/>
</svelte:head>

<Navbar transparent />

<header
	class="relative overflow-hidden"
	style="background-color: #0a0a0a; padding-top: 8rem; padding-bottom: 5rem;"
>
	<div
		class="pointer-events-none absolute inset-0"
		style="left: -5%; width: 110%; top: -5%; height: 110%;"
	>
		<HeroCanvas
			class="absolute inset-0 h-full w-full"
			width={1600}
			height={900}
			lineOffsetY={120}
			lineSpacing={60}
		/>
	</div>
	<div class="relative mx-auto px-6" style="max-width: 780px;">
		<p class="text-sm font-medium tracking-widest uppercase" style="color: rgba(255,255,255,0.4);">
			Berlin &middot; March 2026
		</p>
		<h1
			class="mt-8 font-normal"
			style="color: #fff; font-size: clamp(2.75rem, 6vw, 4.5rem); line-height: 1.05; letter-spacing: -0.03em;"
		>
			The market view restaurants have been missing
		</h1>
		<p
			class="mt-8"
			style="color: rgba(255,255,255,0.8); font-size: clamp(1.125rem, 2vw, 1.25rem); line-height: 1.45;"
		>
			We're building a market intelligence platform to give restaurants a clear view of what is
			happening <em style="color: rgba(255,255,255,0.7);">outside</em> their four walls, not just inside
			them.
		</p>
	</div>
</header>

<article class="memo mx-auto px-6 pb-32" style="max-width: 780px; padding-top: 3.5rem;">
	<!-- <h2>The missing context</h2> -->
	<p>
		Every restaurant operator already knows their internal numbers: covers, average tickets, labor
		costs, and delivery mix. What they can't see is the broader market context.
	</p>
	<p>
		When a month is weak, the question is always the same: is this an internal failure, or a
		market-wide slump? They lack a view on whether they are priced correctly relative to other
		venues, what local labor actually costs, or where the next logical site should be.
	</p>
	<p>
		Hotels solved this decades ago. STR provided every hotel with real-time benchmarking against its
		competitive set. The restaurant sector is larger and more fragmented, and has nothing
		comparable.
	</p>

	<h2>Gossip, gut feel, guesswork</h2>
	<p>
		Restaurants do market intelligence. They just do it badly. When things go off, operators fall
		back on a manual workflow:
	</p>
	<ul>
		<li>Calling other restaurateurs for anecdotes</li>
		<li>Asking supplier account managers for "vibes" on the market</li>
		<li>Manually scrolling delivery apps and review platforms</li>
		<li>Scanning public filings or counting physical receipts</li>
	</ul>
	<p>
		Operators care deeply about external data, but their current process is messy, anecdotal, and
		impossible to scale. We're solving this for them.
	</p>

	<h2>Answers, not analytics</h2>
	<p>Operators don't need more "data"; they need reliable answers to concrete questions:</p>
	<blockquote>
		Are we underperforming, or is the whole neighbourhood down?<br />
		What should we pay staff to ensure retention, not just hiring?<br />
		Which days and hours are actually worth operating in this climate?<br />
		Where is the real expansion opportunity for our specific format?
	</blockquote>
	<p>
		We're not building another dashboard that asks the user to do the analytical heavy lifting.
		We're delivering specific, plain-language answers to the recurring decisions that shape revenue
		and margin.
	</p>

	<h2>A market analyst for every restaurant</h2>
	<p>
		Each restaurant gets an AI agent that knows its market, competitors, and neighbourhood &mdash;
		and can answer questions, build reports, and surface what matters.
	</p>
	<p>
		<strong>We set up the market context.</strong> Superextra maps the restaurant's competitive set, trade
		area, cuisine cohort, and pricing tier. The operator does not build anything from scratch.
	</p>
	<p>
		<strong>The agent delivers tailored analysis.</strong> Reports, interactive dashboards, and deep dives
		&mdash; all generated around the specific questions the restaurant is asking.
	</p>
	<p>
		<strong>We keep the intelligence current.</strong> Markets move. Competitors open and close. Prices
		shift. Sentiment changes. Superextra monitors those changes and turns them into ongoing updates.
	</p>
	<p>
		The goal is to give context, so an operator can move from <em>I think this is happening</em> to
		<em>I know what is happening, and I know what to do next.</em>
	</p>

	<h2>Every signal, one place</h2>
	<p>
		We aggregate signals from dozens of external sources&mdash;including discovery platforms,
		delivery apps, menus, reviews, hiring boards, registries, and foot traffic patterns&mdash;to
		build seven connected layers of intelligence:
	</p>
	<table>
		<tbody>
			<tr
				><td><strong>Market Landscape</strong></td><td
					>Openings, closings, saturation, and "white space" analysis.</td
				></tr
			>
			<tr
				><td><strong>Menu & Pricing</strong></td><td
					>Competitor trends, delivery markups, and promotional activity.</td
				></tr
			>
			<tr
				><td><strong>Revenue & Sales</strong></td><td
					>Estimates for comparable venues, seasonality, and channel splits.</td
				></tr
			>
			<tr
				><td><strong>Guest Intelligence</strong></td><td
					>Deep sentiment analysis across the competitive set.</td
				></tr
			>
			<tr
				><td><strong>Location & Traffic</strong></td><td
					>Trade area demographics and seasonal foot traffic shifts.</td
				></tr
			>
			<tr
				><td><strong>Marketing & Digital</strong></td><td
					>Competitor social signals and demand-generation effectiveness.</td
				></tr
			>
			<tr
				><td><strong>Operations</strong></td><td
					>Local labor salary benchmarks and supplier pricing signals.</td
				></tr
			>
		</tbody>
	</table>
	<p>
		Every layer feeds into the agents so their answers are grounded in real data, not
		hallucinations.
	</p>

	<h2>It's never been possible before</h2>
	<p>
		This opportunity exists now because the information trail is already there. For years, it was
		too fragmented to turn into something reliable without a lot of manual work.
	</p>
	<p>
		What has changed is the ability to connect scattered entities, structure noisy signals, maintain
		them over time, and deliver the output in plain language instead of raw analysis.
	</p>
	<p>That is why our AI models materially change the economics. They make the full chain viable:</p>
	<ul>
		<li>Collect and refresh external market signals continuously</li>
		<li>Connect them into a usable market map</li>
		<li>Synthesise them into benchmarked intelligence</li>
		<li>Deliver them in a form an operator can act on quickly</li>
	</ul>
	<p>
		That combination is what makes our product possible now in a way it was not a few years ago.
	</p>

	<h2>Built for the operators who need it most</h2>
	<p>
		We're starting with small multi-venue operators (groups with 2&ndash;5 locations). These
		businesses sit right in the sweet spot.
	</p>
	<p>
		They make consequential decisions on pricing and expansion, and feel the immediate cost of
		getting those decisions wrong. They're large enough to value professional intelligence but too
		small to have in-house analysts.
	</p>
	<p>
		<strong>Our pricing:</strong> &euro;899 setup fee + &euro;299 quarterly subscription per location.
	</p>

	<h2>Superextra was pulled into existence</h2>
	<p>
		Our founding team previously built <strong>Everytap</strong> and <strong>Finebite</strong>,
		working with over 2,500 restaurants and 2 million guests.
	</p>
	<p>
		This product is a direct response to years of operators asking us the same questions: <em
			>What are my competitors doing? How should I price this? Where do I go next?</em
		> This history gives us a massive head start in access, pattern recognition, and distribution.
	</p>
	<p>We aren't entering this category cold.</p>

	<h2>A large market is hiding behind a messy workflow</h2>
	<p>
		Restaurants are already paying for market intelligence. They spend 2&ndash;3 hours of management
		time every week, pay consultant fees and agency retainers.
	</p>
	<p>
		Existing solutions validate pieces of the demand, but the category remains open. Some players
		are US-centric. Some are enterprise-heavy. Some are tied to internal systems. Some solve only
		one narrow function.
	</p>
	<p>
		There is a gap for a Europe-first product built specifically for restaurant operators and
		centred on external market context rather than internal system data.
	</p>
	<p><strong>That is the position we are taking.</strong></p>

	<h2>Every restaurant will need this</h2>
	<p>
		We are building a piece of infrastructure that every restaurant will eventually rely on for
		market context with the same confidence they have in their own bank balance.
	</p>
	<p>
		Our ambition is to become the definitive external intelligence layer for the industry. Internal
		systems tell operators what happened. Superextra tells them <em>why</em> it happened and what is changing
		next.
	</p>
	<p><strong>That is the company we are building.</strong></p>

	<svg class="signature" viewBox="0 0 260 90" fill="none" xmlns="http://www.w3.org/2000/svg">
		<!-- A -->
		<path
			d="M8 68 C12 40, 20 18, 28 16 C32 15, 34 20, 34 30 C34 42, 30 58, 34 64 C36 68, 42 58, 46 52"
			stroke="currentColor"
			stroke-width="1.8"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<!-- crossbar of A -->
		<path
			d="M16 48 C22 46, 30 44, 38 46"
			stroke="currentColor"
			stroke-width="1.4"
			stroke-linecap="round"
		/>
		<!-- d -->
		<path
			d="M46 52 C44 48, 42 42, 44 38 C46 34, 52 34, 54 38 C56 42, 56 50, 54 54 C52 58, 48 56, 46 52"
			stroke="currentColor"
			stroke-width="1.8"
			stroke-linecap="round"
		/>
		<path
			d="M56 18 C56 28, 55 42, 54 54 C54 58, 56 60, 60 56"
			stroke="currentColor"
			stroke-width="1.8"
			stroke-linecap="round"
		/>
		<!-- a -->
		<path
			d="M60 56 C58 50, 58 42, 60 38 C62 34, 68 34, 70 38 C72 42, 70 52, 68 56 C66 60, 62 58, 60 56"
			stroke="currentColor"
			stroke-width="1.8"
			stroke-linecap="round"
		/>
		<path
			d="M70 38 C72 46, 72 54, 74 58"
			stroke="currentColor"
			stroke-width="1.8"
			stroke-linecap="round"
		/>
		<!-- m -->
		<path
			d="M74 58 C74 50, 74 42, 76 38 C78 34, 80 36, 80 42 C80 48, 80 54, 82 56 C84 58, 86 48, 88 42 C90 36, 92 36, 92 42 C92 48, 92 56, 96 58"
			stroke="currentColor"
			stroke-width="1.8"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<!-- space + P -->
		<path
			d="M116 70 C116 54, 116 22, 116 14"
			stroke="currentColor"
			stroke-width="1.8"
			stroke-linecap="round"
		/>
		<path
			d="M116 14 C124 14, 134 16, 134 26 C134 36, 124 40, 116 38"
			stroke="currentColor"
			stroke-width="1.8"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<!-- dot -->
		<circle cx="144" cy="68" r="2" fill="currentColor" />
	</svg>
</article>

<Footer />

<style>
	.memo :global(h2) {
		font-size: clamp(1.75rem, 3.5vw, 2.5rem);
		line-height: 1.15;
		font-weight: 400;
		letter-spacing: -0.02em;
		color: var(--color-text);
		margin-top: 3.5rem;
		margin-bottom: 1.25rem;
	}

	.memo :global(h2:first-child) {
		margin-top: 0;
	}

	.memo :global(p) {
		font-size: 17px;
		line-height: 1.75;
		color: color-mix(in srgb, var(--color-text) 60%, transparent);
		margin-top: 1.25rem;
	}

	.memo :global(strong) {
		font-weight: 500;
		color: var(--color-text);
	}

	.memo :global(ul) {
		margin-top: 1.25rem;
		padding-left: 1.25rem;
		list-style: disc;
	}

	.memo :global(li) {
		font-size: 17px;
		line-height: 1.75;
		color: color-mix(in srgb, var(--color-text) 60%, transparent);
		margin-top: 0.5rem;
	}

	.memo :global(li)::marker {
		color: color-mix(in srgb, var(--color-text) 20%, transparent);
	}

	.memo :global(blockquote) {
		border-left: 2px solid var(--color-cream-300);
		padding-left: 1.5rem;
		margin: 1.5rem 0;
		font-size: 17px;
		line-height: 1.85;
		font-style: italic;
		color: color-mix(in srgb, var(--color-text) 70%, transparent);
	}

	.memo :global(table) {
		width: 100%;
		margin-top: 1.5rem;
		border-collapse: collapse;
	}

	.memo :global(tr) {
		border-bottom: 1px solid var(--color-cream-200);
	}

	.memo :global(tr:last-child) {
		border-bottom: none;
	}

	.memo :global(td) {
		padding: 0.75rem 0;
		font-size: 15px;
		vertical-align: baseline;
	}

	.memo :global(td:first-child) {
		width: 11rem;
		padding-right: 1.5rem;
		white-space: nowrap;
	}

	.memo :global(td:last-child) {
		color: color-mix(in srgb, var(--color-text) 50%, transparent);
	}

	.memo :global(.signature) {
		margin-top: 4rem;
		width: 180px;
		height: auto;
		color: var(--color-text);
		opacity: 0.5;
	}
</style>
