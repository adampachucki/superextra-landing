<script lang="ts">
	import { formState } from '$lib/form-state.svelte';

	let step = $state(1);
	let selectedType = $state('');
	let selectedCountry = $state('us');
	let submitting = $state(false);
	let submitted = $state(false);
	let backdropVisible = $state(false);
	let modalVisible = $state(false);

	const businessTypes = [
		'Restaurant',
		'Cafe',
		'Bar / Pub',
		'Hotel',
		'Fast Food',
		'Fast Casual',
		'Bakery',
		'Food Truck',
		'Pizzeria',
		'Catering',
		'Delivery Service',
		'Other'
	];

	const countries = [
		{ code: 'us', name: 'United States', dial: '+1' },
		{ code: 'gb', name: 'United Kingdom', dial: '+44' },
		{ code: 'de', name: 'Germany', dial: '+49' },
		{ code: 'pl', name: 'Poland', dial: '+48' }
	];

	let country = $derived(countries.find((c) => c.code === selectedCountry) ?? countries[0]);

	// Animate in when formState.visible becomes true
	$effect(() => {
		if (formState.visible) {
			// Trigger backdrop first, then modal
			requestAnimationFrame(() => {
				backdropVisible = true;
				requestAnimationFrame(() => {
					modalVisible = true;
				});
			});
		}
	});

	function close() {
		modalVisible = false;
		setTimeout(() => {
			backdropVisible = false;
			setTimeout(() => {
				formState.close();
				step = 1;
				selectedType = '';
				selectedCountry = 'us';
				submitting = false;
				submitted = false;
			}, 200);
		}, 150);
	}

	function next() {
		if (step < 3) step++;
	}

	function back() {
		if (step > 1) step--;
	}

	async function submit() {
		submitting = true;
		// Simulate network request
		await new Promise((r) => setTimeout(r, 1500));
		submitting = false;
		submitted = true;
	}
</script>

{#if formState.visible}
	<!-- Backdrop -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-[100] flex items-center justify-center transition-all duration-300
			{backdropVisible ? 'bg-black/20 backdrop-blur-sm' : 'bg-black/0 backdrop-blur-0'}"
		onmousedown={(e) => {
			if (e.target === e.currentTarget && !submitting) close();
		}}
	>
		<!-- Modal -->
		<div
			class="relative mx-4 w-full max-w-[560px] rounded-2xl bg-white p-8 shadow-2xl shadow-black/10 transition-all duration-300 md:p-10
				{modalVisible ? 'translate-y-0 scale-100 opacity-100' : 'translate-y-4 scale-[0.97] opacity-0'}"
		>
			<!-- Close button -->
			{#if !submitting}
				<button
					onclick={close}
					class="absolute top-5 right-5 flex h-8 w-8 items-center justify-center rounded-full text-black/30 transition-colors hover:bg-gray-100 hover:text-black/60"
					aria-label="Close"
				>
					<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			{/if}

			<!-- Success state -->
			{#if submitted}
				<div class="step-content flex flex-col items-center py-8 text-center">
					<div class="mb-6 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-50">
						<svg xmlns="http://www.w3.org/2000/svg" class="h-7 w-7 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
						</svg>
					</div>
					<h2 class="mb-2 text-xl font-semibold tracking-tight text-black">
						You're on the list
					</h2>
					<p class="mb-8 max-w-xs text-sm leading-relaxed text-black/40">
						We'll review your request and get back to you within 24 hours with next steps.
					</p>
					<button
						onclick={close}
						class="rounded-full border border-gray-200 px-7 py-2.5 text-sm text-black transition-colors hover:bg-gray-50"
					>
						Done
					</button>
				</div>
			{:else}
				<!-- Step indicator -->
				<div class="mb-8 flex items-center justify-center gap-2">
					{#each [1, 2, 3] as s}
						<div class="h-1 rounded-full transition-all duration-300 {s === step ? 'w-8 bg-black' : s < step ? 'w-8 bg-black/30' : 'w-8 bg-gray-200'}"></div>
					{/each}
				</div>

				<!-- Step 1: Business Type -->
				{#if step === 1}
					<div class="step-content">
						<h2 class="mb-2 text-center text-xl font-semibold tracking-tight text-black">
							What kind of business do you run?
						</h2>
						<p class="mb-8 text-center text-sm text-black/40">
							Select the option that best describes your business
						</p>

						<div class="grid grid-cols-3 gap-2.5">
							{#each businessTypes as type}
								<button
									onclick={() => (selectedType = selectedType === type ? '' : type)}
									class="cursor-pointer rounded-xl border px-3 py-3 text-sm transition-all duration-200
										{selectedType === type
											? 'border-black bg-black text-white'
											: 'border-gray-200 bg-white text-black/70 hover:border-gray-300 hover:text-black'}"
								>
									{type}
								</button>
							{/each}
						</div>

						<div class="mt-8 flex justify-end">
							<button
								onclick={next}
								class="inline-flex items-center gap-2 rounded-full bg-black px-7 py-2.5 text-sm font-medium text-white transition-colors hover:bg-black/80"
							>
								Continue
								<svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
								</svg>
							</button>
						</div>
					</div>

				<!-- Step 2: Business Details -->
				{:else if step === 2}
					<div class="step-content">
						<h2 class="mb-2 text-center text-xl font-semibold tracking-tight text-black">
							Tell us about your business
						</h2>
						<p class="mb-8 text-center text-sm text-black/40">
							Help us tailor the experience to your needs
						</p>

						<div class="space-y-4">
							<div>
								<label for="country" class="mb-1.5 block text-xs font-medium text-black/50">Country</label>
								<select
									id="country"
									bind:value={selectedCountry}
									class="w-full appearance-none rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-black focus:border-black focus:ring-0 focus:outline-none"
								>
									{#each countries as c}
										<option value={c.code}>{c.name}</option>
									{/each}
								</select>
							</div>
							<div>
								<label for="business-name" class="mb-1.5 block text-xs font-medium text-black/50">Place name</label>
								<input
									id="business-name"
									type="text"
									placeholder="e.g. The Corner Bistro"
									class="w-full rounded-xl border border-gray-200 px-4 py-3 text-sm text-black placeholder:text-black/25 focus:border-black focus:ring-0 focus:outline-none"
								/>
							</div>
							<div>
								<label for="locations" class="mb-1.5 block text-xs font-medium text-black/50">Number of locations</label>
								<select
									id="locations"
									class="w-full appearance-none rounded-xl border border-gray-200 bg-white px-4 py-3 text-sm text-black focus:border-black focus:ring-0 focus:outline-none"
								>
									<option value="" disabled selected class="text-black/25">Select</option>
									<option value="1">1 location</option>
									<option value="2-5">2 – 5 locations</option>
									<option value="6-20">6 – 20 locations</option>
									<option value="20+">20+ locations</option>
								</select>
							</div>
						</div>

						<div class="mt-8 flex items-center justify-between">
							<button
								onclick={back}
								class="inline-flex items-center gap-1.5 text-sm text-black/40 transition-colors hover:text-black"
							>
								<svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
								</svg>
								Back
							</button>
							<button
								onclick={next}
								class="inline-flex items-center gap-2 rounded-full bg-black px-7 py-2.5 text-sm font-medium text-white transition-colors hover:bg-black/80"
							>
								Continue
								<svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
								</svg>
							</button>
						</div>
					</div>

				<!-- Step 3: Contact Info -->
				{:else}
					<div class="step-content">
						<h2 class="mb-2 text-center text-xl font-semibold tracking-tight text-black">
							How can we reach you?
						</h2>
						<p class="mb-8 text-center text-sm text-black/40">
							We'll get back to you within 24 hours
						</p>

						<div class="space-y-4">
							<div>
								<label for="full-name" class="mb-1.5 block text-xs font-medium text-black/50">Full name</label>
								<input
									id="full-name"
									type="text"
									placeholder="Jane Smith"
									class="w-full rounded-xl border border-gray-200 px-4 py-3 text-sm text-black placeholder:text-black/25 focus:border-black focus:ring-0 focus:outline-none"
								/>
							</div>
							<div>
								<label for="email" class="mb-1.5 block text-xs font-medium text-black/50">Work email</label>
								<input
									id="email"
									type="email"
									placeholder="jane@restaurant.com"
									class="w-full rounded-xl border border-gray-200 px-4 py-3 text-sm text-black placeholder:text-black/25 focus:border-black focus:ring-0 focus:outline-none"
								/>
							</div>
							<div>
								<label for="phone" class="mb-1.5 block text-xs font-medium text-black/50">Phone <span class="text-black/25">(optional)</span></label>
								<div class="flex gap-2">
									<span class="flex items-center rounded-xl border border-gray-200 bg-gray-50 px-3.5 text-sm text-black/50">
										{country.dial}
									</span>
									<input
										id="phone"
										type="tel"
										placeholder={country.code === 'us' ? '(555) 000-0000' : country.code === 'gb' ? '7911 123456' : country.code === 'de' ? '151 12345678' : '512 345 678'}
										class="w-full rounded-xl border border-gray-200 px-4 py-3 text-sm text-black placeholder:text-black/25 focus:border-black focus:ring-0 focus:outline-none"
									/>
								</div>
							</div>
						</div>

						<div class="mt-8 flex items-center justify-between">
							<button
								onclick={back}
								disabled={submitting}
								class="inline-flex items-center gap-1.5 text-sm text-black/40 transition-colors hover:text-black disabled:opacity-30"
							>
								<svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
								</svg>
								Back
							</button>
							<button
								onclick={submit}
								disabled={submitting}
								class="inline-flex items-center gap-2 rounded-full bg-black px-7 py-2.5 text-sm font-medium text-white transition-colors hover:bg-black/80 disabled:opacity-60"
							>
								{#if submitting}
									<svg class="h-4 w-4 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
										<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3"></circle>
										<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
									</svg>
									Submitting...
								{:else}
									Request Access
								{/if}
							</button>
						</div>
					</div>
				{/if}
			{/if}
		</div>
	</div>
{/if}

<style>
	.step-content {
		animation: fadeSlideIn 0.25s ease-out;
	}

	@keyframes fadeSlideIn {
		from {
			opacity: 0;
			transform: translateX(12px);
		}
		to {
			opacity: 1;
			transform: translateX(0);
		}
	}
</style>
