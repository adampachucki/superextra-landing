<script lang="ts">
	import { formState } from '$lib/form-state.svelte';
	import HeroCanvas from './HeroCanvas.svelte';
</script>

<section class="relative overflow-hidden pt-30 pb-0 md:pt-36">
	<div class="mx-auto max-w-[1200px] px-6">
		<div class="relative">
			<h1 class="hero-fade relative z-10 mx-auto max-w-5xl text-center text-[clamp(4rem,9vw,9rem)] leading-[0.95] font-normal tracking-[-0.04em] text-black" style="animation-delay: 0ms">
				Market intelligence for restaurants
			</h1>

			<div class="hero-fade relative z-0 mx-auto -mt-14 mb-8 flex justify-center md:-mt-40" style="animation-delay: 100ms">
				<div class="relative h-[250px] w-[520px] overflow-hidden rounded-2xl md:h-[360px] md:w-[680px]">
					<HeroCanvas class="absolute inset-0 h-full w-full" />
				</div>
			</div>
		</div>

		<div class="mx-auto max-w-2xl text-center">
			<p class="hero-fade mb-8 text-lg leading-snug text-black/60 md:text-xl" style="animation-delay: 200ms">
				Super local intelligence and competitor benchmarking platform for the restaurant industry. The extra advantage behind smarter decisions.
			</p>
			<button
				onclick={() => formState.open()}
				class="hero-fade inline-flex cursor-pointer items-center gap-2 rounded-full bg-black px-8 py-3.5 text-sm font-medium text-white transition-colors hover:bg-black/80"
				style="animation-delay: 300ms"
			>
				Get Access
			</button>
		</div>
	</div>

	<div class="hero-fade mx-auto mt-20 max-w-[1200px] px-6 md:mt-28" style="animation-delay: 450ms">
		<div class="grid grid-cols-1 border-t border-gray-200 md:grid-cols-3 md:divide-x md:divide-gray-200">
			<div class="border-b border-gray-200 p-8 md:border-b-0 md:py-10 md:pr-10">
				<div class="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-[#f5f4f2]">
					<svg xmlns="http://www.w3.org/2000/svg" class="h-7 w-7" fill="none" viewBox="0 0 24 24"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12Z" stroke="black" stroke-width="0.8"/><path d="M12 9v6M9 12h6" stroke="black" stroke-width="0.8"/></svg>
				</div>
				<h3 class="text-xl font-semibold text-black">Unrivaled data</h3>
				<p class="mt-1 text-sm text-black/60">Competitor activity, menu pricing, reviews, foot traffic, and financials derived from dozens of public and proprietary sources.</p>
			</div>
			<div class="border-b border-gray-200 p-8 md:border-b-0 md:py-10 md:px-10">
				<div class="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-[#f5f4f2]">
					<svg xmlns="http://www.w3.org/2000/svg" class="h-7 w-7" fill="none" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" stroke="black" stroke-width="0.8"/><circle cx="12" cy="12" r="5" stroke="black" stroke-width="0.8"/><circle cx="12" cy="12" r="1.2" fill="black"/></svg>
				</div>
				<h3 class="text-xl font-semibold text-black">Hyper-local focus</h3>
				<p class="mt-1 text-sm text-black/60">Labor, rent, supply chain, and occupancy data that reveals how the industry operates. Benchmarked down to the neighbourhood.</p>
			</div>
			<div class="p-8 md:py-10 md:pl-10">
				<div class="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-[#f5f4f2]">
					<svg xmlns="http://www.w3.org/2000/svg" class="h-7 w-7" fill="black" viewBox="0 0 24 24"><path d="M12 2C12 2 14 9 12 12C10 9 12 2 12 2Z"/><path d="M12 12C12 12 14 15 12 22C10 15 12 12 12 12Z"/><path d="M2 12C2 12 9 10 12 12C9 14 2 12 2 12Z"/><path d="M12 12C12 12 15 10 22 12C15 14 12 12 12 12Z"/></svg>
				</div>
				<h3 class="text-xl font-semibold text-black">AI-native research</h3>
				<p class="mt-1 text-sm text-black/60">Vast market data distilled into clear, actionable insights and custom reports. Backed by human experts when it matters most.</p>
			</div>
		</div>
	</div>
</section>

<style>
	.hero-fade {
		animation: heroFadeIn 0.8s cubic-bezier(0.16, 1, 0.3, 1) both;
	}

	@keyframes heroFadeIn {
		from {
			opacity: 0;
			transform: translateY(16px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}
</style>
