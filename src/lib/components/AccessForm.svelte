<script lang="ts">
	import { PUBLIC_GOOGLE_PLACES_KEY } from '$env/static/public';
	import { formState } from '$lib/form-state.svelte';

	const btnPrimary = 'inline-flex items-center gap-2 rounded-full bg-black px-7 py-2.5 text-sm font-medium text-white transition-colors hover:bg-black/80';
	const inputBase = 'w-full rounded-xl border px-4 py-3 text-sm text-black placeholder:text-black/25 focus:border-black focus:ring-0 focus:outline-none';

	let step = $state(1);
	let selectedType = $state('');
	let selectedCountry = $state('us');
	let submitting = $state(false);
	let submitted = $state(false);
	let submitError = $state(false);
	let backdropVisible = $state(false);
	let modalVisible = $state(false);
	let contentEl: HTMLDivElement | undefined = $state();
	let contentHeight = $state<number | undefined>();

	$effect(() => {
		// Track step and submitted to re-measure
		step; submitted;
		if (!contentEl) return;
		// Wait a tick for DOM to update
		requestAnimationFrame(() => {
			if (contentEl) contentHeight = contentEl.scrollHeight;
		});
	});

	const businessTypes = [
		'Single venue',
		'Chain operator',
		'Hotel operator',
		'Delivery service',
		'Supply & distrib.',
		'Advisory',
		'Real estate',
		'Tech platform',
		'Other'
	];

	const countries = [
		{ code: 'us', name: 'United States', dial: '+1' },
		{ code: 'gb', name: 'United Kingdom', dial: '+44' },
		{ code: 'de', name: 'Germany', dial: '+49' },
		{ code: 'pl', name: 'Poland', dial: '+48' }
	];

	let placeName = $state('');
	let businessName = $state('');
	let selectedLocations = $state('');
	let webUrl = $state('');
	let fullName = $state('');
	let email = $state('');
	let phone = $state('');

	let country = $derived(countries.find((c) => c.code === selectedCountry) ?? countries[0]);
	let isVenue = $derived(['Single venue', 'Chain operator', 'Hotel operator'].includes(selectedType));

	let emailEl: HTMLInputElement | undefined = $state();
	let emailValid = $derived(email.trim() !== '' && (emailEl?.validity.valid ?? false));

	$effect(() => {
		if (selectedType === 'Single venue') {
			selectedLocations = '1';
		}
	});

	// --- Google Places Autocomplete ---
	let mapsPromise: Promise<void> | null = null;
	let placeSuggestions = $state<Array<{ name: string; secondary: string; placeId: string }>>([]);
	let selectedPlaceId = $state('');
	let showSuggestions = $state(false);
	let loadingSuggestions = $state(false);
	let debounceTimer: ReturnType<typeof setTimeout>;

	function loadGoogleMaps(): Promise<void> {
		if (mapsPromise) return mapsPromise;
		mapsPromise = new Promise<void>((resolve, reject) => {
			if (typeof google !== 'undefined' && google.maps?.places) {
				resolve();
				return;
			}
			const script = document.createElement('script');
			script.src = `https://maps.googleapis.com/maps/api/js?key=${PUBLIC_GOOGLE_PLACES_KEY}&libraries=places`;
			script.async = true;
			script.onload = () => resolve();
			script.onerror = reject;
			document.head.appendChild(script);
		});
		return mapsPromise;
	}

	async function fetchPlaceSuggestions(input: string) {
		if (input.length < 2) {
			placeSuggestions = [];
			loadingSuggestions = false;
			return;
		}
		loadingSuggestions = true;
		try {
			await loadGoogleMaps();
			const { suggestions } = await (google.maps.places.AutocompleteSuggestion as any).fetchAutocompleteSuggestions({
				input,
				includedPrimaryTypes: ['restaurant', 'cafe', 'bar', 'hotel', 'food'],
				includedRegionCodes: [selectedCountry]
			});
			placeSuggestions = suggestions.map((s: any) => ({
				name: s.placePrediction.mainText.text,
				secondary: s.placePrediction.secondaryText?.text ?? '',
				placeId: s.placePrediction.placeId
			}));
		} catch {
			placeSuggestions = [];
		}
		loadingSuggestions = false;
	}

	function onPlaceInput(e: Event) {
		const value = (e.target as HTMLInputElement).value;
		placeName = value;
		selectedPlaceId = '';
		clearTimeout(debounceTimer);
		debounceTimer = setTimeout(() => fetchPlaceSuggestions(value), 300);
		showSuggestions = true;
	}

	function selectPlace(s: { name: string; secondary: string; placeId: string }) {
		placeName = s.name;
		selectedPlaceId = s.placeId;
		placeSuggestions = [];
		showSuggestions = false;
		// Dismiss keyboard on mobile to prevent viewport offset
		if (document.activeElement instanceof HTMLElement) {
			document.activeElement.blur();
		}
	}

	// Lock body scroll when modal is open to prevent iOS keyboard viewport offset
	$effect(() => {
		if (formState.visible) {
			const scrollY = window.scrollY;
			document.body.style.position = 'fixed';
			document.body.style.top = `-${scrollY}px`;
			document.body.style.left = '0';
			document.body.style.right = '0';
			document.body.style.width = '100%';
			document.body.style.overflow = 'hidden';

			return () => {
				document.body.style.position = '';
				document.body.style.top = '';
				document.body.style.left = '';
				document.body.style.right = '';
				document.body.style.width = '';
				document.body.style.overflow = '';
				window.scrollTo(0, scrollY);
			};
		}
	});

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
				placeName = '';
				selectedPlaceId = '';
				businessName = '';
				selectedLocations = '';
				webUrl = '';
				fullName = '';
				email = '';
				phone = '';
				submitting = false;
				submitted = false;
				submitError = false;
			}, 200);
		}, 150);
	}

	let shakeFields = $state<Set<string>>(new Set());

	function shake(fields: string[]) {
		shakeFields = new Set(fields);
		setTimeout(() => (shakeFields = new Set()), 600);
	}

	function getInvalidFields(): string[] {
		if (step === 1) return selectedType === '' ? ['type-grid'] : [];
		if (step === 2) {
			const fields: string[] = [];
			if (isVenue && placeName.trim() === '') fields.push('place-name');
			if (!isVenue && businessName.trim() === '') fields.push('business-name');
			if (isVenue && selectedLocations === '') fields.push('locations');
			if (!isVenue && !(/\S+\.\S+/.test(webUrl.trim()))) fields.push('web-url');
			return fields;
		}
		if (step === 3) {
			const fields: string[] = [];
			if (fullName.trim() === '') fields.push('full-name');
			if (!emailValid) fields.push('email');
			return fields;
		}
		return [];
	}

	function next() {
		const invalid = getInvalidFields();
		if (invalid.length > 0) { shake(invalid); return; }
		if (step < 3) step++;
	}

	function back() {
		if (step > 1) step--;
	}

	async function submit() {
		const invalid = getInvalidFields();
		if (invalid.length > 0) { shake(invalid); return; }
		submitting = true;
		submitError = false;
		try {
			const res = await fetch('/api/intake', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					type: selectedType,
					country: country.name,
					businessName: isVenue ? placeName : businessName,
					placeId: selectedPlaceId || undefined,
					locations: isVenue ? selectedLocations : undefined,
					webUrl: isVenue ? undefined : webUrl,
					fullName,
					email,
					phone: phone || undefined
				})
			});
			if (!res.ok) throw new Error();
		} catch {
			submitting = false;
			submitError = true;
			return;
		}
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
				{modalVisible ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0'}"
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

			<!-- Content wrapper with animated height -->
			<div
				class="overflow-hidden transition-[height] duration-300 ease-out"
				style={contentHeight ? `height:${contentHeight}px` : ''}
			>
				<div bind:this={contentEl}>

			<!-- Success state -->
			{#if submitted}
				<div class="step-content flex flex-col items-center py-8 text-center">
					<div class="mb-6 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-50">
						<svg xmlns="http://www.w3.org/2000/svg" class="h-7 w-7 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
						</svg>
					</div>
					<h2 class="mb-2 text-xl font-semibold tracking-tight text-black">
						Form submitted
					</h2>
					<p class="mb-8 max-w-xs text-sm leading-relaxed text-black/40">
						We'll get back to you within 24 hours
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
							Select the option that best describes you
						</p>

						<div class="grid grid-cols-3 gap-2.5 {shakeFields.has('type-grid') ? 'shake' : ''}">
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
								class="{btnPrimary}"
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
							{#if isVenue}
								<div class="relative">
									<label for="place-name" class="mb-1.5 block text-xs font-medium text-black/50">Place name</label>
									<input
										id="place-name"
										type="text"
										value={placeName}
										oninput={onPlaceInput}
										onfocus={() => { if (placeSuggestions.length) showSuggestions = true; }}
										onblur={() => setTimeout(() => (showSuggestions = false), 150)}
										placeholder="The Corner Bistro"
										autocomplete="off"
										autocorrect="off"
										spellcheck="false"
										class="{inputBase} pr-10 {shakeFields.has('place-name') ? 'shake border-red-300' : 'border-gray-200'}"
									/>
									{#if loadingSuggestions}
										<svg class="absolute top-1/2 right-3 h-4 w-4 -translate-y-1/2 animate-spin text-black/20" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
											<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="3"></circle>
											<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
										</svg>
									{/if}
									{#if showSuggestions && placeSuggestions.length > 0}
										<ul class="absolute left-0 right-0 top-full z-10 mt-1 max-h-48 overflow-auto rounded-xl border border-gray-200 bg-white py-1 shadow-lg">
											{#each placeSuggestions as s}
												<li>
													<button
														type="button"
														class="w-full px-4 py-2 text-left text-sm hover:bg-gray-50"
														onmousedown={() => selectPlace(s)}
													>
														<span class="text-black">{s.name}</span>
														{#if s.secondary}
															<span class="ml-1 text-black/30">{s.secondary}</span>
														{/if}
													</button>
												</li>
											{/each}
										</ul>
									{/if}
								</div>
							{:else}
								<div>
									<label for="business-name" class="mb-1.5 block text-xs font-medium text-black/50">Business name</label>
									<input
										id="business-name"
										type="text"
										bind:value={businessName}
										placeholder="Acme Inc."
										class="{inputBase} {shakeFields.has('business-name') ? 'shake border-red-300' : 'border-gray-200'}"
									/>
								</div>
							{/if}
							{#if isVenue}
								<div>
									<label for="locations" class="mb-1.5 block text-xs font-medium text-black/50">Number of locations</label>
									<select
										id="locations"
										bind:value={selectedLocations}
										class="w-full appearance-none rounded-xl border bg-white px-4 py-3 text-sm text-black focus:border-black focus:ring-0 focus:outline-none {shakeFields.has('locations') ? 'shake border-red-300' : 'border-gray-200'}"
									>
										<option value="" disabled class="text-black/25">Select</option>
										<option value="1">1 location</option>
										<option value="2-5">2 – 5 locations</option>
										<option value="6-20">6 – 20 locations</option>
										<option value="20+">20+ locations</option>
									</select>
								</div>
							{:else}
								<div>
									<label for="web-url" class="mb-1.5 block text-xs font-medium text-black/50">Web URL</label>
									<input
										id="web-url"
										type="text"
										bind:value={webUrl}
										placeholder="example.com"
										class="{inputBase} {shakeFields.has('web-url') ? 'shake border-red-300' : 'border-gray-200'}"
									/>
								</div>
							{/if}
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
								class="{btnPrimary}"
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
									bind:value={fullName}
									placeholder="Jane Smith"
									class="{inputBase} {shakeFields.has('full-name') ? 'shake border-red-300' : 'border-gray-200'}"
								/>
							</div>
							<div>
								<label for="email" class="mb-1.5 block text-xs font-medium text-black/50">Work email</label>
								<input
									id="email"
									type="email"
									bind:this={emailEl}
									bind:value={email}
									placeholder="jane@company.com"
									class="{inputBase} {shakeFields.has('email') ? 'shake border-red-300' : 'border-gray-200'}"
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
										bind:value={phone}
										placeholder={country.code === 'us' ? '(555) 000-0000' : country.code === 'gb' ? '7911 123456' : country.code === 'de' ? '151 12345678' : '512 345 678'}
										class="w-full rounded-xl border border-gray-200 px-4 py-3 text-sm text-black placeholder:text-black/25 focus:border-black focus:ring-0 focus:outline-none"
									/>
								</div>
							</div>
						</div>

						{#if submitError}
							<p class="mt-4 text-sm text-red-500">Something went wrong, please try again</p>
						{/if}

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
								class="{btnPrimary} disabled:opacity-60"
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

	.shake {
		animation: shake 0.4s ease-out;
	}

	@keyframes shake {
		0%, 100% { transform: translateX(0); }
		20% { transform: translateX(-6px); }
		40% { transform: translateX(5px); }
		60% { transform: translateX(-3px); }
		80% { transform: translateX(2px); }
	}
</style>
