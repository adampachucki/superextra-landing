<script lang="ts">
	let year = $state(new Date().getFullYear());
</script>

<footer class="border-t border-gray-200 py-12 pb-20 md:pb-12">
	<div class="mx-auto max-w-[1200px] px-6">
		<div class="flex flex-col items-center justify-between gap-6 md:flex-row">
			<div class="flex flex-col items-center gap-2 md:items-start">
				<span class="text-[22px] font-light tracking-tight text-black">Superextra</span>
				<p class="text-sm text-black/40">
					&copy; {year} Superextra. All rights reserved.
				</p>
			</div>

			<div class="flex flex-col items-center gap-4 md:flex-row md:gap-6">
				<div class="flex items-center gap-6">
					<div class="hidden items-center gap-2 md:flex">
						<span class="text-xs text-black/40">Supported by</span>
						<img src="/google-for-startups.svg" alt="Google for Startups" class="h-3.5 translate-y-px opacity-40 grayscale" />
					</div>
					<span class="mx-2 hidden h-4 w-px bg-black/10 md:block"></span>
					<a href="/privacy-policy" class="text-sm text-black/40 transition-colors hover:text-black/60">Privacy</a>
					<a href="/terms" class="text-sm text-black/40 transition-colors hover:text-black/60">Terms</a>
					<a href="https://www.linkedin.com/company/superextra" target="_blank" rel="noopener noreferrer" class="text-black/40 transition-colors hover:text-black/60" aria-label="LinkedIn">
						<svg class="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" /></svg>
					</a>
				</div>
				<div class="flex items-center gap-2 md:hidden">
					<span class="text-xs text-black/40">Supported by</span>
					<img src="/google-for-startups.svg" alt="Google for Startups" class="h-3.5 translate-y-px opacity-40 grayscale" />
				</div>
			</div>
		</div>
		<p class="mt-4 text-center text-xs text-black/40 md:hidden">
			We use <a href="/privacy-policy" class="underline transition-colors hover:text-black/60">cookies</a>
		</p>
	</div>
</footer>
