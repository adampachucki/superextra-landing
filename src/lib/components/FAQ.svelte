<script lang="ts">
	import SectionHeader from './SectionHeader.svelte';
	import * as m from '$lib/paraglide/messages';

	let {
		items
	}: {
		items?: { question: string; answer: string }[];
	} = $props();

	const defaultFaqs = [
		{ question: m.faq_q1(), answer: m.faq_a1() },
		{ question: m.faq_q2(), answer: m.faq_a2() },
		{ question: m.faq_q3(), answer: m.faq_a3() },
		{ question: m.faq_q4(), answer: m.faq_a4() },
		{ question: m.faq_q5(), answer: m.faq_a5() },
		{ question: m.faq_q6(), answer: m.faq_a6() },
		{ question: m.faq_q7(), answer: m.faq_a7() },
		{ question: m.faq_q8(), answer: m.faq_a8() }
	];

	let faqs = $derived(items ?? defaultFaqs);
	let openIndex = $state(-1);
</script>

<section id="faq" class="bg-cream-100 py-24 md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<div class="grid grid-cols-1 gap-12 lg:grid-cols-[1fr_1.5fr] lg:gap-20">
			<div>
				<SectionHeader subtitle={m.faq_subtitle()} title={m.faq_title()} />
			</div>

			<div class="divide-y divide-cream-200 border-t border-cream-200">
				{#each faqs as faq, i (faq.question)}
					<div>
						<button
							class="group flex w-full items-center justify-between py-5 text-left"
							aria-expanded={openIndex === i}
							aria-controls="faq-answer-{i}"
							onclick={() => (openIndex = openIndex === i ? -1 : i)}
						>
							<h3
								class="pr-8 text-base font-medium transition-colors {openIndex === i
									? 'text-black dark:text-white'
									: 'text-black/60 group-hover:text-black dark:text-white/60 dark:group-hover:text-white'}"
							>
								{faq.question}
							</h3>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								class="h-5 w-5 shrink-0 text-black/25 transition-transform duration-300 dark:text-white/25 {openIndex ===
								i
									? 'rotate-45'
									: ''}"
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
								stroke-width="1.5"
							>
								<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
							</svg>
						</button>
						<div
							id="faq-answer-{i}"
							role="region"
							class="grid transition-[grid-template-rows] duration-300 {openIndex === i
								? 'grid-rows-[1fr]'
								: 'grid-rows-[0fr]'}"
						>
							<div class="overflow-hidden">
								<p class="pb-6 text-sm leading-snug text-black/60 dark:text-white/60">
									{faq.answer}
								</p>
							</div>
						</div>
					</div>
				{/each}
			</div>
		</div>
	</div>
</section>
