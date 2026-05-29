<script lang="ts">
	import { formState } from '$lib/form-state.svelte';
	import { resolveSupportedBrowserCountry } from '$lib/browser-country';
	import { fetchPlaceSuggestions, type PlaceSuggestion } from '$lib/google-places';
	import Modal from '$lib/components/Modal.svelte';
	import Spinner from '$lib/components/Spinner.svelte';

	// --- Shared constants ---

	const btnPrimary = 'inline-flex items-center gap-2 btn-primary px-7 py-2.5 text-sm';

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
		{ code: 'de', name: 'Germany', dial: '+49' },
		{ code: 'pl', name: 'Poland', dial: '+48' },
		{ code: 'gb', name: 'United Kingdom', dial: '+44' },
		{ code: 'us', name: 'United States', dial: '+1' }
	];
	const fallbackCountryCode = countries[0].code;
	const supportedCountryCodes = countries.map((c) => c.code);

	function resolveDefaultCountry(): string {
		return resolveSupportedBrowserCountry(supportedCountryCodes, fallbackCountryCode);
	}

	// --- Modal state ---

	let contentEl: HTMLDivElement | undefined = $state();
	let contentHeight = $state<number | undefined>();

	// --- Form state ---

	let step = $state(1);
	let submitting = $state(false);
	let submitted = $state(false);
	let submitError = $state(false);
	let submitErrorDetail = $state('');
	let shakeFields = $state<Set<string>>(new Set());

	// Step 1
	let selectedType = $state('');

	// Step 2
	let selectedCountry = $state(fallbackCountryCode);
	let placeName = $state('');
	let selectedPlaceId = $state('');
	let businessName = $state('');
	let selectedLocations = $state('');
	let webUrl = $state('');
	let placeSuggestions = $state<PlaceSuggestion[]>([]);
	let showSuggestions = $state(false);
	let loadingSuggestions = $state(false);
	let debounceTimer: ReturnType<typeof setTimeout>;

	// Step 3
	let fullName = $state('');
	let email = $state('');
	let phone = $state('');
	let emailEl: HTMLInputElement | undefined = $state();

	// --- Derived ---

	let country = $derived(countries.find((c) => c.code === selectedCountry) ?? countries[0]);
	let isVenue = $derived(
		['Single venue', 'Chain operator', 'Hotel operator'].includes(selectedType)
	);
	let emailValid = $derived(email.trim() !== '' && (emailEl?.validity.valid ?? false));

	// --- Effects ---

	$effect(() => {
		step;
		submitted;
		submitError;
		if (!contentEl) return;
		requestAnimationFrame(() => {
			if (contentEl) contentHeight = contentEl.scrollHeight;
		});
	});

	$effect(() => {
		if (selectedType === 'Single venue') {
			selectedLocations = '1';
		}
	});

	// Reset to a clean first step each time the modal opens. The Modal shell owns
	// the open/close animation, so there's no exit-delay to clear state behind.
	$effect(() => {
		if (!formState.visible) return;
		clearTimeout(debounceTimer);
		step = 1;
		selectedType = '';
		selectedCountry = resolveDefaultCountry();
		placeName = '';
		selectedPlaceId = '';
		businessName = '';
		selectedLocations = '';
		webUrl = '';
		fullName = '';
		email = '';
		phone = '';
		placeSuggestions = [];
		showSuggestions = false;
		loadingSuggestions = false;
		shakeFields = new Set();
		submitting = false;
		submitted = false;
		submitError = false;
		submitErrorDetail = '';
	});

	// --- Actions ---

	// Close button, backdrop, and Escape are all gated by `dismissible={!submitting}`
	// on the Modal, so this is unreachable mid-submit.
	function close() {
		formState.close();
	}

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
			if (!isVenue && !/\S+\.\S+/.test(webUrl.trim())) fields.push('web-url');
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
		if (invalid.length > 0) {
			shake(invalid);
			return;
		}
		if (step < 3) step++;
	}

	function back() {
		if (step > 1) step--;
	}

	function onPlaceInput(e: Event) {
		const value = (e.target as HTMLInputElement).value;
		placeName = value;
		selectedPlaceId = '';
		clearTimeout(debounceTimer);
		debounceTimer = setTimeout(async () => {
			loadingSuggestions = true;
			try {
				placeSuggestions = await fetchPlaceSuggestions(value, selectedCountry);
			} catch {
				placeSuggestions = [];
			}
			loadingSuggestions = false;
		}, 300);
		showSuggestions = true;
	}

	function selectPlace(s: PlaceSuggestion) {
		placeName = s.name;
		selectedPlaceId = s.placeId;
		placeSuggestions = [];
		showSuggestions = false;
		if (document.activeElement instanceof HTMLElement) {
			document.activeElement.blur();
		}
	}

	async function submit() {
		const invalid = getInvalidFields();
		if (invalid.length > 0) {
			shake(invalid);
			return;
		}
		submitting = true;
		submitError = false;
		submitErrorDetail = '';
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
			if (!res.ok) {
				const body = await res.json().catch(() => ({}));
				submitErrorDetail = body.error || `Server error (${res.status})`;
				throw new Error(submitErrorDetail);
			}
		} catch (err) {
			submitting = false;
			submitError = true;
			console.error('Form submission failed:', err);
			return;
		}
		submitting = false;
		submitted = true;
	}
</script>

<!-- Step snippets -->

{#snippet selectChevron()}
	<svg
		class="pointer-events-none absolute top-1/2 right-3 h-4 w-4 -translate-y-1/2 text-black/45 dark:text-white/45"
		viewBox="0 0 24 24"
		fill="none"
		stroke="currentColor"
		aria-hidden="true"
	>
		<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="m6 9 6 6 6-6" />
	</svg>
{/snippet}

{#snippet successStep()}
	<div class="step-content flex flex-col items-center py-8 text-center">
		<div
			class="mb-6 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-50 dark:bg-emerald-500/10"
		>
			<svg
				xmlns="http://www.w3.org/2000/svg"
				class="h-7 w-7 text-emerald-500"
				fill="none"
				viewBox="0 0 24 24"
				stroke="currentColor"
				stroke-width="2"
			>
				<path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
			</svg>
		</div>
		<h2 class="mb-2 text-xl font-medium tracking-tight text-black dark:text-white">
			Demo request sent
		</h2>
		<p class="mb-8 max-w-xs text-sm leading-relaxed text-black/40 dark:text-white/40">
			A confirmation email has been sent. The team will follow up with available times.
		</p>
		<button onclick={close} class="btn-primary px-7 py-2.5 text-sm"> Done </button>
	</div>
{/snippet}

{#snippet step1()}
	<div class="step-content">
		<h2 class="mb-2 text-lg font-medium tracking-tight text-black dark:text-white">
			What kind of business do you run?
		</h2>
		<p class="mb-8 text-[13px] text-black/50 dark:text-white/50">Choose the closest fit.</p>

		<div class="grid grid-cols-3 gap-2.5 {shakeFields.has('type-grid') ? 'shake' : ''}">
			{#each businessTypes as type (type)}
				<button
					onclick={() => (selectedType = selectedType === type ? '' : type)}
					class="rounded-xl border px-3 py-3 text-sm transition-all duration-200
					{selectedType === type
						? 'border-black bg-black text-white dark:border-white dark:bg-white dark:text-black'
						: 'border-cream-200 bg-white text-black/60 hover:border-cream-300 hover:text-black dark:bg-cream-50 dark:text-white/60 dark:hover:text-white'}"
				>
					{type}
				</button>
			{/each}
		</div>
	</div>
{/snippet}

{#snippet step2()}
	<div class="step-content">
		<h2 class="mb-2 text-lg font-medium tracking-tight text-black dark:text-white">
			Add your business details
		</h2>
		<p class="mb-8 text-[13px] text-black/50 dark:text-white/50">Help us understand your needs.</p>

		<div class="space-y-4">
			<div>
				<label
					for="country"
					class="mb-1.5 block text-xs font-medium text-black/60 dark:text-white/60">Country</label
				>
				<div class="relative">
					<select id="country" bind:value={selectedCountry} class="field appearance-none pr-10">
						{#each countries as c (c.code)}
							<option value={c.code}>{c.name}</option>
						{/each}
					</select>
					{@render selectChevron()}
				</div>
			</div>
			{#if isVenue}
				<div class="relative">
					<label
						for="place-name"
						class="mb-1.5 block text-xs font-medium text-black/60 dark:text-white/60"
						>Place name</label
					>
					<input
						id="place-name"
						type="text"
						value={placeName}
						oninput={onPlaceInput}
						onfocus={() => {
							if (placeSuggestions.length) showSuggestions = true;
						}}
						onblur={() => setTimeout(() => (showSuggestions = false), 150)}
						placeholder="The Corner Bistro"
						autocomplete="off"
						autocorrect="off"
						spellcheck="false"
						role="combobox"
						aria-autocomplete="list"
						aria-expanded={showSuggestions && placeSuggestions.length > 0}
						aria-controls="place-suggestions"
						aria-invalid={shakeFields.has('place-name') ? 'true' : undefined}
						class="field pr-10 {shakeFields.has('place-name') ? 'shake' : ''}"
					/>
					{#if loadingSuggestions}
						<Spinner class="absolute right-3 bottom-3 h-4 w-4 text-black/25 dark:text-white/25" />
					{/if}
					{#if showSuggestions && placeSuggestions.length > 0}
						<ul
							id="place-suggestions"
							role="listbox"
							class="absolute top-full right-0 left-0 z-10 mt-1 max-h-40 popover"
						>
							{#each placeSuggestions as s (s.placeId)}
								<li role="option" aria-selected="false">
									<button
										type="button"
										class="popover-option text-sm"
										onpointerdown={(e) => e.preventDefault()}
										onclick={() => selectPlace(s)}
									>
										<span class="text-black dark:text-white">{s.name}</span>
										{#if s.secondary}
											<span class="ml-1 text-black/45 dark:text-white/45">{s.secondary}</span>
										{/if}
									</button>
								</li>
							{/each}
						</ul>
					{/if}
				</div>
			{:else}
				<div>
					<label
						for="business-name"
						class="mb-1.5 block text-xs font-medium text-black/60 dark:text-white/60"
						>Business name</label
					>
					<input
						id="business-name"
						type="text"
						bind:value={businessName}
						placeholder="Acme Inc."
						aria-invalid={shakeFields.has('business-name') ? 'true' : undefined}
						class="field {shakeFields.has('business-name') ? 'shake' : ''}"
					/>
				</div>
			{/if}
			{#if isVenue}
				<div>
					<label
						for="locations"
						class="mb-1.5 block text-xs font-medium text-black/60 dark:text-white/60"
						>Number of locations</label
					>
					<div class="relative">
						<select
							id="locations"
							bind:value={selectedLocations}
							aria-invalid={shakeFields.has('locations') ? 'true' : undefined}
							class="field appearance-none pr-10 {shakeFields.has('locations') ? 'shake' : ''}"
						>
							<option value="" disabled class="text-black/25">Select</option>
							<option value="1">1 location</option>
							<option value="2-5">2 – 5 locations</option>
							<option value="6-20">6 – 20 locations</option>
							<option value="20+">20+ locations</option>
						</select>
						{@render selectChevron()}
					</div>
				</div>
			{:else}
				<div>
					<label
						for="web-url"
						class="mb-1.5 block text-xs font-medium text-black/60 dark:text-white/60">Web URL</label
					>
					<input
						id="web-url"
						type="text"
						bind:value={webUrl}
						placeholder="example.com"
						aria-invalid={shakeFields.has('web-url') ? 'true' : undefined}
						class="field {shakeFields.has('web-url') ? 'shake' : ''}"
					/>
				</div>
			{/if}
		</div>
	</div>
{/snippet}

{#snippet step3()}
	<div class="step-content">
		<h2 class="mb-2 text-lg font-medium tracking-tight text-black dark:text-white">
			Your contact details
		</h2>
		<p class="mb-8 text-[13px] text-black/50 dark:text-white/50">
			Available time slots will arrive by email.
		</p>

		<div class="space-y-4">
			<div>
				<label
					for="full-name"
					class="mb-1.5 block text-xs font-medium text-black/60 dark:text-white/60">Full name</label
				>
				<input
					id="full-name"
					type="text"
					bind:value={fullName}
					placeholder="Jane Smith"
					aria-invalid={shakeFields.has('full-name') ? 'true' : undefined}
					class="field {shakeFields.has('full-name') ? 'shake' : ''}"
				/>
			</div>
			<div>
				<label for="email" class="mb-1.5 block text-xs font-medium text-black/60 dark:text-white/60"
					>Work email</label
				>
				<input
					id="email"
					type="email"
					bind:this={emailEl}
					bind:value={email}
					placeholder="jane@company.com"
					aria-invalid={shakeFields.has('email') ? 'true' : undefined}
					class="field {shakeFields.has('email') ? 'shake' : ''}"
				/>
			</div>
			<div>
				<label for="phone" class="mb-1.5 block text-xs font-medium text-black/60 dark:text-white/60"
					>Phone <span class="text-black/25 dark:text-white/25">(optional)</span></label
				>
				<div class="flex gap-2">
					<span
						class="flex items-center rounded-xl border border-black/[0.12] bg-cream-50 px-3.5 text-sm text-black/60 dark:border-white/[0.12] dark:text-white/60"
					>
						{country.dial}
					</span>
					<input
						id="phone"
						type="tel"
						bind:value={phone}
						placeholder={country.code === 'us'
							? '(555) 000-0000'
							: country.code === 'gb'
								? '7911 123456'
								: country.code === 'de'
									? '151 12345678'
									: '512 345 678'}
						class="field"
					/>
				</div>
			</div>
		</div>

		{#if submitError}
			<p class="mt-4 text-sm text-red-500">
				Something went wrong, please try again{#if submitErrorDetail}
					({submitErrorDetail}){/if}
			</p>
		{/if}
	</div>
{/snippet}

<!-- Main template -->

<Modal
	open={formState.visible}
	onclose={close}
	ariaLabel="Book a demo"
	maxWidth="max-w-[560px]"
	z="z-[100]"
	dismissible={!submitting}
>
	<div class="p-8 md:p-10">
		<!-- Content wrapper with animated height -->
		<div
			class="transition-[height] duration-300 ease-out"
			style={contentHeight ? `height:${contentHeight}px` : ''}
		>
			<div bind:this={contentEl}>
				{#if submitted}
					{@render successStep()}
				{:else}
					<!-- Step indicator -->
					<div class="mb-8 flex items-center justify-start gap-2">
						{#each [1, 2, 3] as s (s)}
							<div
								class="h-1 rounded-full transition-all duration-300 {s === step
									? 'w-8 bg-black dark:bg-white'
									: s < step
										? 'w-8 bg-black/30 dark:bg-white/30'
										: 'w-8 bg-cream-200'}"
							></div>
						{/each}
					</div>

					{#if step === 1}
						{@render step1()}
					{:else if step === 2}
						{@render step2()}
					{:else}
						{@render step3()}
					{/if}
				{/if}
			</div>
		</div>

		<!-- Navigation buttons (outside height transition to avoid clipping) -->
		{#if !submitted}
			<div class="mt-8 flex items-center {step === 1 ? 'justify-end' : 'justify-between'}">
				{#if step > 1}
					<button
						onclick={back}
						disabled={submitting}
						class="-ml-2 inline-flex btn-secondary items-center gap-1.5 px-4 py-2.5 text-sm"
					>
						<svg
							xmlns="http://www.w3.org/2000/svg"
							class="h-3.5 w-3.5"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							stroke-width="2"
						>
							<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
						</svg>
						Back
					</button>
				{/if}
				{#if step < 3}
					<button onclick={next} class={btnPrimary}>
						Continue
						<svg
							xmlns="http://www.w3.org/2000/svg"
							class="h-3.5 w-3.5"
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							stroke-width="2"
						>
							<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
						</svg>
					</button>
				{:else}
					<button onclick={submit} disabled={submitting} class={btnPrimary}>
						{#if submitting}
							<Spinner class="h-4 w-4" />
							Submitting...
						{:else}
							Request demo
						{/if}
					</button>
				{/if}
			</div>
		{/if}
	</div>
</Modal>

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
		0%,
		100% {
			transform: translateX(0);
		}
		20% {
			transform: translateX(-6px);
		}
		40% {
			transform: translateX(5px);
		}
		60% {
			transform: translateX(-3px);
		}
		80% {
			transform: translateX(2px);
		}
	}
</style>
