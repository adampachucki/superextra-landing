<script lang="ts">
	let {
		headline = 'The market view restaurants have been missing',
		intro = 'Restaurants make critical decisions every day — where to open, how to price, when to hire — too often without a clear view of the market around them at all. Superextra changes that.',
		description = 'Our AI models synthesize competitor, pricing, guest, delivery, and market signals into an external intelligence layer for restaurants and the partners around them — from operators to suppliers and tech platforms. Better context behind better decisions.',
		class: className = ''
	}: {
		headline?: string;
		intro?: string;
		description?: string;
		class?: string;
	} = $props();
</script>

<section class="py-24 md:py-32 {className}">
	<div class="mx-auto max-w-[1200px] px-6">
		<p class="mb-6 text-sm font-medium tracking-widest text-black/40 uppercase dark:text-white/40">
			About Superextra
		</p>

		<div class="grid grid-cols-1 gap-12 lg:grid-cols-2 lg:gap-20">
			<h2
				class="text-[clamp(2rem,4vw,3.25rem)] leading-[1.1] font-normal tracking-[-0.02em] text-black dark:text-white"
			>
				{headline}
			</h2>

			<div class="space-y-6">
				<p class="text-lg leading-snug text-black/60 dark:text-white/60">
					{intro}
				</p>
				<p class="text-lg leading-snug text-black/60 dark:text-white/60">
					{description}
				</p>
				<p class="text-lg leading-snug font-medium text-black dark:text-white">
					Super intelligence. Extra advantage.
				</p>
			</div>
		</div>
	</div>
</section>
