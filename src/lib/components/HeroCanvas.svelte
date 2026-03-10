<script lang="ts">
	import { onMount } from 'svelte';

	let { animate = true, class: className = '' }: { animate?: boolean; class?: string } = $props();

	let canvasEl: HTMLCanvasElement;

	onMount(() => {
		const ctx = canvasEl.getContext('2d')!;
		const W = 680;
		const H = 400;

		function noise(t: number, seed: number): number {
			return (
				Math.sin(t * 0.67 + seed * 7.13) * 0.4 +
				Math.sin(t * 1.13 + seed * 3.37) * 0.35 +
				Math.sin(t * 0.31 + seed * 11.71) * 0.25
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

		const blobs = Array.from({ length: 8 }, (_, i) => ({
			seed: i * 13.7 + 5.3,
			baseX: ((i * 97 + 80) % (W - 100)) + 50,
			baseY: ((i * 73 + 40) % (H - 80)) + 40,
			baseR: 70 + ((i * 41) % 80),
			aspectRatio: 0.6 + ((i * 29) % 50) / 50
		}));

		const lines = [
			{ seed: 3.7, baseY: 130, width: 1.5, points: 5, amp: 80 },
			{ seed: 17.3, baseY: 220, width: 1.5, points: 6, amp: 90 },
			{ seed: 31.1, baseY: 300, width: 1, points: 4, amp: 70 }
		];

		const circles = [
			{ seed: 41.3, baseX: W * 0.15, baseY: H * 0.3, baseR: 300 },
			{ seed: 67.9, baseX: W * 0.85, baseY: H * 0.7, baseR: 250 }
		];

		let frame: number;

		function draw(time: number) {
			const t = time * 0.001;
			ctx.clearRect(0, 0, W, H);

			const bgSpeed = 0.04;
			const bgPhase = t * bgSpeed;
			const bgIdx = Math.floor(bgPhase) % colors.length;
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
			grad.addColorStop(0.5, `rgb(${lerp(bgC1[0], bgC2[0], 0.5)},${lerp(bgC1[1], bgC2[1], 0.5)},${lerp(bgC1[2], bgC2[2], 0.5)})`);
			grad.addColorStop(1, `rgb(${bgC2[0]},${bgC2[1]},${bgC2[2]})`);
			ctx.fillStyle = grad;
			ctx.fillRect(0, 0, W, H);

			for (const blob of blobs) {
				const s = blob.seed;
				const x = blob.baseX + noise(t * 0.15, s) * 100;
				const y = blob.baseY + noise(t * 0.12, s + 100) * 70;
				const r = blob.baseR * (1 + noise(t * 0.1, s + 200) * 0.4);
				const ry = r * (blob.aspectRatio + noise(t * 0.08, s + 300) * 0.3);
				const rotation = noise(t * 0.06, s + 400) * Math.PI * 0.25;
				const opacity = 0.15 + noise(t * 0.07, s + 500) * 0.15 + 0.15;

				const cSpeed = 0.03 + (s % 5) * 0.005;
				const cPhase = t * cSpeed + s * 0.8;
				const cIdx = Math.floor(cPhase) % colors.length;
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

			for (const circle of circles) {
				const s = circle.seed;
				const x = circle.baseX + noise(t * 0.06, s) * 60;
				const y = circle.baseY + noise(t * 0.05, s + 100) * 40;
				const r = circle.baseR * (1 + noise(t * 0.04, s + 200) * 0.2);
				const fadeRaw = noise(t * 0.05, s + 500);
				const opacity = Math.max(0, fadeRaw * 0.5 + 0.15);

				ctx.save();
				ctx.globalAlpha = Math.min(0.15, opacity);
				ctx.fillStyle = 'rgba(255,255,255,0.5)';
				ctx.beginPath();
				ctx.arc(x, y, r, 0, Math.PI * 2);
				ctx.fill();
				ctx.restore();
			}

			for (const line of lines) {
				const s = line.seed;
				const opacity = 0.15 + noise(t * 0.08, s + 600) * 0.1 + 0.05;
				const step = (W + 40) / (line.points - 1);

				const pts: { x: number; y: number }[] = [];
				for (let j = 0; j < line.points; j++) {
					pts.push({
						x: -20 + j * step,
						y: line.baseY + noise(t * 0.15 + j * 0.5, s + j * 11) * line.amp
					});
				}

				ctx.save();
				ctx.globalAlpha = Math.max(0.05, opacity);
				ctx.strokeStyle = 'white';
				ctx.lineWidth = line.width;
				ctx.lineCap = 'round';
				ctx.lineJoin = 'round';
				ctx.beginPath();
				ctx.moveTo(pts[0].x, pts[0].y);

				const tension = 0.3;
				for (let j = 0; j < pts.length - 1; j++) {
					const p0 = pts[Math.max(0, j - 1)];
					const p1 = pts[j];
					const p2 = pts[j + 1];
					const p3 = pts[Math.min(pts.length - 1, j + 2)];

					const cp1x = p1.x + (p2.x - p0.x) * tension;
					const cp1y = p1.y + (p2.y - p0.y) * tension;
					const cp2x = p2.x - (p3.x - p1.x) * tension;
					const cp2y = p2.y - (p3.y - p1.y) * tension;

					ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y);
				}

				ctx.stroke();
				ctx.restore();
			}

			if (animate) {
				frame = requestAnimationFrame(draw);
			}
		}

		function resize() {
			const rect = canvasEl.getBoundingClientRect();
			const dpr = window.devicePixelRatio || 1;
			canvasEl.width = rect.width * dpr;
			canvasEl.height = rect.height * dpr;
			ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
			if (!animate) {
				draw(5000);
			}
		}

		const ro = new ResizeObserver(resize);
		ro.observe(canvasEl);
		resize();

		if (animate) {
			frame = requestAnimationFrame(draw);
		}

		return () => {
			if (frame) cancelAnimationFrame(frame);
			ro.disconnect();
		};
	});
</script>

<canvas
	bind:this={canvasEl}
	class={className}
	style="width:100%;height:100%"
></canvas>
