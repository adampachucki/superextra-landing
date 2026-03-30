<script lang="ts">
	import { theme } from '$lib/theme.svelte';

	let year = $state(new Date().getFullYear());
</script>

<footer class="border-t border-cream-200 py-12 pb-20 md:pb-12">
	<div class="mx-auto max-w-[1200px] px-6">
		<div class="flex flex-col items-center justify-between gap-6 md:flex-row">
			<div class="flex flex-col items-center gap-2 md:items-start">
				<div class="group flex items-center gap-0 md:gap-0.5">
					<svg class="h-[18px] w-[18px] -mt-2.5 md:-mt-2 transition-transform duration-500 ease-out group-hover:rotate-45" viewBox="0 0 12 12" fill="none">
						<line x1="6" y1="0.5" x2="6" y2="11.5" stroke="currentColor" stroke-width="1.5"/>
						<line x1="1.24" y1="3.25" x2="10.76" y2="8.75" stroke="currentColor" stroke-width="1.5"/>
						<line x1="1.24" y1="8.75" x2="10.76" y2="3.25" stroke="currentColor" stroke-width="1.5"/>
					</svg>
					<span class="text-[22px] font-light tracking-tight text-black dark:text-white">Superextra</span>
				</div>
				<p class="text-sm text-black/40 dark:text-white/40">
					&copy; {year} Superextra. All rights reserved.
				</p>
			</div>

			<div class="flex flex-col items-center gap-4 md:items-end">
				<div class="flex flex-col items-center gap-4 md:flex-row md:gap-6">
					<div class="flex items-center gap-6">
						<div class="hidden items-center gap-2 md:flex">
							<span class="text-xs text-black/40 dark:text-white/40">Supported by</span>
							<img src="/google-for-startups.svg" alt="Google for Startups" class="h-3.5 translate-y-px opacity-40 grayscale dark:invert" />
						</div>
						<span class="mx-2 hidden h-4 w-px bg-black/10 dark:bg-white/10 md:block"></span>
						<a href="/memo" class="text-sm text-black/40 dark:text-white/40 transition-colors hover:text-black/60 dark:hover:text-white/60">Memo</a>
						<a href="/privacy-policy" class="text-sm text-black/40 dark:text-white/40 transition-colors hover:text-black/60 dark:hover:text-white/60">Privacy</a>
						<a href="/terms" class="text-sm text-black/40 dark:text-white/40 transition-colors hover:text-black/60 dark:hover:text-white/60">Terms</a>
						<a href="https://www.linkedin.com/company/superextra" target="_blank" rel="noopener noreferrer" class="text-black/40 dark:text-white/40 transition-colors hover:text-black/60 dark:hover:text-white/60" aria-label="LinkedIn">
							<svg class="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" /></svg>
						</a>
						<span class="h-4 w-px bg-black/10 dark:bg-white/10"></span>
						<button
							onclick={() => theme.cycle()}
							class="text-black/40 dark:text-white/40 transition-colors hover:text-black/60 dark:hover:text-white/60 cursor-pointer"
							aria-label="Toggle theme"
						>
							{#if theme.mode === 'dark'}
								<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z" /></svg>
							{:else if theme.mode === 'light'}
								<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="4" /><path stroke-linecap="round" d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32l1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41m11.32-11.32l1.41-1.41" /></svg>
							{:else}
								<svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25A2.25 2.25 0 015.25 3h13.5A2.25 2.25 0 0121 5.25z" /></svg>
							{/if}
						</button>
					</div>
					<div class="flex items-center gap-2 md:hidden">
						<span class="text-xs text-black/40 dark:text-white/40">Supported by</span>
						<img src="/google-for-startups.svg" alt="Google for Startups" class="h-3.5 translate-y-px opacity-40 grayscale dark:invert" />
					</div>
				</div>
			</div>
		</div>
		<p class="mt-4 text-center text-xs text-black/40 dark:text-white/40 md:hidden">
			We use <a href="/privacy-policy" class="underline transition-colors hover:text-black/60 dark:hover:text-white/60">cookies</a>
		</p>
	</div>
</footer>
