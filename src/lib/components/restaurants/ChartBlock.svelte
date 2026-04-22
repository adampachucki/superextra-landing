<script lang="ts">
	import { onDestroy } from 'svelte';
	import {
		Chart,
		BarController,
		LineController,
		PieController,
		BarElement,
		LineElement,
		PointElement,
		ArcElement,
		CategoryScale,
		LinearScale,
		Tooltip,
		Legend,
		Title,
		type ChartConfiguration
	} from 'chart.js';
	import type { ChartSpec } from '$lib/chart-blocks';

	Chart.register(
		BarController,
		LineController,
		PieController,
		BarElement,
		LineElement,
		PointElement,
		ArcElement,
		CategoryScale,
		LinearScale,
		Tooltip,
		Legend,
		Title
	);

	let { spec }: { spec: ChartSpec } = $props();

	let canvas: HTMLCanvasElement | undefined = $state();
	let chart: Chart | undefined;

	// Cream-toned palette matches the rest of the UI; opacity varies across
	// slices so categorical charts read without a legend-heavy layout.
	const PALETTE = [
		'rgba(120, 90, 60, 0.85)',
		'rgba(160, 130, 90, 0.85)',
		'rgba(90, 110, 90, 0.85)',
		'rgba(140, 100, 100, 0.85)',
		'rgba(80, 100, 130, 0.85)',
		'rgba(160, 140, 80, 0.85)',
		'rgba(110, 130, 110, 0.85)',
		'rgba(130, 90, 120, 0.85)'
	];

	function buildConfig(spec: ChartSpec): ChartConfiguration {
		const title = spec.title ? { display: true, text: spec.title } : { display: false };
		if (spec.type === 'bar') {
			const labels = spec.data.map((d) => String(d.label ?? ''));
			const values = spec.data.map((d) => Number(d.value ?? 0));
			return {
				type: 'bar',
				data: {
					labels,
					datasets: [
						{
							data: values,
							backgroundColor: labels.map((_, i) => PALETTE[i % PALETTE.length]),
							borderWidth: 0
						}
					]
				},
				options: {
					responsive: true,
					maintainAspectRatio: false,
					plugins: { legend: { display: false }, title },
					scales: { y: { beginAtZero: true } }
				}
			};
		}
		if (spec.type === 'pie') {
			const labels = spec.data.map((d) => String(d.label ?? ''));
			const values = spec.data.map((d) => Number(d.value ?? 0));
			return {
				type: 'pie',
				data: {
					labels,
					datasets: [
						{
							data: values,
							backgroundColor: labels.map((_, i) => PALETTE[i % PALETTE.length]),
							borderWidth: 0
						}
					]
				},
				options: {
					responsive: true,
					maintainAspectRatio: false,
					plugins: { legend: { position: 'right' }, title }
				}
			};
		}
		// line — stringify x values to let Chart.js treat them as categorical
		// labels. Keeps the type simple; numeric-x axes weren't load-bearing.
		const labels = spec.data.map((d) => String(d.x ?? ''));
		const values = spec.data.map((d) => Number(d.y ?? 0));
		return {
			type: 'line',
			data: {
				labels,
				datasets: [
					{
						data: values,
						borderColor: PALETTE[0],
						backgroundColor: PALETTE[0],
						tension: 0.25,
						pointRadius: 3
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: { legend: { display: false }, title },
				scales: { y: { beginAtZero: true } }
			}
		};
	}

	$effect(() => {
		if (!canvas) return;
		chart?.destroy();
		try {
			chart = new Chart(canvas, buildConfig(spec));
		} catch (err) {
			console.warn('chart render failed', err);
		}
	});

	onDestroy(() => chart?.destroy());
</script>

<div
	class="chart-block my-4 rounded-lg border border-black/10 bg-white/60 p-3 dark:border-white/10 dark:bg-black/20"
>
	<div class="h-[260px] w-full">
		<canvas bind:this={canvas}></canvas>
	</div>
</div>
