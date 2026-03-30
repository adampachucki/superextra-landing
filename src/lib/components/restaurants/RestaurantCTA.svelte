<script lang="ts">
	function scrollToPrompt() {
		const textarea = document.querySelector<HTMLTextAreaElement>('textarea[autofocus]');
		if (textarea) {
			textarea.scrollIntoView({ behavior: 'smooth', block: 'center' });
			setTimeout(() => textarea.focus(), 500);
		}
	}
</script>

<section class="bg-cream-100 py-24 md:py-32">
	<div class="mx-auto max-w-2xl px-6 text-center">
		<h2 class="text-[clamp(1.75rem,3.5vw,2.75rem)] leading-[1.1] font-medium tracking-[-0.02em] text-black dark:text-white">
			Start with a question
		</h2>
		<p class="mt-4 text-lg text-black/50 dark:text-white/50">
			Limited early access is now open.
		</p>
		<button
			onclick={scrollToPrompt}
			aria-label="Scroll to prompt"
			class="mt-8 inline-flex cursor-pointer items-center justify-center rounded-full bg-black p-4 transition-colors hover:bg-black/80 dark:bg-white dark:hover:bg-white/80"
		>
			<svg class="h-5 w-5 text-white dark:text-black" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
				<path stroke-linecap="round" stroke-linejoin="round" d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" />
			</svg>
		</button>
	</div>
</section>
