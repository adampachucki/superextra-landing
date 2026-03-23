<script lang="ts">
	let { index, hovered = false }: { index: number; hovered: boolean } = $props();
</script>

<svg viewBox="0 0 200 200" fill="none" class="w-full" class:hovered>
{#if index === 0}
	<!-- Market Landscape: Voronoi partition — market territory segmentation -->

	<g class="partition">
		<!-- Boundary edges (partition lines reaching the edge) -->
		<line x1="78" y1="12" x2="75" y2="50" stroke="black" stroke-width="0.5" stroke-dasharray="1.5,3"/>
		<line x1="188" y1="74" x2="155" y2="80" stroke="black" stroke-width="0.5" stroke-dasharray="1.5,3"/>
		<line x1="12" y1="100" x2="42" y2="98" stroke="black" stroke-width="0.6"/>
		<line x1="95" y1="155" x2="90" y2="188" stroke="black" stroke-width="0.5" stroke-dasharray="1.5,3"/>

		<!-- Internal edges (cell dividers) -->
		<line x1="75" y1="50" x2="155" y2="80" stroke="black" stroke-width="0.8"/>
		<line x1="75" y1="50" x2="42" y2="98" stroke="black" stroke-width="0.8"/>
		<line class="ants" x1="155" y1="80" x2="95" y2="155" stroke="black" stroke-width="0.6" stroke-dasharray="4,3"/>
		<line x1="42" y1="98" x2="95" y2="155" stroke="black" stroke-width="0.8"/>

		<!-- Junction dots -->
		<circle cx="75" cy="50" r="1.5" fill="black"/>
		<circle cx="155" cy="80" r="1.5" fill="black"/>
		<circle cx="42" cy="98" r="1.5" fill="black"/>
		<circle cx="95" cy="155" r="1.5" fill="black"/>

		<!-- Cell A: top-left -->
		<circle cx="32" cy="30" r="2.5" stroke="black" stroke-width="0.7" fill="none"/>
		<circle cx="32" cy="30" r="1" fill="black"/>

		<!-- Cell B: top-right (monitored — dashed halo) -->
		<circle cx="138" cy="30" r="3" stroke="black" stroke-width="0.8" fill="none"/>
		<circle cx="138" cy="30" r="1.5" fill="black"/>
		<circle class="ants-rev" cx="138" cy="30" r="8" stroke="black" stroke-width="0.4" stroke-dasharray="2,3" fill="none"/>

		<!-- Cell C: bottom-left (emerging — dashed outline) -->
		<circle cx="25" cy="148" r="2.5" stroke="black" stroke-width="0.6" stroke-dasharray="3,3" fill="none"/>
		<circle cx="25" cy="148" r="1" fill="black"/>

		<!-- Cell D: bottom-right -->
		<circle cx="152" cy="152" r="2.5" stroke="black" stroke-width="0.7" fill="none"/>
		<circle cx="152" cy="152" r="1" fill="black"/>

		<!-- Cell E: center (dominant) -->
		<g class="center-dot">
			<circle cx="98" cy="92" r="4" stroke="black" stroke-width="0.9" fill="none"/>
			<circle cx="98" cy="92" r="1.5" fill="black"/>
		</g>
	</g>

{:else if index === 1}
	<!-- Menu & Pricing: Parallel tracking curves with gap markers -->

	<!-- Baseline reference -->
	<line x1="10" y1="168" x2="190" y2="168" stroke="black" stroke-width="0.3" stroke-dasharray="1.5,3"/>

	<!-- Upper curve (primary price line) -->
	<g class="curve-upper">
		<path d="M 18,82 C 50,65 80,92 115,75 C 150,58 172,70 184,62" stroke="black" stroke-width="0.9" fill="none"/>
		<circle cx="18" cy="82" r="1.5" fill="black"/>
		<circle cx="184" cy="62" r="1.5" fill="black"/>
	</g>

	<!-- Lower curve (comparison price line) -->
	<g class="curve-lower">
		<path d="M 18,120 C 50,105 80,130 115,115 C 150,100 172,110 184,102" stroke="black" stroke-width="0.9" fill="none"/>
		<circle cx="18" cy="120" r="1.5" fill="black"/>
		<circle cx="184" cy="102" r="1.5" fill="black"/>
	</g>

	<!-- Delivery curve (diverges upward from primary) -->
	<g class="curve-delivery">
		<path class="ants" d="M 18,76 C 50,55 80,58 115,42 C 150,26 172,34 184,28" stroke="black" stroke-width="0.6" stroke-dasharray="4,3" fill="none"/>
		<circle cx="18" cy="76" r="1" fill="black"/>
		<circle cx="184" cy="28" r="1.5" fill="black"/>
	</g>

	<!-- Gap tick marks between upper and lower curves -->
	<line x1="48" y1="72" x2="48" y2="108" stroke="black" stroke-width="0.5"/>
	<circle cx="48" cy="72" r="1" fill="black"/>
	<circle cx="48" cy="108" r="1" fill="black"/>

	<line x1="82" y1="88" x2="82" y2="126" stroke="black" stroke-width="0.5"/>
	<circle cx="82" cy="88" r="1" fill="black"/>
	<circle cx="82" cy="126" r="1" fill="black"/>

	<line x1="115" y1="76" x2="115" y2="114" stroke="black" stroke-width="0.5"/>
	<circle cx="115" cy="76" r="1" fill="black"/>
	<circle cx="115" cy="114" r="1" fill="black"/>

	<line class="ants-rev" x1="150" y1="62" x2="150" y2="102" stroke="black" stroke-width="0.5" stroke-dasharray="2,3"/>
	<circle cx="150" cy="62" r="1" fill="black"/>
	<circle cx="150" cy="102" r="1" fill="black"/>
{/if}
</svg>

<style>
	/* === Shared: marching ants === */
	.ants, .ants-rev {
		stroke-dashoffset: 0;
		transition: stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1);
	}
	.hovered .ants { stroke-dashoffset: -21; }
	.hovered .ants-rev { stroke-dashoffset: 18; }

	/* === 0: Market Landscape — partition shifts on hover === */
	.partition {
		transform-origin: 100px 100px;
		transition: transform 0.7s cubic-bezier(0.4, 0, 0.2, 1);
	}
	.hovered .partition { transform: rotate(3deg) scale(1.02); }

	.center-dot {
		transform-origin: 98px 92px;
		transition: transform 0.6s ease;
	}
	.hovered .center-dot { transform: scale(1.12); }

	/* === 1: Menu & Pricing — curves separate on hover === */
	.curve-upper {
		transition: transform 0.7s cubic-bezier(0.4, 0, 0.2, 1);
	}
	.hovered .curve-upper { transform: translateY(-4px); }

	.curve-lower {
		transition: transform 0.7s cubic-bezier(0.4, 0, 0.2, 1);
	}
	.hovered .curve-lower { transform: translateY(4px); }

	.curve-delivery {
		transition: transform 0.8s cubic-bezier(0.4, 0, 0.2, 1);
	}
	.hovered .curve-delivery { transform: translateY(-6px); }
</style>
