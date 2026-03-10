<script lang="ts">
	const faqs = [
		{
			question: 'What types of restaurants is Superextra built for?',
			answer: 'Superextra is built for every segment of the restaurant industry — from independent operators and fast-casual chains to fine dining groups and enterprise brands. Whether you run a single location or hundreds, our intelligence adapts to your scale and needs.'
		},
		{
			question: 'How is the data collected and how accurate is it?',
			answer: 'We aggregate data from dozens of public and proprietary sources including review platforms, delivery apps, foot traffic sensors, real estate databases, public filings, and more. Our AI models cross-reference and validate data in real time to deliver the most accurate picture of your market.'
		},
		{
			question: 'How hyper-local is the intelligence?',
			answer: 'Extremely. We map intelligence down to 1-mile trade areas, allowing you to understand the competitive dynamics of your exact neighborhood — not just your city or zip code. This is the granularity that makes Superextra different.'
		},
		{
			question: 'Can I benchmark against specific competitors?',
			answer: 'Yes. You can select specific competitors to build custom benchmarking sets, or let our AI automatically identify your most relevant competitive set based on concept, cuisine, price point, and proximity.'
		},
		{
			question: 'What does pricing look like?',
			answer: "We offer flexible plans based on the number of locations and depth of intelligence you need. Early access users get preferential pricing. Reach out to our team to learn more about the plan that fits your business."
		},
		{
			question: 'How is this different from existing market research?',
			answer: "Traditional market research is expensive, slow, and generic. Superextra delivers always-on, hyper-local intelligence that updates in real time and is specifically built for restaurant decision-making. Think of it as the Bloomberg Terminal for the restaurant industry."
		}
	];

	let openIndex = $state(-1);
</script>

<section id="faq" class="border-t border-gray-200 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<div class="grid grid-cols-1 gap-12 lg:grid-cols-[1fr_1.5fr] lg:gap-20">
			<div>
				<p class="mb-6 text-sm font-medium uppercase tracking-widest text-black/40">
					FAQ
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
							<p class="pb-6 text-sm leading-relaxed text-black/50">
								{faq.answer}
							</p>
						{/if}
					</button>
				{/each}
			</div>
		</div>

		<!-- CTA below FAQ like ElevenLabs -->
		<div class="mt-12">
			<a
				href="https://superextra.ai"
				class="inline-flex items-center gap-2 rounded-full bg-black px-8 py-3.5 text-sm font-medium text-white transition-colors hover:bg-black/80"
			>
				Get Early Access
			</a>
		</div>
	</div>
</section>
