<script lang="ts">
	import Navbar from '$lib/components/Navbar.svelte';
	import Footer from '$lib/components/Footer.svelte';
	import HeroCanvas from '$lib/components/HeroCanvas.svelte';
</script>

<svelte:head>
	<title>Memo - Superextra</title>
	<meta name="description" content="Superextra — the market intelligence layer restaurants have been missing." />
</svelte:head>

<Navbar />

<header class="relative overflow-hidden" style="background-color: #0a0a0a; padding-top: 8rem; padding-bottom: 5rem;">
	<div class="pointer-events-none absolute inset-0" style="left: -5%; width: 110%; top: -5%; height: 110%;">
		<HeroCanvas class="absolute inset-0 h-full w-full" width={1600} height={900} />
	</div>
	<div class="relative mx-auto px-6" style="max-width: 780px;">
		<p class="text-sm font-medium uppercase tracking-widest" style="color: rgba(255,255,255,0.4);">Berlin &middot; March 2026</p>
		<h1 class="mt-8 font-normal" style="color: #fff; font-size: clamp(2.75rem, 6vw, 4.5rem); line-height: 1.05; letter-spacing: -0.03em;">
			The market view restaurants have been missing
		</h1>
		<p class="mt-8 max-w-xl" style="color: rgba(255,255,255,0.8); font-size: clamp(1.125rem, 2vw, 1.25rem); line-height: 1.45;">
			We are building the market intelligence platform for the restaurant industry. Our purpose is simple: to give operators a clear view of what is happening <em style="color: rgba(255,255,255,0.7);">outside</em> their four walls, not just inside them.
		</p>
	</div>
</header>

<article class="memo mx-auto px-6 pb-32" style="max-width: 780px; padding-top: 5.5rem;">
	<h2>The operational blind spot</h2>
	<p>Restaurants already know their internal numbers: covers, average tickets, labor costs, and delivery mix. What they cannot see is the context.</p>
	<p>When a month is weak, they don't know if it's an internal failure or a market-wide slump. They lack a view on whether they are priced correctly against their true competitor set, what local labor actually costs, or where the next logical site should be.</p>
	<p>Hotels solved this decades ago. STR provided every hotel with real-time benchmarking against its competitive set. The restaurant sector is larger and more fragmented, yet it has had nothing comparable&mdash;until now.</p>

	<h2>The guesswork era is over</h2>
	<p>Currently, the industry does market intelligence badly. When a bad stretch hits or a competitor pulls ahead, operators fall back on a manual, unreliable workflow:</p>
	<ul>
		<li>Calling other restaurateurs for anecdotes.</li>
		<li>Asking supplier account managers for "vibes" on the market.</li>
		<li>Manually scrolling delivery apps and review platforms.</li>
		<li>Scanning public filings or counting physical receipts.</li>
	</ul>
	<p>Operators care deeply about external data, but their current process is messy, anecdotal, and impossible to scale. We are replacing this broken workflow with a professional intelligence infrastructure.</p>

	<h2>Answers, not analytics</h2>
	<p>Operators don't need more "data"; they need reliable answers to concrete questions:</p>
	<blockquote>
		Are we underperforming, or is the whole neighborhood down?<br />
		What should we pay staff to ensure retention, not just hiring?<br />
		Which days and hours are actually worth operating in this climate?<br />
		Where is the real expansion opportunity for our specific format?
	</blockquote>
	<p>We are not building another dashboard that asks the user to do the analytical heavy lifting. We are building a system that delivers specific, plain-language answers to the recurring decisions that shape revenue and margin.</p>

	<h2 class="!text-[clamp(2rem,4vw,3rem)]">A market analyst for every restaurant</h2>
	<p>Superextra aggregates and synthesises external market data from dozens of sources, then delivers it through AI agents tailored to each restaurant's specific context.</p>
	<p><strong>We set up the market context.</strong> Superextra maps the restaurant's competitive set, trade area, cuisine cohort, and pricing tier. The operator does not build anything from scratch.</p>
	<p><strong>We deliver a structured market view.</strong> Each customer receives an initial intelligence layer that is specific to their business, interactive rather than static, and designed to be explored over time.</p>
	<p><strong>We provide a tailored agent.</strong> Every customer gets an AI agent that understands the venue, its neighbourhood, and its benchmark cohort, and can answer market questions in natural language.</p>
	<p><strong>We keep the intelligence current.</strong> Markets move. Competitors open and close. Prices shift. Sentiment changes. Superextra monitors those changes and turns them into ongoing updates.</p>
	<p>The goal is not to replace operator judgment. It is to give that judgment context, so an operator can move from "I think this is happening" to "I know what is happening, and I know what to do next."</p>

	<h2>Every signal, one view</h2>
	<p>We aggregate signals from dozens of external sources&mdash;including discovery platforms, delivery apps, menus, reviews, hiring boards, registries, and foot traffic patterns&mdash;to build seven distinct layers of intelligence:</p>
	<table>
		<tbody>
			<tr><td><strong>Market Landscape</strong></td><td>Openings, closings, saturation, and "white space" analysis.</td></tr>
			<tr><td><strong>Menu & Pricing</strong></td><td>Competitor trends, delivery markups, and promotional activity.</td></tr>
			<tr><td><strong>Revenue & Sales</strong></td><td>Estimates for comparable venues, seasonality, and channel splits.</td></tr>
			<tr><td><strong>Guest Intelligence</strong></td><td>Deep sentiment analysis across the competitive set.</td></tr>
			<tr><td><strong>Location & Traffic</strong></td><td>Trade area demographics and seasonal foot traffic shifts.</td></tr>
			<tr><td><strong>Marketing & Digital</strong></td><td>Competitor social signals and demand-generation effectiveness.</td></tr>
			<tr><td><strong>Operations</strong></td><td>Local labor salary benchmarks and supplier pricing signals.</td></tr>
		</tbody>
	</table>

	<h2>It's never been possible before</h2>
	<p>This opportunity exists now because the information trail is finally mature, but the noise is at an all-time high. Previously, connecting fragmented signals from menus, filings, and reviews was too manual to be profitable.</p>
	<p>Our AI models materially change the economics of this industry. We can now continuously collect, refresh, and synthesize these noisy external signals into a usable market map at a fraction of the cost of a traditional consultant.</p>

	<h2>Built for the operators who need it most</h2>
	<p>We are starting with small multi-venue operators (groups with 2&ndash;5 locations). These businesses are the perfect "design center":</p>
	<ul>
		<li>They make consequential decisions on pricing and expansion.</li>
		<li>They feel the immediate cost of getting those decisions wrong.</li>
		<li>They are large enough to value professional intelligence but too small to have in-house analysts.</li>
	</ul>
	<p><strong>Our pricing:</strong> &euro;899 setup fee + &euro;299 quarterly subscription per location.</p>

	<h2>Superextra was pulled into existence</h2>
	<p>Superextra was pulled into existence by the market. Our founding team previously built <strong>Everytap</strong> and <strong>Finebite</strong>, working with over 2,500 restaurants and 2 million guests.</p>
	<p>We aren't entering this category cold. This product is a direct response to years of operators asking us the same questions: <em>What are my competitors doing? How should I price this? Where do I go next?</em> This history gives us a massive head start in access, pattern recognition, and distribution.</p>

	<h2 class="!text-[clamp(2rem,4vw,3rem)]">A large market is hiding behind a messy workflow</h2>
	<p>Restaurants across Europe are already paying for market intelligence. They pay in consultant fees, agency retainers, management time, and bad decisions made with incomplete information.</p>
	<p>Existing companies validate pieces of the demand, but the category remains open. Some players are US-centric. Some are enterprise-heavy. Some are tied to internal systems. Some solve only one narrow function. The gap is still there for a Europe-first product built specifically for restaurant operators and centred on external market context rather than internal system data.</p>
	<p><strong>That is the position we are taking.</strong></p>

	<h2>Every restaurant will need this</h2>
	<p>By starting with a practical wedge in Poland and Germany, we are building a piece of infrastructure that every restaurant will eventually rely on for market context with the same confidence they have in their own bank balance.</p>
	<p>Our ambition is to become the definitive external intelligence layer for the industry. Internal systems (POS, Inventory) tell operators what happened. Superextra tells them <em>why</em> it happened and what is changing next.</p>
	<p><strong>That is the company we are building.</strong></p>
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
		font-size: 18px;
		line-height: 2;
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
</style>
