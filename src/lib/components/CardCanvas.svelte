<script lang="ts">
	import { onMount } from 'svelte';

	let {
		active = false,
		seed = 0,
		class: className = ''
	}: { active?: boolean; seed?: number; class?: string } = $props();

	let canvasEl: HTMLCanvasElement;
	let ctx: CanvasRenderingContext2D;
	let frame = 0;
	let animating = false;

	const W = 400;
	const H = 300;

	function noise(t: number, s: number): number {
		return (
			Math.sin(t * 0.67 + s * 7.13) * 0.4 +
			Math.sin(t * 1.13 + s * 3.37) * 0.35 +
			Math.sin(t * 0.31 + s * 11.71) * 0.25
		);
	}

	function lerp(a: number, b: number, t: number): number {
		return a + (b - a) * t;
	}

	function lerpColor(a: number[], b: number[], t: number): number[] {
		return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
	}

	function smoothstep(t: number): number {
		return t * t * (3 - 2 * t);
	}

	const colors: number[][] = [
		[110, 231, 183], // emerald
		[167, 139, 250], // violet
		[244, 114, 182], // pink
		[251, 191, 36], // amber
		[6, 182, 212], // cyan
		[99, 102, 241] // indigo
	];

	const blobs = Array.from({ length: 8 }, () => ({
		seed: Math.random() * 100,
		baseX: Math.random() * (W - 80) + 40,
		baseY: Math.random() * (H - 60) + 30,
		baseR: 50 + Math.random() * 60,
		aspectRatio: 0.6 + Math.random() * 0.5
	}));

	function draw(time: number) {
		if (!ctx) return;
		const t = time * 0.001 + seed * 13.7;
		ctx.clearRect(0, 0, W, H);

		const bgSpeed = 0.04;
		const bgPhase = t * bgSpeed;
		const bgIdx = Math.floor(Math.abs(bgPhase)) % colors.length;
		const bgNext = (bgIdx + 1) % colors.length;
		const bgT = smoothstep(bgPhase - Math.floor(bgPhase));
		const bgC1 = lerpColor(colors[bgIdx], colors[bgNext], bgT);
		const bgIdx2 = (bgIdx + 3) % colors.length;
		const bgNext2 = (bgIdx2 + 1) % colors.length;
		const bgC2 = lerpColor(colors[bgIdx2], colors[bgNext2], bgT);

		const angle = noise(t * 0.08, 0.5) * Math.PI * 2;
		const cx = W / 2;
		const cy = H / 2;
		const radius = Math.max(W, H) * 0.6;
		const x0 = cx + Math.cos(angle) * radius;
		const y0 = cy + Math.sin(angle) * radius;
		const x1 = cx - Math.cos(angle) * radius;
		const y1 = cy - Math.sin(angle) * radius;

		const grad = ctx.createLinearGradient(x0, y0, x1, y1);
		grad.addColorStop(0, `rgb(${bgC1[0]},${bgC1[1]},${bgC1[2]})`);
		grad.addColorStop(
			0.5,
			`rgb(${lerp(bgC1[0], bgC2[0], 0.5)},${lerp(bgC1[1], bgC2[1], 0.5)},${lerp(bgC1[2], bgC2[2], 0.5)})`
		);
		grad.addColorStop(1, `rgb(${bgC2[0]},${bgC2[1]},${bgC2[2]})`);
		ctx.fillStyle = grad;
		ctx.fillRect(0, 0, W, H);

		for (const blob of blobs) {
			const s = blob.seed;
			const x = blob.baseX + noise(t * 0.15, s) * 80;
			const y = blob.baseY + noise(t * 0.12, s + 100) * 50;
			const r = blob.baseR * (1 + noise(t * 0.1, s + 200) * 0.4);
			const ry = r * (blob.aspectRatio + noise(t * 0.08, s + 300) * 0.3);
			const rotation = noise(t * 0.06, s + 400) * Math.PI * 0.25;
			const opacity = 0.15 + noise(t * 0.07, s + 500) * 0.15 + 0.15;

			const cSpeed = 0.03 + (s % 5) * 0.005;
			const cPhase = t * cSpeed + s * 0.8;
			const cIdx = Math.floor(Math.abs(cPhase)) % colors.length;
			const cNext = (cIdx + 1) % colors.length;
			const cT = smoothstep(cPhase - Math.floor(cPhase));
			const col = lerpColor(colors[cIdx], colors[cNext], cT);

			ctx.save();
			ctx.globalAlpha = Math.max(0, Math.min(1, opacity));
			ctx.translate(x, y);
			ctx.rotate(rotation);
			ctx.scale(1, ry / r);

			const rg = ctx.createRadialGradient(0, 0, 0, 0, 0, r);
			rg.addColorStop(0, `rgba(${col[0]},${col[1]},${col[2]},0.7)`);
			rg.addColorStop(0.4, `rgba(${col[0]},${col[1]},${col[2]},0.3)`);
			rg.addColorStop(1, `rgba(${col[0]},${col[1]},${col[2]},0)`);
			ctx.fillStyle = rg;
			ctx.beginPath();
			ctx.arc(0, 0, r, 0, Math.PI * 2);
			ctx.fill();
			ctx.restore();
		}
	}

	function loop(time: number) {
		if (!animating) return;
		draw(time);
		frame = requestAnimationFrame(loop);
	}

	function startAnimation() {
		if (animating) return;
		animating = true;
		frame = requestAnimationFrame(loop);
	}

	function stopAnimation() {
		animating = false;
		if (frame) {
			cancelAnimationFrame(frame);
			frame = 0;
		}
	}

	onMount(() => {
		ctx = canvasEl.getContext('2d')!;

		function resize() {
			const rect = canvasEl.getBoundingClientRect();
			const dpr = window.devicePixelRatio || 1;
			canvasEl.width = rect.width * dpr;
			canvasEl.height = rect.height * dpr;
			ctx.setTransform((rect.width * dpr) / W, 0, 0, (rect.height * dpr) / H, 0, 0);
			draw(seed * 5000 + 5000);
		}

		const ro = new ResizeObserver(resize);
		ro.observe(canvasEl);
		resize();

		return () => {
			stopAnimation();
			ro.disconnect();
		};
	});

	$effect(() => {
		if (active) {
			startAnimation();
		} else {
			stopAnimation();
		}
	});
</script>

<canvas bind:this={canvasEl} class={className} style="width:100%;height:100%"></canvas>
