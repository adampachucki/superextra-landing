<script lang="ts">
	import * as m from '$lib/paraglide/messages';
</script>

<section class="bg-black py-24 text-white md:py-32">
	<div class="mx-auto max-w-[1200px] px-6">
		<h2 class="mx-auto mb-4 text-center heading-display">{m.aud_title()}</h2>
		<p class="mx-auto mb-16 max-w-lg text-center text-lg text-white/50">
			{m.aud_sub()}
		</p>

		<div
			class="grid grid-cols-1 gap-px overflow-hidden border-t border-white/10 bg-white/10 sm:grid-cols-2 lg:grid-cols-3"
		>
			<div class="bg-black p-8">
				<h3 class="mb-2 text-base font-medium text-white">{m.aud_independent_title()}</h3>
				<p class="text-sm leading-snug text-white/40">
					{m.aud_independent_desc()}
				</p>
			</div>
			<div class="bg-black p-8">
				<h3 class="mb-2 text-base font-medium text-white">{m.aud_chains_title()}</h3>
				<p class="text-sm leading-snug text-white/40">
					{m.aud_chains_desc()}
				</p>
			</div>
			<div class="bg-black p-8">
				<h3 class="mb-2 text-base font-medium text-white">{m.aud_suppliers_title()}</h3>
				<p class="text-sm leading-snug text-white/40">
					{m.aud_suppliers_desc()}
				</p>
			</div>
			<div class="bg-black p-8">
				<h3 class="mb-2 text-base font-medium text-white">{m.aud_tech_title()}</h3>
				<p class="text-sm leading-snug text-white/40">
					{m.aud_tech_desc()}
				</p>
			</div>
			<div class="bg-black p-8">
				<h3 class="mb-2 text-base font-medium text-white">{m.aud_agencies_title()}</h3>
				<p class="text-sm leading-snug text-white/40">
					{m.aud_agencies_desc()}
				</p>
			</div>
			<div class="bg-black p-8">
				<h3 class="mb-2 text-base font-medium text-white">{m.aud_investors_title()}</h3>
				<p class="text-sm leading-snug text-white/40">
					{m.aud_investors_desc()}
				</p>
			</div>
		</div>
	</div>
</section>
