<script lang="ts">
	let scrollContainer: HTMLDivElement;
	let activeIndex = $state(0);

	const useCases = [
		{
			title: 'Market Research',
			audience: 'Operators & Chains',
			description:
				'Understand market dynamics, competitive positioning, and emerging white spaces. Continuously monitor shifts so you spot opportunities before anyone else.',
			image: '/ppl/image1.webp'
		},
		{
			title: 'Marketing Strategy',
			audience: 'Operators & Agencies',
			description:
				'Benchmark your brand against local competitors. Know which campaigns, channels, and price points are driving results in your market.',
			image: '/ppl/image2.webp'
		},
		{
			title: 'Expansion Planning',
			audience: 'Chains & Investors',
			description:
				'Evaluate locations with foot traffic, demographics, competition density, and rent data side by side. De-risk every new site decision.',
			image: '/ppl/image3.webp'
		},
		{
			title: 'Financial Modelling',
			audience: 'Operators & Investors',
			description:
				'Build projections grounded in real revenue benchmarks, occupancy rates, labor costs, and seasonality patterns — not assumptions.',
			image: '/ppl/image4.webp'
		},
		{
			title: 'Ops & Workforce',
			audience: 'Operators & Chains',
			description:
				'Track how your costs, staffing, and channel performance compare to the local market. Spot inefficiencies before they hit margins.',
			image: '/ppl/image5.webp'
		},
		{
			title: 'Sales & Leads',
			audience: 'Suppliers & Distributors',
			description:
				'Find restaurants that match your ideal customer profile, track new openings in your territory, and time your outreach with real demand signals.',
			image: '/ppl/image6.webp'
		},
		{
			title: 'Due Diligence',
			audience: 'Investors & Advisors',
			description:
				'Verify partners and vet investment opportunities with independent market data — revenue benchmarks, competitive positioning, and local demand signals.',
			image: '/ppl/image7.webp'
		},
		{
			title: 'Enrichment',
			audience: 'Tech Platforms',
			description:
				'Integrate hyper-local restaurant intelligence into your platform via API. Add market context, venue data, and competitive insights to your product.',
			image: '/ppl/image3.webp'
		}
	];

	function scrollTo(index: number) {
		if (!scrollContainer) return;
		if (index === 0) {
			scrollContainer.scrollTo({ left: 0, behavior: 'smooth' });
			return;
		}
		const cards = scrollContainer.querySelectorAll<HTMLElement>('[data-card]');
		if (cards[index]) {
			const card = cards[index];
			const containerLeft = scrollContainer.getBoundingClientRect().left;
			const cardLeft = card.getBoundingClientRect().left;
			const offset = cardLeft - containerLeft + scrollContainer.scrollLeft;
			scrollContainer.scrollTo({ left: offset, behavior: 'smooth' });
		}
	}

	function next() {
		const newIndex = Math.min(activeIndex + 1, useCases.length - 1);
		activeIndex = newIndex;
		scrollTo(newIndex);
	}

	function prev() {
		const newIndex = Math.max(activeIndex - 1, 0);
		activeIndex = newIndex;
		scrollTo(newIndex);
	}

	function onScroll() {
		if (!scrollContainer) return;
		const cards = scrollContainer.querySelectorAll<HTMLElement>('[data-card]');
		const containerLeft = scrollContainer.getBoundingClientRect().left;
		let closest = 0;
		let closestDist = Infinity;
		cards.forEach((card, i) => {
			const dist = Math.abs(card.getBoundingClientRect().left - containerLeft);
			if (dist < closestDist) {
				closestDist = dist;
				closest = i;
			}
		});
		activeIndex = closest;
	}
</script>

{#snippet navButtons()}
	<button
		onclick={prev}
		disabled={activeIndex === 0}
		class="flex h-10 w-10 cursor-pointer items-center justify-center rounded-full border border-gray-200 transition-colors hover:bg-gray-50 disabled:cursor-default disabled:opacity-30"
		aria-label="Previous"
	>
		<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
			<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
		</svg>
	</button>
	<button
		onclick={next}
		disabled={activeIndex === useCases.length - 1}
		class="flex h-10 w-10 cursor-pointer items-center justify-center rounded-full border border-gray-200 transition-colors hover:bg-gray-50 disabled:cursor-default disabled:opacity-30"
		aria-label="Next"
	>
		<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
			<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
		</svg>
	</button>
{/snippet}

{#snippet useCaseGraphic(index: number)}
	{#if index === 0}
		<!-- Market Research: Orbital ellipses -->
		<svg viewBox="0 0 200 200" fill="none" class="graphic-0 w-3/5">
			<line x1="10" y1="100" x2="190" y2="100" stroke="black" stroke-width="0.5" stroke-dasharray="2,3"/>
			<line x1="100" y1="10" x2="100" y2="190" stroke="black" stroke-width="0.5" stroke-dasharray="2,3"/>
			<g class="orbit-1-group">
				<ellipse class="orbit-1" cx="100" cy="100" rx="82" ry="26" stroke="black" stroke-width="1"/>
				<circle cx="18" cy="100" r="1.5" fill="black"/>
				<circle cx="182" cy="100" r="1.5" fill="black"/>
			</g>
			<g class="orbit-2-group">
				<ellipse class="orbit-2" cx="100" cy="100" rx="64" ry="34" stroke="black" stroke-width="1"/>
				<circle cx="145" cy="76" r="1.5" fill="black"/>
			</g>
			<g class="orbit-3-group">
				<ellipse class="orbit-3" cx="100" cy="100" rx="46" ry="20" stroke="black" stroke-width="0.7" stroke-dasharray="4,3"/>
				<circle cx="123" cy="82" r="1.5" fill="black"/>
			</g>
			<circle cx="100" cy="100" r="2.5" fill="black"/>
		</svg>
	{:else if index === 1}
		<!-- Marketing Strategy: Overlapping spotlights / Venn -->
		<svg viewBox="0 0 200 200" fill="none" class="graphic-1 w-3/5">
			<!-- Three overlapping circles -->
			<g class="venn-a">
				<circle cx="78" cy="88" r="52" stroke="black" stroke-width="0.8"/>
				<circle cx="78" cy="36" r="1.5" fill="black"/>
			</g>
			<g class="venn-b">
				<circle cx="122" cy="88" r="48" stroke="black" stroke-width="0.8"/>
				<circle cx="170" cy="88" r="1.5" fill="black"/>
			</g>
			<g class="venn-c">
				<circle class="venn-dash" cx="100" cy="125" r="42" stroke="black" stroke-width="0.7" stroke-dasharray="4,3"/>
				<circle cx="100" cy="167" r="1.5" fill="black"/>
			</g>
			<!-- Intersection marker -->
			<circle cx="100" cy="98" r="2" fill="black"/>
		</svg>
	{:else if index === 2}
		<!-- Expansion Planning: Growth rings -->
		<svg viewBox="0 0 200 200" fill="none" class="graphic-2 w-3/5">
			<g class="ring-1"><rect x="88" y="88" width="24" height="24" stroke="black" stroke-width="1.2" rx="2"/></g>
			<g class="ring-2">
				<rect x="68" y="68" width="64" height="64" stroke="black" stroke-width="1" rx="4"/>
				<circle cx="69" cy="69" r="1.5" fill="black"/>
				<circle cx="131" cy="69" r="1.5" fill="black"/>
				<circle cx="69" cy="131" r="1.5" fill="black"/>
				<circle cx="131" cy="131" r="1.5" fill="black"/>
			</g>
			<g class="ring-3"><rect class="ring-dash-1" x="45" y="45" width="110" height="110" stroke="black" stroke-width="0.8" stroke-dasharray="4,3" rx="6"/></g>
			<g class="ring-4"><rect class="ring-dash-2" x="20" y="20" width="160" height="160" stroke="black" stroke-width="0.5" stroke-dasharray="2,3" rx="8"/></g>
			<circle cx="100" cy="100" r="2" fill="black"/>
			<line x1="100" y1="20" x2="100" y2="88" stroke="black" stroke-width="0.4" stroke-dasharray="2,3"/>
			<line x1="100" y1="112" x2="100" y2="180" stroke="black" stroke-width="0.4" stroke-dasharray="2,3"/>
			<line x1="20" y1="100" x2="88" y2="100" stroke="black" stroke-width="0.4" stroke-dasharray="2,3"/>
			<line x1="112" y1="100" x2="180" y2="100" stroke="black" stroke-width="0.4" stroke-dasharray="2,3"/>
		</svg>
	{:else if index === 3}
		<!-- Financial Modelling: Wave curves -->
		<svg viewBox="0 0 200 200" fill="none" class="graphic-3 w-3/5">
			<line x1="10" y1="110" x2="190" y2="110" stroke="black" stroke-width="0.5"/>
			<line x1="20" y1="110" x2="20" y2="40" stroke="black" stroke-width="0.5"/>
			<g class="wave-solid-group">
				<path class="wave-solid" d="M 20,110 C 55,55 75,55 110,110 S 165,165 190,110" stroke="black" stroke-width="1"/>
				<circle cx="65" cy="69" r="1.5" fill="black"/>
				<circle cx="110" cy="110" r="2" fill="black"/>
			</g>
			<g class="wave-dash-group">
				<path class="wave-dash" d="M 20,125 C 60,75 90,75 120,110 S 170,145 190,100" stroke="black" stroke-width="0.7" stroke-dasharray="4,3"/>
				<circle cx="155" cy="135" r="1.5" fill="black"/>
			</g>
			<line x1="65" y1="65" x2="65" y2="155" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/>
			<line x1="110" y1="65" x2="110" y2="155" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/>
			<line x1="155" y1="65" x2="155" y2="155" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/>
		</svg>
	{:else if index === 4}
		<!-- Ops & Workforce: Gantt / shift schedule -->
		<svg viewBox="0 0 200 200" fill="none" class="graphic-4 w-3/5">
			<!-- Vertical time markers -->
			<line x1="40" y1="25" x2="40" y2="180" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/>
			<line x1="80" y1="25" x2="80" y2="180" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/>
			<line x1="120" y1="25" x2="120" y2="180" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/>
			<line x1="160" y1="25" x2="160" y2="180" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/>
			<!-- Schedule bars with edge markers -->
			<g class="gantt-row-1"><rect x="25" y="32" width="95" height="10" rx="2" stroke="black" stroke-width="1"/><circle cx="25" cy="37" r="1.5" fill="black"/></g>
			<g class="gantt-row-2"><rect x="55" y="55" width="50" height="10" rx="2" stroke="black" stroke-width="1"/><circle cx="55" cy="60" r="1.5" fill="black"/></g>
			<g class="gantt-row-3"><rect class="gantt-dash-fwd" x="80" y="78" width="90" height="10" rx="2" stroke="black" stroke-width="0.8" stroke-dasharray="4,3"/><circle cx="80" cy="83" r="1.5" fill="black"/></g>
			<g class="gantt-row-4"><rect x="25" y="101" width="55" height="10" rx="2" stroke="black" stroke-width="1"/><circle cx="25" cy="106" r="1.5" fill="black"/><rect x="100" y="101" width="75" height="10" rx="2" stroke="black" stroke-width="0.8"/><circle cx="100" cy="106" r="1.5" fill="black"/></g>
			<g class="gantt-row-5"><rect class="gantt-dash-rev" x="40" y="124" width="135" height="10" rx="2" stroke="black" stroke-width="0.7" stroke-dasharray="4,3"/><circle cx="40" cy="129" r="1.5" fill="black"/></g>
			<g class="gantt-row-6"><rect x="25" y="147" width="60" height="10" rx="2" stroke="black" stroke-width="1"/><circle cx="25" cy="152" r="1.5" fill="black"/><rect x="110" y="147" width="65" height="10" rx="2" stroke="black" stroke-width="0.8"/><circle cx="110" cy="152" r="1.5" fill="black"/></g>
		</svg>
	{:else if index === 5}
		<!-- Sales & Leads: CRM network graph -->
		<svg viewBox="0 0 200 200" fill="none" class="graphic-5 w-3/5">
			<!-- Central hub -->
			<circle cx="100" cy="100" r="6" stroke="black" stroke-width="1.2"/>
			<circle cx="100" cy="100" r="2" fill="black"/>
			<!-- Node clusters: line + node + secondary connections grouped -->
			<g class="node-a">
				<line x1="95" y1="96" x2="41" y2="54" stroke="black" stroke-width="0.8"/>
				<circle cx="38" cy="52" r="4" stroke="black" stroke-width="0.8"/>
			</g>
			<g class="node-b">
				<line x1="104" y1="96" x2="156" y2="46" stroke="black" stroke-width="0.8"/>
				<circle cx="160" cy="42" r="5" stroke="black" stroke-width="0.8"/>
			</g>
			<g class="node-c">
				<line class="crm-dash" x1="106" y1="100" x2="169" y2="98" stroke="black" stroke-width="0.7" stroke-dasharray="4,3"/>
				<circle cx="172" cy="98" r="3" stroke="black" stroke-width="0.7"/>
			</g>
			<g class="node-d">
				<line x1="104" y1="104" x2="149" y2="155" stroke="black" stroke-width="0.8"/>
				<circle cx="152" cy="158" r="4.5" stroke="black" stroke-width="0.8"/>
			</g>
			<g class="node-e">
				<line class="crm-dash" x1="96" y1="104" x2="51" y2="150" stroke="black" stroke-width="0.7" stroke-dasharray="4,3"/>
				<circle cx="48" cy="152" r="3.5" stroke="black" stroke-width="0.7"/>
			</g>
			<g class="node-f">
				<line x1="94" y1="101" x2="33" y2="114" stroke="black" stroke-width="0.8"/>
				<circle cx="30" cy="115" r="3" stroke="black" stroke-width="0.8"/>
			</g>
			<g class="node-g">
				<line class="crm-dash" x1="98" y1="94" x2="79" y2="30" stroke="black" stroke-width="0.7" stroke-dasharray="4,3"/>
				<circle cx="78" cy="28" r="2.5" stroke="black" stroke-width="0.7"/>
			</g>
			<g class="node-h">
				<line class="crm-dash" x1="105" y1="104" x2="166" y2="150" stroke="black" stroke-width="0.7" stroke-dasharray="4,3"/>
				<circle cx="168" cy="152" r="3" stroke="black" stroke-width="0.7"/>
			</g>
			<!-- Secondary connections -->
			<g class="link-bc"><line x1="161" y1="47" x2="171" y2="95" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/></g>
			<g class="link-ef"><line x1="31" y1="118" x2="46" y2="149" stroke="black" stroke-width="0.3" stroke-dasharray="2,3"/></g>
		</svg>
	{:else if index === 6}
		<!-- Due Diligence: Concentric circles with sweep -->
		<svg viewBox="0 0 200 200" fill="none" class="graphic-6 w-3/5">
			<circle class="dd-dash-inner" cx="100" cy="100" r="20" stroke="black" stroke-width="0.5" stroke-dasharray="2,3"/>
			<circle cx="100" cy="100" r="40" stroke="black" stroke-width="0.7"/>
			<circle cx="100" cy="100" r="60" stroke="black" stroke-width="0.7"/>
			<circle class="dd-dash-outer" cx="100" cy="100" r="80" stroke="black" stroke-width="0.5" stroke-dasharray="3,3"/>
			<path d="M 100,20 A 80,80 0 0,1 174,68" stroke="black" stroke-width="2.5"/>
			<path d="M 100,40 A 60,60 0 0,1 152,72" stroke="black" stroke-width="1.8"/>
			<circle cx="100" cy="100" r="2" fill="black"/>
			<circle cx="100" cy="20" r="1.5" fill="black"/>
			<circle cx="174" cy="68" r="1.5" fill="black"/>
			<circle cx="140" cy="100" r="1.5" fill="black"/>
		</svg>
	{:else if index === 7}
		<!-- Enrichment: Vertically stacked isometric layers -->
		<svg viewBox="0 0 200 200" fill="none" class="graphic-7 w-3/5">
			<g class="enrich-layer-1">
				<path class="enrich-dash" d="M 100,28 L 170,58 L 100,88 L 30,58 Z" stroke="black" stroke-width="0.5" stroke-dasharray="3,3"/>
				<circle cx="135" cy="43" r="1.5" fill="black"/>
			</g>
			<g class="enrich-layer-2">
				<path d="M 100,58 L 170,88 L 100,118 L 30,88 Z" stroke="black" stroke-width="0.7"/>
				<circle cx="130" cy="71" r="1.5" fill="black"/>
			</g>
			<g class="enrich-layer-3">
				<path d="M 100,88 L 170,118 L 100,148 L 30,118 Z" stroke="black" stroke-width="0.8"/>
				<circle cx="70" cy="101" r="1.5" fill="black"/>
			</g>
			<g class="enrich-layer-4">
				<path d="M 100,118 L 170,148 L 100,178 L 30,148 Z" stroke="black" stroke-width="1"/>
				<circle cx="120" cy="127" r="1.5" fill="black"/>
				<circle cx="80" cy="169" r="1.5" fill="black"/>
			</g>
			<!-- Vertical axis -->
			<line x1="100" y1="20" x2="100" y2="185" stroke="black" stroke-width="0.4" stroke-dasharray="2,3"/>
		</svg>
	{/if}
{/snippet}

<section id="use-cases" class="border-t border-gray-200 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<div class="mb-12 flex items-end justify-between">
			<div>
				<p class="mb-6 text-sm font-medium uppercase tracking-widest text-black/40">Use Cases</p>
				<h2
					class="max-w-xl text-[clamp(2rem,4vw,3.25rem)] leading-[1.1] font-normal tracking-[-0.02em] text-black"
				>
					Supporting teams across all roles and functions
				</h2>
			</div>

			<div class="hidden items-center gap-2 md:flex">
				{@render navButtons()}
			</div>
		</div>
	</div>

	<div
		bind:this={scrollContainer}
		onscroll={onScroll}
		class="scrollbar-hide flex gap-5 overflow-x-auto scroll-smooth"
	>
		{#each useCases as useCase, i (useCase.title)}
			<div
				data-card
				class="group w-[min(75vw,380px)] flex-shrink-0"
				style="{i === 0 ? 'margin-left: var(--content-inset)' : ''}{i === useCases.length - 1 ? 'margin-right: var(--content-inset)' : ''}"
			>
				<div
					class="mb-5 flex aspect-[4/3] items-center justify-center overflow-hidden rounded-2xl bg-[#f5f4f2]"
				>
					{@render useCaseGraphic(i)}
				</div>

				<p class="mb-1 text-xs font-medium text-black/30">{useCase.audience}</p>
				<h3 class="mb-2 text-lg font-semibold tracking-[-0.01em] text-black">
					{useCase.title}
				</h3>
				<p class="pr-4 text-sm leading-snug text-black/50">
					{useCase.description}
				</p>
			</div>
		{/each}
	</div>

	<div class="mt-8 flex items-center justify-center gap-2 md:hidden">
		{@render navButtons()}
	</div>
</section>

<style>
	section {
		--content-inset: max(24px, calc((100% - 1200px) / 2 + 24px));
	}
	.scrollbar-hide {
		-ms-overflow-style: none;
		scrollbar-width: none;
	}
	.scrollbar-hide::-webkit-scrollbar {
		display: none;
	}

	/* Market Research: orbits shift and rescale */
	:global(.graphic-0 .orbit-1-group) {
		transform: rotate(-30deg);
		transform-origin: 100px 100px;
		transition: transform 0.7s cubic-bezier(0.4, 0, 0.2, 1);
	}
	:global(.graphic-0 .orbit-2-group) {
		transform: rotate(25deg);
		transform-origin: 100px 100px;
		transition: transform 0.8s cubic-bezier(0.4, 0, 0.2, 1);
	}
	:global(.graphic-0 .orbit-3-group) {
		transform: rotate(75deg);
		transform-origin: 100px 100px;
		transition: transform 0.9s cubic-bezier(0.4, 0, 0.2, 1);
	}
	:global(.graphic-0 .orbit-3) {
		stroke-dashoffset: 0;
		transition: stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1);
	}
	:global(.group:hover .graphic-0 .orbit-3) {
		stroke-dashoffset: -21;
	}
	:global(.group:hover .graphic-0 .orbit-1-group) {
		transform: rotate(-42deg) scaleX(0.92) scaleY(1.1);
	}
	:global(.group:hover .graphic-0 .orbit-2-group) {
		transform: rotate(18deg) scaleX(1.08) scaleY(0.9);
	}
	:global(.group:hover .graphic-0 .orbit-3-group) {
		transform: rotate(88deg) scaleX(0.9) scaleY(1.12);
	}

	/* Marketing Strategy: circles drift apart + resize */
	:global(.group .graphic-1 .venn-a) {
		transform-origin: 78px 88px;
		transition: transform 0.6s cubic-bezier(0.4, 0, 0.2, 1);
	}
	:global(.group .graphic-1 .venn-b) {
		transform-origin: 122px 88px;
		transition: transform 0.7s cubic-bezier(0.4, 0, 0.2, 1);
	}
	:global(.group .graphic-1 .venn-c) {
		transform-origin: 100px 125px;
		transition: transform 0.8s cubic-bezier(0.4, 0, 0.2, 1);
	}
	:global(.group:hover .graphic-1 .venn-a) { transform: translate(-4px, -3px) scale(1.06); }
	:global(.group:hover .graphic-1 .venn-b) { transform: translate(4px, -3px) scale(0.92); }
	:global(.group:hover .graphic-1 .venn-c) { transform: translate(0, 5px) scale(1.08); }
	:global(.group .graphic-1 .venn-dash) {
		stroke-dashoffset: 0;
		transition: stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1);
	}
	:global(.group:hover .graphic-1 .venn-dash) {
		stroke-dashoffset: -21;
	}

	/* Expansion Planning: rings scale outward */
	:global(.group .graphic-2 g[class^="ring-"]) {
		transition: transform 0.5s ease;
		transform-origin: 100px 100px;
	}
	:global(.group:hover .graphic-2 .ring-1) { transform: scale(1); }
	:global(.group:hover .graphic-2 .ring-2) { transform: scale(1); }
	:global(.group:hover .graphic-2 .ring-3) { transform: scale(1.018); }
	:global(.group:hover .graphic-2 .ring-4) { transform: scale(1); }
	:global(.group .graphic-2 .ring-dash-1),
	:global(.group .graphic-2 .ring-dash-2) {
		stroke-dashoffset: 0;
		transition: stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1);
	}
	:global(.group:hover .graphic-2 .ring-dash-1) {
		stroke-dashoffset: -21;
	}
	:global(.group:hover .graphic-2 .ring-dash-2) {
		stroke-dashoffset: 15;
	}

	/* Financial Modelling: waves undulate */
	:global(.group .graphic-3 .wave-solid-group) {
		transform-origin: 105px 110px;
		transform: scaleY(1) scaleX(1);
		transition: transform 0.8s ease-in-out;
	}
	:global(.group:hover .graphic-3 .wave-solid-group) {
		transform: scaleY(1.12) scaleX(0.98);
	}
	:global(.group .graphic-3 .wave-dash-group) {
		transform-origin: 105px 110px;
		transform: scaleY(1) scaleX(1);
		transition: transform 0.9s ease-in-out;
	}
	:global(.group:hover .graphic-3 .wave-dash-group) {
		transform: scaleY(0.88) scaleX(1.02);
	}
	:global(.group .graphic-3 .wave-dash) {
		stroke-dashoffset: 0;
		transition: stroke-dashoffset 0.9s cubic-bezier(0.4, 0, 0.2, 1);
	}
	:global(.group:hover .graphic-3 .wave-dash) {
		stroke-dashoffset: -21;
	}

	/* Ops & Workforce: subtle bar resize + ants on dashed */
	:global(.group .graphic-4 g[class^="gantt-row"]) {
		transition: transform 0.5s ease;
	}
	:global(.group:hover .graphic-4 .gantt-row-1) {
		transform: scaleX(1.08);
	}
	:global(.group:hover .graphic-4 .gantt-row-4) {
		transform: scaleX(0.92);
	}
	:global(.group .graphic-4 .gantt-dash-fwd),
	:global(.group .graphic-4 .gantt-dash-rev) {
		stroke-dashoffset: 0;
		transition: transform 0.5s ease, stroke-dashoffset 0.7s cubic-bezier(0.4, 0, 0.2, 1);
	}
	:global(.group:hover .graphic-4 .gantt-dash-fwd) {
		stroke-dashoffset: -14;
	}
	:global(.group:hover .graphic-4 .gantt-dash-rev) {
		stroke-dashoffset: 14;
	}

	/* Sales & Leads: nodes scale outward from hub */
	:global(.group .graphic-5 g[class^="node-"]) {
		transition: transform 0.5s ease;
		transform-origin: 100px 100px;
	}
	:global(.group:hover .graphic-5 .node-a) { transform: scale(1.1); }
	:global(.group:hover .graphic-5 .node-b) { transform: scale(1.08); }
	:global(.group:hover .graphic-5 .node-c) { transform: scale(1.08); }
	:global(.group:hover .graphic-5 .node-d) { transform: scale(1.07); }
	:global(.group:hover .graphic-5 .node-e) { transform: scale(1.09); }
	:global(.group:hover .graphic-5 .node-f) { transform: scale(1.11); }
	:global(.group:hover .graphic-5 .node-g) { transform: scale(1.05); }
	:global(.group:hover .graphic-5 .node-h) { transform: scale(1.08); }
	/* Ants on dashed connection lines */
	:global(.group .graphic-5 .crm-dash) {
		stroke-dashoffset: 0;
		transition: stroke-dashoffset 0.7s cubic-bezier(0.4, 0, 0.2, 1);
	}
	:global(.group:hover .graphic-5 .crm-dash) {
		stroke-dashoffset: -14;
	}
	/* Secondary links scale from hub to match connected nodes */
	:global(.group .graphic-5 .link-bc),
	:global(.group .graphic-5 .link-ef) {
		transition: transform 0.5s ease;
		transform-origin: 100px 100px;
	}
	:global(.group:hover .graphic-5 .link-bc) { transform: scale(1.08); }
	:global(.group:hover .graphic-5 .link-ef) { transform: scale(1.10); }

	/* Due Diligence: sweep arcs rotate + ants on dashed circles */
	:global(.group .graphic-6 path) {
		transition: transform 0.6s ease;
		transform-origin: 100px 100px;
	}
	:global(.group:hover .graphic-6 path:nth-of-type(1)) {
		transform: rotate(15deg);
	}
	:global(.group:hover .graphic-6 path:nth-of-type(2)) {
		transform: rotate(10deg);
	}
	:global(.group .graphic-6 .dd-dash-inner),
	:global(.group .graphic-6 .dd-dash-outer) {
		stroke-dashoffset: 0;
		transition: stroke-dashoffset 0.7s cubic-bezier(0.4, 0, 0.2, 1);
	}
	:global(.group:hover .graphic-6 .dd-dash-inner) {
		stroke-dashoffset: -15;
	}
	:global(.group:hover .graphic-6 .dd-dash-outer) {
		stroke-dashoffset: 18;
	}

	/* Enrichment: layers compress together + ants */
	:global(.group .graphic-7 g[class^="enrich-layer"]) {
		transition: transform 0.5s ease;
	}
	:global(.group:hover .graphic-7 .enrich-layer-1) { transform: translateY(8px); }
	:global(.group:hover .graphic-7 .enrich-layer-2) { transform: translateY(4px); }
	:global(.group:hover .graphic-7 .enrich-layer-3) { transform: translateY(-4px); }
	:global(.group:hover .graphic-7 .enrich-layer-4) { transform: translateY(-8px); }
	:global(.group .graphic-7 .enrich-dash) {
		stroke-dashoffset: 0;
		transition: stroke-dashoffset 0.7s cubic-bezier(0.4, 0, 0.2, 1);
	}
	:global(.group:hover .graphic-7 .enrich-dash) {
		stroke-dashoffset: -18;
	}
</style>
