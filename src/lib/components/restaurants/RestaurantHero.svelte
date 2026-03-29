<script lang="ts">
	import { formState } from '$lib/form-state.svelte';

	const PREFIX = 'Ask Superextra ';
	const PROMPTS = [
		'to compare prices in your area...',
		'to analyze competitor reviews...',
		'how was last month for others...',
		'where to open next...',
		'what line cooks earn nearby...',
		'which platforms perform best...'
	];
	const TYPE_MS = 45;
	const DELETE_MS = 25;
	const HOLD_MS = 2200;
	const PAUSE_MS = 400;

	let display = $state(PREFIX);
	let userQuery = $state('');
	let inputEl: HTMLTextAreaElement | undefined = $state();

	let isAnimating = $derived(!userQuery && display.length > 0);

	$effect(() => {
		if (userQuery) return;

		let timeout: ReturnType<typeof setTimeout>;
		let cancelled = false;
		let idx = 0;

		function sleep(ms: number) {
			return new Promise<void>((r) => {
				timeout = setTimeout(r, ms);
			});
		}

		async function run() {
			while (!cancelled) {
				const text = PROMPTS[idx % PROMPTS.length];

				for (let i = 1; i <= text.length; i++) {
					if (cancelled) return;
					display = PREFIX + text.slice(0, i);
					await sleep(TYPE_MS);
				}

				await sleep(HOLD_MS);

				for (let i = text.length - 1; i >= 0; i--) {
					if (cancelled) return;
					display = PREFIX + text.slice(0, i);
					await sleep(DELETE_MS);
				}

				await sleep(PAUSE_MS);
				idx++;
			}
		}

		run();

		return () => {
			cancelled = true;
			clearTimeout(timeout);
		};
	});

	function handleExplore() {
		formState.open();
	}

	const topics = [
		{ label: 'Menu price gaps', color: '#6ee7b3', query: 'How does our menu pricing compare to competitors within a mile?' },
		{ label: "Who's getting the traffic", color: '#a78bfa', query: 'What are the foot traffic patterns in my neighbourhood by day and daypart?' },
		{ label: 'Salary benchmarks', color: '#f472b6', query: 'What are restaurants near us actually paying for every role?' },
		{ label: 'What guests are saying', color: '#fbbf24', query: 'What are the real sentiment themes across our reviews and competitors?' },
		{ label: 'Who just opened nearby', color: '#06b6d4', query: 'What new restaurants have opened or closed in my area recently?' },
		{ label: 'Market-wide sales shifts', color: '#818cf8', query: 'Is a slow month just us or is the whole neighbourhood pulling back?' }
	];

	function resizeTextarea() {
		if (inputEl) {
			inputEl.style.height = 'auto';
			inputEl.style.height = inputEl.scrollHeight + 'px';
		}
	}

	$effect(() => {
		userQuery;
		resizeTextarea();
	});

	function selectTopic(query: string) {
		userQuery = query;
		inputEl?.focus();
	}
</script>

<section class="pt-32 md:pt-40">
	<div class="mx-auto max-w-[1200px] px-6">
		<!-- Headline -->
		<h1
			class="hero-fade mx-auto text-center font-semibold tracking-[-0.03em] text-black dark:text-white"
			style="max-width: 14ch; font-size: clamp(2.75rem, 6vw, 5.25rem); line-height: 1.02; animation-delay: 100ms;"
		>
			A market analyst <br />for every restaurant
		</h1>

		<!-- Subheadline -->
		<p class="hero-fade mx-auto mt-6 text-center text-xl leading-relaxed text-black/45 dark:text-white/45" style="max-width: 540px; animation-delay: 170ms;">
			Stop relying on gossip and gut feel. Get clear answers about your competitors, pricing, and demand in minutes.
		</p>

		<!-- Prompt card -->
		<div class="prompt-fade mx-auto mt-10 md:mt-12" style="max-width: 650px; animation-delay: 280ms;">
			<div class="prompt-card overflow-hidden rounded-2xl border border-black/[0.06] bg-white dark:border-white/[0.06] dark:bg-cream-50">
				<div class="flex items-center gap-3 border-b border-black/[0.04] px-5 dark:border-white/[0.06]">
					<!-- svelte-ignore a11y_autofocus -->
					<input
						type="text"
						autofocus
						placeholder="Restaurant name or location..."
						class="w-full border-0 bg-transparent py-4 text-[15px] text-black placeholder:text-black/25 focus:outline-none dark:text-white dark:placeholder:text-white/25"
					/>
				</div>
				<div class="flex items-start gap-3 px-5 py-4">
					<textarea
						bind:this={inputEl}
						bind:value={userQuery}
						onfocus={() => {}}
						placeholder={isAnimating ? display : 'What do you want to know about your market?'}
						rows="1"
						class="w-full resize-none border-0 bg-transparent text-[15px] leading-relaxed text-black focus:outline-none dark:text-white {isAnimating ? 'placeholder:text-black/70 dark:placeholder:text-white/70' : 'placeholder:text-black/25 dark:placeholder:text-white/25'}"
					></textarea>

					<button onclick={handleExplore} aria-label="Explore" class="mt-0.5 cursor-pointer shrink-0 rounded-full bg-black p-2 transition-colors hover:bg-black/80 dark:bg-white dark:hover:bg-white/80">
						<svg class="h-4 w-4 text-white dark:text-black" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
							<path stroke-linecap="round" stroke-linejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
						</svg>
					</button>
				</div>
			</div>
		</div>

		<!-- Topic suggestion pills -->
		<div class="topic-row mx-auto mt-12 flex gap-2 overflow-x-auto pb-1 md:mt-12" style="max-width: 900px;">
			{#each topics as topic, i}
				<button
					onclick={() => selectTopic(topic.query)}
					class="topic-pill inline-flex shrink-0 cursor-pointer items-center gap-2 whitespace-nowrap rounded-full border border-black/[0.06] px-3.5 py-2 text-[13px] text-black/40 transition-all hover:border-black/[0.12] hover:text-black/60 dark:border-white/[0.06] dark:text-white/40 dark:hover:border-white/[0.12] dark:hover:text-white/60"
					style="animation-delay: {380 + i * 40}ms"
				>
					<span class="h-1.5 w-1.5 shrink-0 rounded-full" style="background-color: {topic.color}"></span>
					{topic.label}
				</button>
			{/each}
		</div>
	</div>
</section>

<div class="h-24 md:h-36"></div>

<style>
	.hero-fade {
		animation: fadeIn 0.7s ease-out both;
	}

	@keyframes fadeIn {
		from { opacity: 0; transform: translateY(8px); }
		to { opacity: 1; transform: translateY(0); }
	}

	.prompt-fade {
		animation: fadeIn 0.6s ease-out both;
	}

	.prompt-card {
		box-shadow:
			0 0 0 1px rgba(0, 0, 0, 0.03),
			0 1px 2px rgba(0, 0, 0, 0.02),
			0 8px 32px rgba(0, 0, 0, 0.06);
	}

	:global(.dark) .prompt-card {
		box-shadow:
			0 0 0 1px rgba(255, 255, 255, 0.06),
			0 1px 2px rgba(0, 0, 0, 0.1),
			0 8px 32px rgba(0, 0, 0, 0.3);
	}

	.topic-pill {
		animation: fadeIn 0.4s ease-out both;
	}

	.topic-row {
		scrollbar-width: none;
		-ms-overflow-style: none;
	}
	.topic-row::-webkit-scrollbar {
		display: none;
	}

	@media (min-width: 768px) {
		.topic-row {
			flex-wrap: wrap;
			justify-content: center;
			gap: 10px;
			overflow: visible;
		}
	}
</style>
