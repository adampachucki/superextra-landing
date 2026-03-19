<script lang="ts">
	const faqs = [
		{
			question: 'What types of restaurants is Superextra built for?',
			answer: "Superextra is built for every segment of the restaurant industry — from independent operators and fast-casual concepts to fine dining groups and growing multi-unit brands. It's also used by suppliers, tech platforms, agencies, and investors who need restaurant market intelligence."
		},
		{
			question: 'How is the data collected and how accurate is it?',
			answer: 'Superextra aggregates data from dozens of public and proprietary sources including review platforms, delivery apps, foot traffic providers, real estate databases, public filings, and more. AI models cross-reference and validate data continuously to deliver the most accurate picture of the market.'
		},
		{
			question: 'How reliable are the AI agents? Do they hallucinate?',
			answer: "Superextra agents are built to report facts, not generate them. Every insight is grounded in real data. When information isn't available, the agent flags it as missing rather than inventing an answer."
		},
		{
			question: 'Does Superextra connect to my POS or internal systems?',
			answer: "No — and that's by design. Superextra brings the market data to you, so there's no integration required. Think of it as an external intelligence layer: all the competitive, location, and industry data you need without sharing any of your own."
		},
		{
			question: 'What markets and geographies are covered?',
			answer: 'Superextra is launching with deep coverage in select European markets and expanding rapidly. If you want to check availability for a specific region, reach out to the team.'
		},
		{
			question: 'How hyper-local is the intelligence?',
			answer: 'Extremely. Intelligence is mapped down to precise trade areas, so you can understand the competitive dynamics of your exact neighborhood — not just a city or zip code. That granularity is what makes Superextra different.'
		},
		{
			question: 'Can I benchmark against specific competitors?',
			answer: 'Superextra uses cohort-based benchmarking rather than direct competitor comparisons. Performance is measured against relevant peer groups based on cuisine, price point, format, and location — giving a more reliable and statistically meaningful picture than one-to-one comparisons.'
		},
		{
			question: 'What does pricing look like?',
			answer: "Flexible plans based on the number of locations and depth of intelligence needed. Early access users get preferential pricing. Reach out to learn more about the plan that fits best."
		}
	];

	let openIndex = $state(-1);
</script>

<section id="faq" class="border-t border-gray-200 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<div class="grid grid-cols-1 gap-12 lg:grid-cols-[1fr_1.5fr] lg:gap-20">
			<div>
				<p class="mb-6 text-sm font-medium uppercase tracking-widest text-black/40">
					Learn More
				</p>
				<h2 class="text-[clamp(2rem,4vw,3.25rem)] leading-[1.1] font-normal tracking-[-0.02em] text-black">
					Frequently asked questions
				</h2>
			</div>

			<div class="divide-y divide-gray-200 border-t border-gray-200">
				{#each faqs as faq, i}
					<button
						class="group w-full cursor-pointer text-left"
						onclick={() => (openIndex = openIndex === i ? -1 : i)}
					>
						<div class="flex items-center justify-between py-5">
							<h3 class="pr-8 text-base font-semibold transition-colors {openIndex === i ? 'text-black' : 'text-black/60 group-hover:text-black'}">
								{faq.question}
							</h3>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								class="h-5 w-5 shrink-0 text-black/30 transition-transform duration-300 {openIndex === i ? 'rotate-45' : ''}"
								fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"
							>
								<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
							</svg>
						</div>
						{#if openIndex === i}
							<p class="pb-6 text-sm leading-snug text-black/50">
								{faq.answer}
							</p>
						{/if}
					</button>
				{/each}
			</div>
		</div>
	</div>
</section>
